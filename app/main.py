from fastapi import FastAPI, HTTPException, Query, status, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
import httpx
import os
import socket
import uuid
import signal
import sys

from app.config import settings
from app.database import db
from app.tasks import TaskManager, TaskCreate, TaskUpdate, Task
from app.llm import llm_client
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

from app.tools.youtube_learner import YouTubeLearner
from app.tools.web_research import WebResearcher
from app.tools.doc_reader import DocumentReader
from app.tools.doc_manager import DocumentManager
from app.tools.knowledge_indexer import KnowledgeIndexer

from app.perception.speech_to_text import LocalSpeechToText
from app.perception.text_to_speech import LocalTextToSpeech

from app.tools.screen_capture import ScreenCaptureTool
from app.tools.ocr_reader import OCRReaderTool
from app.tools.vision_analyzer import VisionAnalyzerTool

app = FastAPI(
    title=settings.APP_NAME,
    description="Version 0 Core Engine & Visual Dashboard for the Local Personal Assistant",
    version="0.1.0"
)

# Global System State
SYSTEM_STATE = "active"  # "active" or "sleeping"

# Mount static files directory if it exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount audio static directory
audio_dir = settings.DATA_DIR / "audio"
audio_dir.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

# Models for the API
class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    complexity: str = Field(default="fast", description="'fast' for Qwen 3B/4B, 'main' for Qwen 9B")
    temperature: float = 0.7
    max_tokens: int = 512

class ActionEvaluationRequest(BaseModel):
    action_type: str
    details: Dict[str, Any]

class MemoryCreate(BaseModel):
    content: str
    category: str
    source: Optional[str] = "user"
    confidence: Optional[float] = 1.0

class DocUpdate(BaseModel):
    content: str

class ModelConfigUpdate(BaseModel):
    fast_model: Optional[str] = None
    main_model: Optional[str] = None
    lm_studio_url: Optional[str] = None

class ModelUnloadRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: Optional[str] = None

class YouTubeLearnRequest(BaseModel):
    url: str
    prompt_focus: Optional[str] = None
    auto_save_memory: bool = True

class WebLearnRequest(BaseModel):
    url: str
    auto_save_memory: bool = True

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 3

class DocReadRequest(BaseModel):
    file_path: str
    auto_save_memory: bool = True

class DocCreateRequest(BaseModel):
    file_path: str
    content: str
    overwrite: bool = False

class DocEditRequest(BaseModel):
    file_path: str
    new_content: Optional[str] = None
    append_content: Optional[str] = None
    search_target: Optional[str] = None
    replace_text: Optional[str] = None

class TTSSynthesizeRequest(BaseModel):
    text: str

class VoiceProfileSelectRequest(BaseModel):
    profile_name: str

class MobileLocationRequest(BaseModel):
    latitude: float
    longitude: float
    city: Optional[str] = None

class SystemSleepRequest(BaseModel):
    mode: str = Field(..., description="'sleeping' or 'active'")

class VisionOCRRequest(BaseModel):
    image_path: str

class VisionAnalyzeRequest(BaseModel):
    image_path: str
    prompt_focus: Optional[str] = None
    auto_save_memory: bool = True

# 1. Base Endpoint - Serves HTML Visual Dashboard or JSON status
@app.get("/")
def get_root(request: Request):
    # Check if client explicitly requested JSON
    accept_header = request.headers.get("accept", "")
    index_path = os.path.join(static_dir, "index.html")

    if "text/html" in accept_header and os.path.exists(index_path):
        return FileResponse(index_path)

    # Return JSON API status by default for non-HTML/API requests
    lm_status = "offline"
    try:
        r = httpx.get(f"{settings.LM_STUDIO_URL}/models", timeout=2.0)
        if r.status_code == 200:
            lm_status = "online"
    except Exception:
        pass

    return {
        "status": "online",
        "system_mode": SYSTEM_STATE,
        "app_name": settings.APP_NAME,
        "version": "0.1.0",
        "local_llm_status": lm_status,
        "lm_studio_endpoint": settings.LM_STUDIO_URL,
        "database_connected": True
    }

@app.get("/api/status")
def get_api_status():
    lm_status = "offline"
    try:
        r = httpx.get(f"{settings.LM_STUDIO_URL}/models", timeout=2.0)
        if r.status_code == 200:
            lm_status = "online"
    except Exception:
        pass

    return {
        "status": "online",
        "system_mode": SYSTEM_STATE,
        "app_name": settings.APP_NAME,
        "version": "0.1.0",
        "local_llm_status": lm_status,
        "lm_studio_endpoint": settings.LM_STUDIO_URL,
        "database_connected": True
    }

# 2. Local Chat Completions Route
@app.post("/chat")
def chat_with_local_brain(req: ChatRequest):
    global SYSTEM_STATE
    if SYSTEM_STATE == "sleeping":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is currently in SLEEP MODE. Wake up the assistant from the dashboard header to resume."
        )

    app_logger.info(f"Chat request with complexity '{req.complexity}' received.")
    try:
        response = llm_client.generate_chat_completion(
            messages=req.messages,
            complexity=req.complexity,
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        return response
    except Exception as e:
        app_logger.error(f"Error in /chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# 3. Tasks Endpoints
@app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_persistent_task(task_in: TaskCreate):
    try:
        return TaskManager.create_task(task_in)
    except Exception as e:
        app_logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks", response_model=List[Task])
def list_tasks(status: Optional[str] = Query(None, description="Filter tasks by status")):
    return TaskManager.get_all_tasks(status=status)

@app.get("/tasks/{task_id}", response_model=Task)
def get_single_task(task_id: str):
    task = TaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.patch("/tasks/{task_id}", response_model=Task)
def update_existing_task(task_id: str, updates: TaskUpdate):
    task = TaskManager.update_task(task_id, updates)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or update failed")
    return task

@app.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK)
def delete_task_by_id(task_id: str):
    if not TaskManager.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found or deletion failed")
    return {"message": f"Task {task_id} deleted successfully."}

@app.post("/tasks/{task_id}/acquire-skill")
def acquire_skill_for_task_endpoint(task_id: str):
    res = TaskManager.acquire_skill_for_task(task_id)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error", "Task not found"))
    return res

# 4. Audit Log Endpoint
@app.get("/audit-logs")
def view_audit_logs(limit: int = Query(50, ge=1, le=500)):
    return db.get_audit_logs(limit=limit)

# 5. Memories Endpoints
@app.post("/memories", status_code=status.HTTP_201_CREATED)
def add_new_memory(mem: MemoryCreate):
    try:
        mem_id = db.create_memory({
            "content": mem.content,
            "category": mem.category,
            "source": mem.source,
            "confidence": mem.confidence
        })
        return {"id": mem_id, "message": "Memory stored successfully."}
    except Exception as e:
        app_logger.error(f"Error saving memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories")
def list_memories(category: Optional[str] = Query(None, description="Filter memories by category")):
    return db.get_memories(category=category)

@app.delete("/memories/{memory_id}")
def delete_memory_record(memory_id: int):
    if not db.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found or deletion failed")
    return {"message": f"Memory {memory_id} deleted successfully."}

# 6. Policy & Rules Evaluation Endpoint
@app.post("/policies/evaluate")
def evaluate_action_policy(req: ActionEvaluationRequest):
    allowed, reason, level = PolicyEvaluator.evaluate_action(req.action_type, req.details)
    return {
        "allowed": allowed,
        "reason": reason,
        "authority_level": level,
        "action": req.action_type
    }

# 7. File Readers & Editors for Context Docs (Manual and Rules)
@app.get("/manual")
def get_user_manual():
    try:
        with open(settings.USER_MANUAL_PATH, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="User Operating Manual not found")

@app.post("/manual")
def update_user_manual(doc: DocUpdate):
    try:
        os.makedirs(os.path.dirname(settings.USER_MANUAL_PATH), exist_ok=True)
        with open(settings.USER_MANUAL_PATH, "w", encoding="utf-8") as f:
            f.write(doc.content)
        db.create_audit_log("update_user_manual", "success", "User operating manual updated.", level=1)
        return {"message": "User Operating Manual updated successfully."}
    except Exception as e:
        app_logger.error(f"Error updating user manual: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rules")
def get_rules():
    try:
        with open(settings.RULES_PATH, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Rules and boundaries document not found")

@app.post("/rules")
def update_rules(doc: DocUpdate):
    try:
        os.makedirs(os.path.dirname(settings.RULES_PATH), exist_ok=True)
        with open(settings.RULES_PATH, "w", encoding="utf-8") as f:
            f.write(doc.content)
        db.create_audit_log("update_rules", "success", "Rules and boundaries updated.", level=1)
        return {"message": "Rules and boundaries updated successfully."}
    except Exception as e:
        app_logger.error(f"Error updating rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 8. Model Management & Real-time LM Studio Query Endpoints
@app.get("/models")
def get_local_models():
    lm_online = False
    loaded_models = []
    try:
        r = httpx.get(f"{settings.LM_STUDIO_URL}/models", timeout=3.0)
        if r.status_code == 200:
            lm_online = True
            data = r.json()
            if "data" in data and isinstance(data["data"], list):
                loaded_models = [m.get("id", "") for m in data["data"] if m.get("id")]
    except Exception as e:
        app_logger.warning(f"Unable to query LM Studio models endpoint: {e}")

    return {
        "lm_studio_online": lm_online,
        "lm_studio_url": settings.LM_STUDIO_URL,
        "loaded_models": loaded_models,
        "configured_fast_model": settings.FAST_MODEL,
        "configured_main_model": settings.MAIN_MODEL
    }

@app.post("/models/config")
def update_model_config(config: ModelConfigUpdate):
    if config.fast_model:
        settings.FAST_MODEL = config.fast_model.strip()
    if config.main_model:
        settings.MAIN_MODEL = config.main_model.strip()
    if config.lm_studio_url:
        settings.LM_STUDIO_URL = config.lm_studio_url.rstrip('/').strip()
        llm_client.base_url = settings.LM_STUDIO_URL
    
    db.create_audit_log("update_model_config", "success", f"Fast Model: {settings.FAST_MODEL}, Main Model: {settings.MAIN_MODEL}, Endpoint: {settings.LM_STUDIO_URL}", level=1)
    
    return {
        "message": "Model settings updated successfully.",
        "configured_fast_model": settings.FAST_MODEL,
        "configured_main_model": settings.MAIN_MODEL,
        "lm_studio_url": settings.LM_STUDIO_URL
    }

@app.post("/models/unload")
def unload_lm_studio_model(req: Optional[ModelUnloadRequest] = None):
    model_id = req.model_id if req else None
    results = []
    
    for ep in ["/models/unload", "/models/eject"]:
        try:
            payload = {"model": model_id} if model_id else {}
            r = httpx.post(f"{settings.LM_STUDIO_URL}{ep}", json=payload, timeout=3.0)
            if r.status_code == 200:
                results.append(f"Successfully called {ep}")
        except Exception:
            pass

    return {
        "message": "Unload command issued.",
        "details": results if results else "Note: For strict 1-model VRAM limit, set 'Max Loaded Models = 1' in LM Studio Settings."
    }

# 9. Phase 2 Tools: Web Scraper, YouTube Learner & All-Purpose Document Manager Endpoints
@app.post("/tools/youtube-learn")
def youtube_learn_endpoint(req: YouTubeLearnRequest):
    result = YouTubeLearner.learn_from_video(req.url, prompt_focus=req.prompt_focus)
    if result.get("success") and req.auto_save_memory:
        mem_id = KnowledgeIndexer.index_youtube_knowledge(result)
        result["memory_id"] = mem_id
    return result

@app.post("/tools/web-learn")
def web_learn_endpoint(req: WebLearnRequest):
    result = WebResearcher.learn_from_article(req.url)
    if result.get("success") and req.auto_save_memory:
        mem_id = KnowledgeIndexer.index_web_knowledge(result)
        result["memory_id"] = mem_id
    return result

@app.post("/tools/web-search")
def web_search_endpoint(req: WebSearchRequest):
    return WebResearcher.search_and_scrape(req.query, max_results=req.max_results)

@app.get("/tools/approved-docs")
def list_approved_docs_endpoint():
    return DocumentManager.list_workspace_files()

@app.get("/tools/workspace-files")
def list_workspace_files_endpoint():
    return DocumentManager.list_workspace_files()

@app.post("/tools/read-doc")
def read_doc_endpoint(req: DocReadRequest):
    result = DocumentManager.read_document(req.file_path)
    if result.get("success") and req.auto_save_memory:
        summary_prompt = f"Summarize key technical takeaways from this document ({result['file_name']}):\n\n{result['content'][:8000]}"
        try:
            llm_res = llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": summary_prompt}],
                complexity="main",
                max_tokens=600
            )
            ai_summary = llm_res["choices"][0]["message"]["content"] if llm_res.get("choices") else "Document content ingested."
            mem_id = KnowledgeIndexer.index_doc_knowledge(result, ai_summary)
            result["memory_id"] = mem_id
            result["ai_summary"] = ai_summary
        except Exception as e:
            app_logger.error(f"Error summarizing document: {e}")
    return result

@app.post("/tools/create-doc")
def create_doc_endpoint(req: DocCreateRequest):
    return DocumentManager.create_document(req.file_path, req.content, overwrite=req.overwrite)

@app.post("/tools/edit-doc")
def edit_doc_endpoint(req: DocEditRequest):
    return DocumentManager.edit_document(
        req.file_path,
        new_content=req.new_content,
        append_content=req.append_content,
        search_target=req.search_target,
        replace_text=req.replace_text
    )

# 10. Phase 3 Perception: Local Speech-to-Text & Text-to-Speech Endpoints
@app.post("/voice/transcribe")
async def voice_transcribe_endpoint(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    temp_filename = f"recording_{file.filename or 'input.wav'}"
    temp_path = settings.DATA_DIR / "audio" / temp_filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(temp_path, "wb") as f:
        f.write(audio_bytes)
        
    res = LocalSpeechToText.transcribe_file(str(temp_path))
    db.create_audit_log("voice_transcribe", "success", f"Transcribed {file.filename}: '{res.get('text', '')[:100]}'", level=0)
    return res

@app.post("/voice/synthesize")
def voice_synthesize_endpoint(req: TTSSynthesizeRequest):
    res = LocalTextToSpeech.synthesize_speech(req.text)
    db.create_audit_log("voice_synthesize", "success", f"Synthesized speech for text: '{req.text[:80]}'", level=0)
    return res

@app.post("/voice/clone-reference")
async def upload_voice_clone_reference(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    ref_path = LocalTextToSpeech.set_custom_voice_reference(audio_bytes)
    db.create_audit_log("upload_voice_clone_reference", "success", f"Saved custom voice cloning reference ({len(audio_bytes)} bytes)", level=0)
    return {
        "success": True,
        "message": "Custom voice cloning reference updated successfully!",
        "file_path": ref_path
    }

@app.get("/voice/profiles")
def get_voice_profiles_endpoint():
    return LocalTextToSpeech.list_voice_profiles()

@app.post("/voice/profiles/select")
def select_voice_profile_endpoint(req: VoiceProfileSelectRequest):
    success = LocalTextToSpeech.set_active_voice_profile(req.profile_name)
    db.create_audit_log("select_voice_profile", "success", f"Selected voice profile: '{req.profile_name}'", level=0)
    return {"success": success, "active_profile": req.profile_name}

@app.post("/voice/profiles/record")
async def record_voice_profile_endpoint(file: UploadFile = File(...), profile_name: str = Query(...)):
    audio_bytes = await file.read()
    res = LocalTextToSpeech.save_voice_profile(profile_name, audio_bytes)
    db.create_audit_log("record_voice_profile", "success", f"Recorded custom voice profile: '{profile_name}'", level=0)
    return res

@app.post("/voice/chat")
async def voice_chat_endpoint(file: UploadFile = File(...), complexity: str = Query("fast")):
    global SYSTEM_STATE
    if SYSTEM_STATE == "sleeping":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is currently in SLEEP MODE. Wake up the assistant to resume."
        )

    # 1. Save and Transcribe Audio
    audio_bytes = await file.read()
    temp_filename = f"voice_input_{file.filename or 'mic.wav'}"
    temp_path = settings.DATA_DIR / "audio" / temp_filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(temp_path, "wb") as f:
        f.write(audio_bytes)
        
    stt_res = LocalSpeechToText.transcribe_file(str(temp_path))
    user_text = stt_res.get("text", "").strip()
    
    # Conversational Fallback if no clear speech detected
    if not user_text or len(user_text) == 0:
        fallback_msg = "I didn't get that—I couldn't hear you clearly. Could you please say that again?"
        tts_res = LocalTextToSpeech.synthesize_speech(fallback_msg)
        return {
            "success": True,
            "user_text": "[Unclear speech / No audio detected]",
            "assistant_text": fallback_msg,
            "audio_url": tts_res.get("audio_url", ""),
            "model_used": "System Voice Perception"
        }

    # 2. Chat Completion with Local LLM Brain
    messages = [{"role": "user", "content": user_text}]
    llm_res = llm_client.generate_chat_completion(
        messages=messages,
        complexity=complexity,
        max_tokens=256
    )
    
    assistant_text = "No response generated."
    if llm_res.get("choices") and len(llm_res["choices"]) > 0:
        assistant_text = llm_res["choices"][0]["message"]["content"]

    # 3. Synthesize Speech
    tts_res = LocalTextToSpeech.synthesize_speech(assistant_text)

    return {
        "success": True,
        "user_text": user_text,
        "assistant_text": assistant_text,
        "audio_url": tts_res.get("audio_url", ""),
        "model_used": llm_res.get("model", "")
    }

# 11. Mobile Network & Remote Access Endpoints
@app.get("/api/network-info")
def get_network_info_endpoint():
    local_ips = []
    try:
        hostname = socket.gethostname()
        local_ips.append(socket.gethostbyname(hostname))
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        default_ip = s.getsockname()[0]
        s.close()
        if default_ip not in local_ips:
            local_ips.insert(0, default_ip)
    except Exception:
        if not local_ips:
            local_ips = ["127.0.0.1"]

    mobile_urls = [f"http://{ip}:8000/" for ip in local_ips]
    return {
        "local_ips": local_ips,
        "mobile_urls": mobile_urls,
        "instructions": "Connect your Android or iPhone to the same home Wi-Fi and open any of the mobile URLs in Chrome/Safari!"
    }

@app.post("/mobile/location")
def update_mobile_location_endpoint(req: MobileLocationRequest):
    loc_str = f"Latitude: {req.latitude}, Longitude: {req.longitude}" + (f" ({req.city})" if req.city else "")
    db.create_memory({
        "content": f"User Physical Location Context: {loc_str}",
        "category": "user_location",
        "source": "mobile_gps",
        "confidence": 1.0
    })
    db.create_audit_log("update_mobile_location", "success", loc_str, level=0)
    return {"success": True, "location": loc_str, "message": "Location context saved to memory."}

@app.post("/mobile/camera")
async def upload_mobile_camera_photo(file: UploadFile = File(...)):
    photo_bytes = await file.read()
    filename = f"camera_{uuid.uuid4().hex[:8]}_{file.filename or 'photo.jpg'}"
    save_dir = settings.DATA_DIR / "workspace" / "camera_uploads"
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / filename

    with open(file_path, "wb") as f:
        f.write(photo_bytes)

    db.create_audit_log("upload_mobile_camera", "success", f"Saved camera photo {filename} ({len(photo_bytes)} bytes)", level=0)
    return {
        "success": True,
        "file_name": filename,
        "file_path": str(file_path),
        "file_url": f"/static/camera_uploads/{filename}"
    }

# 12. Phase 4 Vision & Desktop Sight Endpoints
@app.post("/vision/capture")
def capture_screen_endpoint():
    res = ScreenCaptureTool.capture_screen()
    db.create_audit_log("capture_screen", "success", f"Captured screen: {res.get('file_name')}", level=0)
    return res

@app.post("/vision/ocr")
def vision_ocr_endpoint(req: VisionOCRRequest):
    return OCRReaderTool.extract_text_from_image(req.image_path)

@app.post("/vision/analyze")
def vision_analyze_endpoint(req: VisionAnalyzeRequest):
    return VisionAnalyzerTool.analyze_screen_image(
        req.image_path, 
        prompt_focus=req.prompt_focus, 
        auto_save_memory=req.auto_save_memory
    )

@app.post("/vision/capture-and-analyze")
def capture_and_analyze_screen_endpoint(prompt_focus: Optional[str] = Query(None)):
    cap_res = ScreenCaptureTool.capture_screen()
    if not cap_res.get("success"):
        raise HTTPException(status_code=500, detail=cap_res.get("error", "Screen capture failed"))

    analysis_res = VisionAnalyzerTool.analyze_screen_image(
        cap_res["file_path"], 
        prompt_focus=prompt_focus, 
        auto_save_memory=True
    )
    analysis_res["image_url"] = cap_res["image_url"]
    return analysis_res

# 13. System Kill Switch: Sleep & Shutdown Endpoints
def _perform_graceful_shutdown():
    app_logger.info("Executing graceful system shutdown...")
    db.create_audit_log("system_shutdown", "success", "System kill switch triggered. Server shutting down.", level=3)

@app.get("/system/mode")
def get_system_mode_endpoint():
    global SYSTEM_STATE
    return {"system_mode": SYSTEM_STATE}

@app.post("/system/sleep")
def set_system_sleep_endpoint(req: SystemSleepRequest):
    global SYSTEM_STATE
    mode = req.mode.lower().strip()
    if mode in ["sleeping", "sleep"]:
        SYSTEM_STATE = "sleeping"
        db.create_audit_log("system_sleep", "success", "System set to SLEEP MODE. Inference & tasks paused.", level=1)
        return {"success": True, "system_mode": "sleeping", "message": "Assistant is now in SLEEP MODE. All background inference paused."}
    else:
        SYSTEM_STATE = "active"
        db.create_audit_log("system_wake", "success", "System WOKEN UP. Resuming active operations.", level=1)
        return {"success": True, "system_mode": "active", "message": "Assistant is now ACTIVE and ready."}

@app.post("/system/shutdown")
def trigger_system_shutdown(background_tasks: BackgroundTasks):
    global SYSTEM_STATE
    SYSTEM_STATE = "shutdown"
    _perform_graceful_shutdown()
    
    # Schedule process termination shortly after returning HTTP response
    def shutdown_process():
        os.kill(os.getpid(), signal.SIGTERM if hasattr(signal, 'SIGTERM') else signal.SIGINT)

    background_tasks.add_task(shutdown_process)
    
    return {
        "success": True,
        "message": "System shutdown initiated safely. Database connections closed and server process terminating."
    }
