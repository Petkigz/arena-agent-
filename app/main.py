from fastapi import FastAPI, HTTPException, Query, status, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
import httpx
import os

from app.config import settings
from app.database import db
from app.tasks import TaskManager, TaskCreate, TaskUpdate, Task
from app.llm import llm_client
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

from app.tools.youtube_learner import YouTubeLearner
from app.tools.web_research import WebResearcher
from app.tools.doc_reader import DocumentReader
from app.tools.knowledge_indexer import KnowledgeIndexer

app = FastAPI(
    title=settings.APP_NAME,
    description="Version 0 Core Engine & Visual Dashboard for the Local Personal Assistant",
    version="0.1.0"
)

# Mount static files directory if it exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
        "app_name": settings.APP_NAME,
        "version": "0.1.0",
        "local_llm_status": lm_status,
        "lm_studio_endpoint": settings.LM_STUDIO_URL,
        "database_connected": True
    }

# 2. Local Chat Completions Route
@app.post("/chat")
def chat_with_local_brain(req: ChatRequest):
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

# 9. Phase 2 Tools: Web Scraper, YouTube Learner & Document Reader Endpoints
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
    return DocumentReader.list_approved_documents()

@app.post("/tools/read-doc")
def read_doc_endpoint(req: DocReadRequest):
    result = DocumentReader.read_document(req.file_path)
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
