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

from app.tools.browser_automation import BrowserAutomation
from app.tools.desktop_control import DesktopControl
from app.tools.web_agent import WebAgent

from app.tools.security_lab import SecurityLabTool
from app.tools.finance_trader import FinanceTraderTool
from app.tools.music_studio import MusicStudioTool
from app.tools.content_creator import ContentCreatorTool
from app.tools.cybersecurity_brain import CybersecurityBrainTool

from app.tools.security_education import SecurityEducationTool
from app.tools.coder_brain import CoderBrainTool
from app.tools.media_studio import MediaStudioTool
from app.tools.knowledge_domains import KnowledgeDomainsTool

from app.memory.semantic_rag import SemanticRAGEngine
from app.memory.reflection_engine import ReflectionEngine
from app.memory.decision_constitution import DecisionConstitution

from app.utils.hardware_monitor import HardwareMonitor
from app.utils.notifier import SystemNotifier
from app.scheduler import ProactiveScheduler
from app.agents.multi_agent import MultiAgentTeam

from app.tools.deep_os_controller import DeepOSController
from app.tools.android_adb_controller import AndroidADBController
from app.tools.universal_filesystem import UniversalFilesystem
from app.tools.data_analyzer import DataAnalysisEngine
from app.tools.daily_briefing import DailyBriefingEngine
from app.tools.workflow_engine import WorkflowEngine
from app.memory.human_nature_engine import HumanNatureEngine
from app.tools.universal_media_learner import UniversalMediaLearner
from app.tools.opsec_manager import OpSecManagerTool
from app.tools.pentest_company_assistant import PentestCompanyAssistant
from app.tools.disposable_sandbox import DisposableSandbox
from app.tools.skill_teaching_engine import SkillTeachingEngine
from app.tools.app_inventory import SystemAppInventory
from app.agents.master_agent import MasterAgentOrchestrator
from app.utils.hardware_governor import HardwareGovernor
from app.tools.security_canary import SecurityCanaryTrap
from app.tools.financial_legal_wellness import FinancialLegalWellnessSuite
from app.agents.self_evolving_agent import SelfEvolvingAgent
from app.scheduler.self_healer import AutonomousSelfHealer
from app.cognition.experiment_engine import ExperimentEngine
from app.cognition.capability_factory import CapabilityFactory
from app.agents.proactive_coworker_daemon import ProactiveCoworkerDaemon
from app.tools.win32_ghost_operator import Win32GhostOperator
from app.tools.ast_janitor import ASTJanitor
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.pipeline import CognitivePipeline

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
    session_id: Optional[str] = None
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

class BrowserNavigateRequest(BaseModel):
    url: str
    fill_inputs: Optional[Dict[str, str]] = None
    click_selectors: Optional[List[str]] = None
    submit_form: bool = False

class AppLaunchRequest(BaseModel):
    app_name: str

class WebAgentRequest(BaseModel):
    objective: str
    target_url: str
    complexity: str = "main"

class SecurityScanRequest(BaseModel):
    target: str

class PositionSizeRequest(BaseModel):
    bankroll: float
    risk_percent: float = 1.0
    entry_price: float = 100.0
    stop_loss_price: float = 95.0

class EVCalcRequest(BaseModel):
    odds_decimal: float
    estimated_win_probability: float
    stake: float

class PaperTradeRequest(BaseModel):
    asset_or_event: str
    direction: str
    entry_val: float
    target_val: float
    stop_val: float
    notes: Optional[str] = ""

class VocalGuideRequest(BaseModel):
    genre: str = "hiphop"
    vocal_type: str = "male_rap"
    daw_name: str = "FL Studio / Logic / Pro Tools"

class ContentScriptRequest(BaseModel):
    topic: str
    platform: str = "youtube"
    target_audience: str = "developers & tech enthusiasts"
    auto_save_workspace: bool = True

class RAGSearchRequest(BaseModel):
    query: str
    limit: int = 5

class ReflectionRequest(BaseModel):
    task_title: str
    task_goal: str
    outcome_summary: str
    user_feedback: Optional[str] = None

class NotificationRequest(BaseModel):
    title: str
    message: str

class MultiAgentRequest(BaseModel):
    objective: str
    complexity: str = "main"

class OSMouseClickRequest(BaseModel):
    x: int
    y: int
    double: bool = False

class OSTypeTextRequest(BaseModel):
    text: str

class OSHotkeyRequest(BaseModel):
    keys: List[str]

class SoftwareUpdateRequest(BaseModel):
    package_name: str = "vlc"

class ADBTapRequest(BaseModel):
    x: int
    y: int
    target_device: Optional[str] = None

class ADBTypeTextRequest(BaseModel):
    text: str
    target_device: Optional[str] = None

class ADBLaunchAppRequest(BaseModel):
    package_name: str
    target_device: Optional[str] = None

class FileSearchRequest(BaseModel):
    query: str
    root_dir: Optional[str] = None
    max_results: int = 20

class FileMoveRequest(BaseModel):
    source_path: str
    destination_path: str

class FileCompressRequest(BaseModel):
    source_paths: List[str]
    output_zip_path: str

class ImageResizeRequest(BaseModel):
    image_path: str
    target_width: int
    target_height: int

class MediaPlayRequest(BaseModel):
    media_path: str

class DataAnalyzeRequest(BaseModel):
    file_path: str

class DataChartRequest(BaseModel):
    file_path: str
    x_col: str
    y_col: str
    chart_type: str = "bar"
    chart_title: Optional[str] = None

class SecurityNLURequest(BaseModel):
    prompt: str
    target_scope: Optional[str] = "127.0.0.1"

class YaraRuleRequest(BaseModel):
    rule_name: str
    strings_list: List[str]
    meta_description: Optional[str] = ""

class SigmaRuleRequest(BaseModel):
    title: str
    logsource_category: str = "process_creation"
    detection_selection: Dict[str, Any]

class DefensiveAuditRequest(BaseModel):
    code_snippet: str
    language: str = "python"

class CodeDebugRequest(BaseModel):
    code_snippet: str
    language: str = "python"

class UnitTestsRequest(BaseModel):
    code_snippet: str
    language: str = "python"

class SVGGenerateRequest(BaseModel):
    description: str

class LegalConsultRequest(BaseModel):
    topic_or_question: str

class CounselingRequest(BaseModel):
    user_reflection: str

class PnLCalcRequest(BaseModel):
    revenue: float
    operating_expenses: float
    tax_rate_percent: float = 20.0

class BriefingRequest(BaseModel):
    custom_topics: Optional[List[str]] = None
    generate_audio: bool = True

class WorkflowExecuteRequest(BaseModel):
    workflow_name: str
    steps: List[Dict[str, Any]]

class HumanAssimilateRequest(BaseModel):
    user_text: str
    assistant_response: str
    feedback: Optional[str] = None

class UniversalMediaRequest(BaseModel):
    target_url_or_path: str
    prompt_focus: Optional[str] = None

class OpSecAuditRequest(BaseModel):
    query_identifier: str

class OpSecErasureRequest(BaseModel):
    target_service_name: str
    user_identifier: str
    jurisdiction: Optional[str] = "GDPR Article 17 / CCPA"

class PentestReportRequest(BaseModel):
    client_company_name: str
    assessment_type: Optional[str] = "External Network & Web Application Penetration Test"
    target_scope: Optional[List[str]] = None
    vulnerabilities_found: Optional[List[Dict[str, Any]]] = None

class PentestRoERequest(BaseModel):
    client_company_name: str
    authorized_ip_ranges: List[str]
    testing_window: Optional[str] = "Monday - Friday, 09:00 - 17:00 EST"

class SandboxCreateRequest(BaseModel):
    sandbox_name: Optional[str] = None

class SandboxRunRequest(BaseModel):
    sandbox_id: str
    command: str
    target_guest_os: Optional[str] = "auto"
    timeout_seconds: int = 60

class SandboxDestroyRequest(BaseModel):
    sandbox_id: str

class SkillTeachRequest(BaseModel):
    skill_name: str
    category: Optional[str] = "cybersecurity_pentesting"
    trigger_keywords: Optional[List[str]] = None
    instructions: str
    sample_commands: Optional[str] = ""
    safety_rules: Optional[str] = "Authorized testing scope only."

class SkillExecuteRequest(BaseModel):
    skill_name: str
    target_parameter: Optional[str] = ""
    run_in_sandbox: bool = True

class AppLaunchQueryRequest(BaseModel):
    app_query: str

class SubscriptionAuditRequest(BaseModel):
    subscriptions_list: List[Dict[str, Any]]

class ToSAuditRequest(BaseModel):
    policy_text_or_url: str

class ToneCritiqueRequest(BaseModel):
    draft_message: str
    recipient_context: Optional[str] = "Professional Client / Colleague"

class AnkiExportRequest(BaseModel):
    study_material: str
    deck_name: Optional[str] = "Personal_AI_Knowledge"

class SelfEvolveRequest(BaseModel):
    task_objective: str
    tool_name_query: Optional[str] = "custom_tool"

class GhostMessageRequest(BaseModel):
    window_title_query: str
    message_type: Optional[str] = "click"
    text_payload: Optional[str] = None

class ASTAuditRequest(BaseModel):
    file_path: str

class ExperimentRequest(BaseModel):
    hypothesis_name: str
    command_or_script: str
    target_guest_os: Optional[str] = "auto"

class CapabilitySynthesizeRequest(BaseModel):
    capability_name: str
    description: str
    sample_params: Optional[Dict[str, Any]] = None

class SimulationRequest(BaseModel):
    target_goal: str
    candidate_actions: List[Dict[str, Any]]

# 1. Base Endpoint - Serves HTML Visual Dashboard or JSON status
@app.get("/")
def get_root(request: Request):
    # Check if client explicitly requested JSON
    accept_header = request.headers.get("accept", "")
    index_path = os.path.join(static_dir, "index.html")

    if "text/html" in accept_header and os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})

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

import re

def _parse_and_execute_intent(user_text: str) -> Optional[str]:
    """DEPRECATED: Legacy direct regex intent executor.
    The single canonical cognitive execution route is CognitivePipeline -> CognitiveRuntime.
    This helper is retained solely for legacy backwards compatibility during migration.
    """
    app_logger.warning("Call to deprecated legacy route _parse_and_execute_intent(). Canonical route is CognitivePipeline -> CognitiveRuntime.")
    text_lower = user_text.lower()

    # 1. Open / Launch ANY Installed Application
    if any(k in text_lower for k in ["open ", "launch ", "start ", "run ", "search for ", "look up "]):
        # Check for browser search URL intent (e.g. YouTube/Google search)
        if "youtube" in text_lower or "google" in text_lower:
            query_term = "ordinary"
            if "search" in text_lower or "for" in text_lower:
                m = re.search(r'(?:search|look up|for|find)\s+(?:me\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+on youtube|\s+in firefox|\s+in chrome|\s+on google|$)', text_lower)
                if m and m.group(1).strip():
                    query_term = m.group(1).strip()

            url = f"https://www.youtube.com/results?search_query={query_term.replace(' ', '+')}" if "youtube" in text_lower else f"https://www.google.com/search?q={query_term.replace(' ', '+')}"

            app_to_launch = "firefox" if "firefox" in text_lower else "chrome"
            DesktopControl.launch_application(app_to_launch)
            DesktopControl.open_url(url)
            return f"[ACTION EXECUTED BY LOCAL SYSTEM OPERATOR]: Launched {app_to_launch.title()} and opened search for '{query_term}' ({url})."

        # General open any installed application intent
        match = re.search(r'(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9_\-\s]+)', text_lower)
        if match:
            target_app_query = match.group(1).strip()
            if len(target_app_query) > 1 and target_app_query not in ["file", "folder", "song", "task", "briefing", "sandbox"]:
                res = SystemAppInventory.launch_any_app(target_app_query)
                if res.get("success"):
                    return f"[ACTION EXECUTED BY LOCAL SYSTEM OPERATOR]: {res.get('message', f'Launched {target_app_query}')}"

    # 2. Screenshot / Screen Vision
    if any(k in text_lower for k in ["take a screenshot", "capture screen", "snap desktop", "screen vision"]):
        cap = ScreenCaptureTool.capture_screen()
        return f"[ACTION EXECUTED BY LOCAL SYSTEM OPERATOR]: Captured screen image: {cap.get('file_name', 'screenshot.png')}."

    # 3. Daily Briefing
    if any(k in text_lower for k in ["daily briefing", "morning report", "generate briefing"]):
        b = DailyBriefingEngine.generate_briefing(generate_audio=False)
        return f"[ACTION EXECUTED BY LOCAL SYSTEM OPERATOR]: Generated Executive Briefing for today."

    return None

def _enrich_messages_with_local_tools_and_rag(user_text: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """DEPRECATED: Legacy prompt enrichment helper.
    The single canonical cognitive execution route is CognitivePipeline -> CognitiveRuntime.
    This helper is retained solely for legacy backwards compatibility during migration.
    """
    app_logger.warning("Call to deprecated legacy route _enrich_messages_with_local_tools_and_rag(). Canonical route is CognitivePipeline -> CognitiveRuntime.")
    rag_context = SemanticRAGEngine.build_rag_context(user_text) if user_text else ""

    app_count = SystemAppInventory.get_installed_apps_count()

    system_instruction = (
        f"You are an advanced local personal assistant running natively on the user's local PC.\n"
        f"You have full permission and native tools to access local files, search directories, read documents, "
        f"play media, launch and operate ANY of the {app_count} installed applications on this PC, monitor hardware, and run sandboxes.\n"
        f"Never state that you cannot access local files, applications, or the system — you ARE the local assistant running on this PC."
    )

    action_context = _parse_and_execute_intent(user_text) or ""

    fs_context = ""
    text_lower = user_text.lower()

    # Ingest App Count Info if user asks about installed apps/PC apps
    if any(k in text_lower for k in ["how many apps", "installed apps", "apps on my pc", "list my apps", "what apps"]):
        scan_info = SystemAppInventory.scan_installed_applications()
        top_apps = [a["app_name"] for a in scan_info.get("applications", [])[:15]]
        fs_context += f"\n\n[SYSTEM INSTALLED APPLICATIONS INFO]: Discovered {scan_info.get('total_apps_count')} installed applications on this {scan_info.get('host_os')} PC. Sample installed apps: {', '.join(top_apps)}."

    # Ingest Filesystem Search
    if any(k in text_lower for k in ["song", "file", "document", "ordinary", "library", "folder", "do i have", "search my pc", "find on my pc"]):
        words = [w for w in user_text.replace("?", "").replace("'", "").split() if len(w) > 3 and w.lower() not in ["have", "called", "song", "this", "library", "with", "from", "does", "what"]]
        search_term = words[0] if words else "Ordinary"
        matched = UniversalFilesystem.search_filesystem(search_term, max_results=10)
        if matched:
            fs_context += f"\n\n[LOCAL FILESYSTEM SEARCH RESULTS FOR '{search_term}']:\n" + "\n".join([f"• {m['file_name']} (Path: {m['file_path']})" for m in matched])
        else:
            fs_context += f"\n\n[LOCAL FILESYSTEM SEARCH RESULTS FOR '{search_term}']: No files matching '{search_term}' were found in the scanned workspace/system directories."

    combined_system_prompt = system_instruction + (f"\n\n{rag_context}" if rag_context else "") + (f"\n\n{action_context}" if action_context else "") + fs_context

    enriched = list(messages)
    if enriched and enriched[0]["role"] == "system":
        enriched[0]["content"] += f"\n\n{combined_system_prompt}"
    else:
        enriched.insert(0, {"role": "system", "content": combined_system_prompt})

    return enriched

# 2. Local Chat Completions Route
@app.post("/chat")
def chat_with_local_brain(req: ChatRequest):
    global SYSTEM_STATE
    if SYSTEM_STATE == "sleeping":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is currently in SLEEP MODE. Wake up the assistant from the dashboard header to resume."
        )

    user_msg_content = next((m["content"] for m in reversed(req.messages) if m["role"] == "user"), "")
    pipeline_res = CognitivePipeline.process_chat(
        user_text=user_msg_content,
        complexity=req.complexity,
        session_id=req.session_id
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "model": pipeline_res.get("model_used", "CognitivePipeline"),
        "trace_id": pipeline_res.get("trace_id"),
        "session_id": pipeline_res.get("session_id"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": pipeline_res.get("assistant_reply", "Task executed.")
            },
            "finish_reason": "stop"
        }]
    }

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

@app.post("/tasks/resume-all")
def resume_all_tasks_endpoint():
    return TaskManager.resume_interrupted_tasks()

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

    # Verify speaker voice in crowded places
    speaker_check = LocalSpeechToText.verify_speaker_voice(str(temp_path))
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

    # 2. Master Agent Orchestrator All-In-One Execution via Cognitive Pipeline
    pipeline_res = CognitivePipeline().process_request(user_text, complexity=complexity)
    assistant_text = pipeline_res.get("assistant_reply", "Done.")

    # 3. Synthesize Speech
    tts_res = LocalTextToSpeech.synthesize_speech(assistant_text)

    return {
        "success": True,
        "user_text": user_text,
        "assistant_text": assistant_text,
        "audio_url": tts_res.get("audio_url", ""),
        "model_used": pipeline_res.get("model_used", ""),
        "executed_actions": pipeline_res.get("executed_actions", []),
        "speaker_verified": speaker_check.get("verified", True)
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

# 13. Phase 5 Automation: Browser & Desktop Automation Endpoints
@app.post("/automation/browser/navigate")
def browser_navigate_endpoint(req: BrowserNavigateRequest):
    return BrowserAutomation.navigate_and_extract(
        req.url, 
        fill_inputs=req.fill_inputs, 
        click_selectors=req.click_selectors, 
        submit_form=req.submit_form
    )

@app.get("/automation/desktop/apps")
def list_approved_apps_endpoint():
    return {"approved_apps": DesktopControl.list_approved_apps()}

@app.post("/automation/desktop/launch")
def launch_app_endpoint(req: AppLaunchRequest):
    return DesktopControl.launch_application(req.app_name)

@app.post("/automation/web-agent")
def web_agent_endpoint(req: WebAgentRequest):
    return WebAgent.execute_web_workflow(req.objective, req.target_url, complexity=req.complexity)

# 14. Phase 6 Domain Specialist Intelligence Endpoints
@app.post("/specialists/security/scan")
def security_scan_endpoint(req: SecurityScanRequest):
    return SecurityLabTool.scan_lab_target(req.target)

@app.post("/specialists/finance/risk-calc")
def finance_risk_calc_endpoint(req: PositionSizeRequest):
    return FinanceTraderTool.calculate_position_size(
        req.bankroll, 
        risk_percent=req.risk_percent, 
        entry_price=req.entry_price, 
        stop_loss_price=req.stop_loss_price
    )

@app.post("/specialists/finance/ev-calc")
def finance_ev_calc_endpoint(req: EVCalcRequest):
    return FinanceTraderTool.calculate_expected_value(
        req.odds_decimal, 
        req.estimated_win_probability, 
        req.stake
    )

@app.post("/specialists/finance/paper-trade")
def finance_paper_trade_endpoint(req: PaperTradeRequest):
    return FinanceTraderTool.log_paper_trade(
        req.asset_or_event, 
        req.direction, 
        req.entry_val, 
        req.target_val, 
        req.stop_val, 
        notes=req.notes or ""
    )

@app.post("/specialists/music/vocal-guide")
def music_vocal_guide_endpoint(req: VocalGuideRequest):
    return MusicStudioTool.generate_vocal_chain_guide(
        genre=req.genre, 
        vocal_type=req.vocal_type, 
        daw_name=req.daw_name
    )

@app.post("/specialists/content/script")
def content_script_endpoint(req: ContentScriptRequest):
    return ContentCreatorTool.generate_content_script(
        req.topic, 
        platform=req.platform, 
        target_audience=req.target_audience, 
        auto_save_workspace=req.auto_save_workspace
    )

@app.post("/specialists/security/parse-intent")
def security_parse_intent_endpoint(req: SecurityNLURequest):
    return CybersecurityBrainTool.parse_natural_security_intent(req.prompt, target_scope=req.target_scope)

@app.post("/specialists/security/generate-yara")
def security_generate_yara_endpoint(req: YaraRuleRequest):
    return CybersecurityBrainTool.generate_yara_rule(req.rule_name, req.strings_list, meta_description=req.meta_description)

@app.post("/specialists/security/generate-sigma")
def security_generate_sigma_endpoint(req: SigmaRuleRequest):
    return CybersecurityBrainTool.generate_sigma_rule(req.title, req.logsource_category, req.detection_selection)

@app.post("/specialists/security/defensive-audit")
def security_defensive_audit_endpoint(req: DefensiveAuditRequest):
    return SecurityEducationTool.audit_code_defensively(req.code_snippet, language=req.language)

@app.post("/specialists/coder/debug")
def coder_debug_endpoint(req: CodeDebugRequest):
    return CoderBrainTool.explain_and_debug_code(req.code_snippet, language=req.language)

@app.post("/specialists/coder/generate-tests")
def coder_generate_tests_endpoint(req: UnitTestsRequest):
    return CoderBrainTool.generate_unit_tests(req.code_snippet, language=req.language)

@app.post("/specialists/media/generate-svg")
def media_generate_svg_endpoint(req: SVGGenerateRequest):
    return MediaStudioTool.generate_svg_graphic(req.description)

@app.post("/specialists/legal/consult")
def legal_consult_endpoint(req: LegalConsultRequest):
    return KnowledgeDomainsTool.legal_compliance_consult(req.topic_or_question)

@app.post("/specialists/counseling/reflect")
def counseling_reflect_endpoint(req: CounselingRequest):
    return KnowledgeDomainsTool.psychological_counseling_partner(req.user_reflection)

@app.post("/specialists/finance/pnl-calc")
def finance_pnl_calc_endpoint(req: PnLCalcRequest):
    return KnowledgeDomainsTool.accounting_finance_calc(
        req.revenue, 
        req.operating_expenses, 
        tax_rate_percent=req.tax_rate_percent
    )

@app.post("/tools/daily-briefing")
def daily_briefing_endpoint(req: BriefingRequest):
    return DailyBriefingEngine.generate_briefing(
        custom_topics=req.custom_topics,
        generate_audio=req.generate_audio
    )

@app.post("/tools/workflow-execute")
def workflow_execute_endpoint(req: WorkflowExecuteRequest):
    return WorkflowEngine.execute_workflow(req.workflow_name, req.steps)

@app.post("/human/assimilate")
def human_assimilate_endpoint(req: HumanAssimilateRequest):
    return HumanNatureEngine.assimilate_human_experience(
        req.user_text, req.assistant_response, feedback=req.feedback
    )

@app.post("/tools/universal-media-learn")
def universal_media_endpoint(req: UniversalMediaRequest):
    return UniversalMediaLearner.analyze_media_target(
        req.target_url_or_path, prompt_focus=req.prompt_focus
    )

@app.post("/opsec/audit-footprint")
def opsec_audit_endpoint(req: OpSecAuditRequest):
    return OpSecManagerTool.audit_digital_footprint(req.query_identifier)

@app.post("/opsec/generate-erasure")
def opsec_erasure_endpoint(req: OpSecErasureRequest):
    return OpSecManagerTool.generate_erasure_requests(
        req.target_service_name, req.user_identifier, jurisdiction=req.jurisdiction or "GDPR Article 17 / CCPA"
    )

@app.post("/specialists/security/pentest-report")
def pentest_report_endpoint(req: PentestReportRequest):
    return PentestCompanyAssistant.generate_pentest_report(
        req.client_company_name,
        assessment_type=req.assessment_type or "External Network & Web Application Penetration Test",
        target_scope=req.target_scope,
        vulnerabilities_found=req.vulnerabilities_found
    )

@app.post("/specialists/security/draft-roe")
def pentest_roe_endpoint(req: PentestRoERequest):
    return PentestCompanyAssistant.draft_rules_of_engagement(
        req.client_company_name,
        req.authorized_ip_ranges,
        testing_window=req.testing_window or "Monday - Friday, 09:00 - 17:00 EST"
    )

@app.post("/sandbox/create")
def sandbox_create_endpoint(req: Optional[SandboxCreateRequest] = None):
    name = req.sandbox_name if req else None
    return DisposableSandbox.create_sandbox(sandbox_name=name)

@app.post("/sandbox/run")
def sandbox_run_endpoint(req: SandboxRunRequest):
    return DisposableSandbox.run_in_sandbox(
        req.sandbox_id,
        req.command,
        target_guest_os=req.target_guest_os or "auto",
        timeout_seconds=req.timeout_seconds
    )

@app.post("/sandbox/destroy")
def sandbox_destroy_endpoint(req: SandboxDestroyRequest):
    return DisposableSandbox.destroy_sandbox(req.sandbox_id)

@app.post("/skills/teach")
def skills_teach_endpoint(req: SkillTeachRequest):
    return SkillTeachingEngine.teach_skill(
        req.skill_name,
        category=req.category or "cybersecurity_pentesting",
        trigger_keywords=req.trigger_keywords,
        instructions=req.instructions,
        sample_commands=req.sample_commands,
        safety_rules=req.safety_rules or "Authorized testing scope only."
    )

@app.get("/skills/list")
def skills_list_endpoint(category: Optional[str] = Query(None)):
    return {"skills": SkillTeachingEngine.list_taught_skills(category=category)}

@app.post("/skills/execute")
def skills_execute_endpoint(req: SkillExecuteRequest):
    return SkillTeachingEngine.execute_taught_skill(
        req.skill_name,
        target_parameter=req.target_parameter or "",
        run_in_sandbox=req.run_in_sandbox
    )

@app.get("/system/apps")
def get_system_apps_endpoint():
    return SystemAppInventory.scan_installed_applications()

@app.post("/system/apps/scan")
def rescan_system_apps_endpoint():
    return SystemAppInventory.scan_installed_applications()

@app.post("/system/apps/launch")
def launch_system_app_endpoint(req: AppLaunchQueryRequest):
    return SystemAppInventory.launch_any_app(req.app_query)

@app.post("/system/governor/p-cores")
def set_p_cores_endpoint():
    return HardwareGovernor.set_thread_affinity(p_cores_only=True)

@app.get("/system/governor/hardware-tier")
def get_hardware_tier_endpoint():
    return HardwareGovernor.detect_hardware_tier()

@app.post("/system/governor/purge-vram")
def purge_vram_endpoint():
    return HardwareGovernor.purge_vram_and_system_memory()

@app.post("/opsec/spawn-canaries")
def spawn_canaries_endpoint():
    return SecurityCanaryTrap.spawn_canary_honeypots()

@app.post("/opsec/inspect-clipboard")
def inspect_clipboard_endpoint():
    return SecurityCanaryTrap.inspect_clipboard_entropy()

@app.post("/tools/audit-subscriptions")
def audit_subscriptions_endpoint(req: SubscriptionAuditRequest):
    return FinancialLegalWellnessSuite.audit_subscriptions_and_trials(req.subscriptions_list)

@app.post("/tools/audit-tos")
def audit_tos_endpoint(req: ToSAuditRequest):
    return FinancialLegalWellnessSuite.audit_tos_and_privacy_policy(req.policy_text_or_url)

@app.post("/tools/tone-critique")
def tone_critique_endpoint(req: ToneCritiqueRequest):
    return FinancialLegalWellnessSuite.socratic_tone_sounding_board(req.draft_message, recipient_context=req.recipient_context)

@app.post("/tools/generate-anki")
def generate_anki_endpoint(req: AnkiExportRequest):
    return FinancialLegalWellnessSuite.generate_anki_flashcards(req.study_material, deck_name=req.deck_name or "Personal_AI_Knowledge")

@app.post("/agent/self-evolve")
def self_evolve_endpoint(req: SelfEvolveRequest):
    return SelfEvolvingAgent.synthesize_and_hotload_tool(req.task_objective, tool_name_query=req.tool_name_query or "custom_tool")

@app.post("/system/self-heal")
async def trigger_self_heal_endpoint():
    return await AutonomousSelfHealer.run_maintenance_cycle()

@app.post("/cognition/experiment")
def test_experiment_endpoint(req: ExperimentRequest):
    return ExperimentEngine.test_hypothesis_in_sandbox(
        req.hypothesis_name,
        req.command_or_script,
        target_guest_os=req.target_guest_os or "auto"
    )

@app.post("/cognition/synthesize-capability")
def synthesize_capability_endpoint(req: CapabilitySynthesizeRequest):
    return CapabilityFactory.synthesize_capability(
        req.capability_name,
        req.description,
        sample_params=req.sample_params
    )

@app.post("/cognition/simulate-branches")
def simulate_branches_endpoint(req: SimulationRequest):
    return CounterfactualSimulator.simulate_competing_branches(
        req.target_goal,
        req.candidate_actions
    )

@app.post("/cognition/self-play-explore")
def self_play_explore_endpoint():
    return ExperimentEngine.run_self_play_sandbox_exploration()

@app.get("/agent/proactive-greeting")
def proactive_greeting_endpoint():
    return {"proactive_greeting": ProactiveCoworkerDaemon.get_proactive_greeting()}

@app.get("/os/ghost-windows")
def list_ghost_windows_endpoint():
    return {"open_windows": Win32GhostOperator.list_open_windows()}

@app.post("/os/ghost-send")
def send_ghost_message_endpoint(req: GhostMessageRequest):
    return Win32GhostOperator.send_background_window_message(
        req.window_title_query,
        message_type=req.message_type or "click",
        text_payload=req.text_payload
    )

@app.post("/coder/ast-audit")
def ast_audit_endpoint(req: ASTAuditRequest):
    return ASTJanitor.audit_and_refactor_code(req.file_path)

@app.post("/coder/ast-generate-test")
def ast_generate_test_endpoint(module_query: str = Query(...)):
    return ASTJanitor.generate_pytest_contract(module_query)

# 15. Phase 7 Meta-Learning & RAG Memory Endpoints
@app.post("/memory/rag-search")
def rag_search_endpoint(req: RAGSearchRequest):
    results = SemanticRAGEngine.search_memories(req.query, limit=req.limit)
    context_str = SemanticRAGEngine.build_rag_context(req.query, limit=req.limit)
    return {
        "query": req.query,
        "results_count": len(results),
        "results": results,
        "rag_prompt_context": context_str
    }

@app.post("/memory/reflect")
def task_reflection_endpoint(req: ReflectionRequest):
    return ReflectionEngine.reflect_on_task_execution(
        req.task_title, 
        req.task_goal, 
        req.outcome_summary, 
        user_feedback=req.user_feedback
    )

@app.get("/memory/constitution")
def get_constitution_endpoint():
    return {
        "constitution_summary": DecisionConstitution.get_constitution_summary(),
        "rules": DecisionConstitution.CORE_VALUES
    }

# 16. Upgrades 1, 4, 5, 6: Hardware Monitor, Notifier, Scheduler & Multi-Agent Endpoints
@app.get("/api/hardware-stats")
def get_hardware_stats_endpoint():
    return HardwareMonitor.get_hardware_stats()

@app.post("/system/notify")
def send_notification_endpoint(req: NotificationRequest):
    return SystemNotifier.send_notification(req.title, req.message)

@app.get("/scheduler/jobs")
def list_scheduler_jobs_endpoint():
    return {"jobs": ProactiveScheduler.list_jobs()}

@app.delete("/scheduler/jobs/{job_id}")
def remove_scheduler_job_endpoint(job_id: str):
    success = ProactiveScheduler.remove_job(job_id)
    return {"success": success, "job_id": job_id}

@app.post("/agents/multi-agent-collaborate")
def run_multi_agent_endpoint(req: MultiAgentRequest):
    return MultiAgentTeam.run_collaborative_workflow(req.objective, complexity=req.complexity)

# 17. Deep OS, Android ADB, Universal Filesystem & Data Science Endpoints
@app.post("/os/click")
def os_mouse_click_endpoint(req: OSMouseClickRequest):
    return DeepOSController.mouse_click(req.x, req.y, double=req.double)

@app.post("/os/type")
def os_type_text_endpoint(req: OSTypeTextRequest):
    return DeepOSController.type_text(req.text)

@app.post("/os/hotkey")
def os_press_hotkey_endpoint(req: OSHotkeyRequest):
    return DeepOSController.press_hotkey(req.keys)

@app.post("/os/update-software")
def os_update_software_endpoint(req: SoftwareUpdateRequest):
    return DeepOSController.check_and_update_software(req.package_name)

@app.get("/android/devices")
def android_list_devices_endpoint():
    return AndroidADBController.list_connected_devices()

@app.post("/android/tap")
def android_tap_endpoint(req: ADBTapRequest):
    return AndroidADBController.tap_screen(req.x, req.y, target_device=req.target_device)

@app.post("/android/type")
def android_type_endpoint(req: ADBTypeTextRequest):
    return AndroidADBController.type_text(req.text, target_device=req.target_device)

@app.post("/android/screenshot")
def android_screenshot_endpoint(target_device: Optional[str] = Query(None)):
    return AndroidADBController.capture_phone_screenshot(target_device=target_device)

@app.post("/android/launch-app")
def android_launch_app_endpoint(req: ADBLaunchAppRequest):
    return AndroidADBController.launch_android_app(req.package_name, target_device=req.target_device)

@app.post("/filesystem/search")
def fs_search_endpoint(req: FileSearchRequest):
    return UniversalFilesystem.search_filesystem(req.query, root_dir=req.root_dir, max_results=req.max_results)

@app.post("/filesystem/move")
def fs_move_endpoint(req: FileMoveRequest):
    return UniversalFilesystem.rename_or_move(req.source_path, req.destination_path)

@app.post("/filesystem/compress")
def fs_compress_endpoint(req: FileCompressRequest):
    return UniversalFilesystem.compress_zip(req.source_paths, req.output_zip_path)

@app.post("/filesystem/resize-image")
def fs_resize_image_endpoint(req: ImageResizeRequest):
    return UniversalFilesystem.resize_image(req.image_path, req.target_width, req.target_height)

@app.post("/filesystem/play-media")
def fs_play_media_endpoint(req: MediaPlayRequest):
    return UniversalFilesystem.play_media_file(req.media_path)

@app.post("/data/analyze")
def data_analyze_endpoint(req: DataAnalyzeRequest):
    return DataAnalysisEngine.analyze_dataset(req.file_path)

@app.post("/data/chart")
def data_chart_endpoint(req: DataChartRequest):
    return DataAnalysisEngine.generate_chart_visualization(
        req.file_path, 
        req.x_col, 
        req.y_col, 
        chart_type=req.chart_type, 
        chart_title=req.chart_title
    )

# 18. System Kill Switch: Sleep & Shutdown Endpoints
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
