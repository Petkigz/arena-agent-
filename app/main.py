from fastapi import FastAPI, APIRouter, HTTPException, Query, status, Request, UploadFile, File, BackgroundTasks, Depends
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
from app.llm import llm_client, require_real_completion
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

from app.tools.manifest import _LazyImportProxy
YouTubeLearner = _LazyImportProxy("app.tools.youtube_learner", "YouTubeLearner")
WebResearcher = _LazyImportProxy("app.tools.web_research", "WebResearcher")
DocumentReader = _LazyImportProxy("app.tools.doc_reader", "DocumentReader")
DocumentManager = _LazyImportProxy("app.tools.doc_manager", "DocumentManager")
KnowledgeIndexer = _LazyImportProxy("app.tools.knowledge_indexer", "KnowledgeIndexer")

LocalSpeechToText = _LazyImportProxy("app.perception.speech_to_text", "LocalSpeechToText")
LocalTextToSpeech = _LazyImportProxy("app.perception.text_to_speech", "LocalTextToSpeech")

ScreenCaptureTool = _LazyImportProxy("app.tools.screen_capture", "ScreenCaptureTool")
OCRReaderTool = _LazyImportProxy("app.tools.ocr_reader", "OCRReaderTool")
VisionAnalyzerTool = _LazyImportProxy("app.tools.vision_analyzer", "VisionAnalyzerTool")

BrowserAutomation = _LazyImportProxy("app.tools.browser_automation", "BrowserAutomation")
DesktopControl = _LazyImportProxy("app.tools.desktop_control", "DesktopControl")
WebAgent = _LazyImportProxy("app.tools.web_agent", "WebAgent")

SecurityLabTool = _LazyImportProxy("app.tools.security_lab", "SecurityLabTool")
FinanceTraderTool = _LazyImportProxy("app.tools.finance_trader", "FinanceTraderTool")
MusicStudioTool = _LazyImportProxy("app.tools.music_studio", "MusicStudioTool")
ContentCreatorTool = _LazyImportProxy("app.tools.content_creator", "ContentCreatorTool")
CybersecurityBrainTool = _LazyImportProxy("app.tools.cybersecurity_brain", "CybersecurityBrainTool")

SecurityEducationTool = _LazyImportProxy("app.tools.security_education", "SecurityEducationTool")
CoderBrainTool = _LazyImportProxy("app.tools.coder_brain", "CoderBrainTool")
MediaStudioTool = _LazyImportProxy("app.tools.media_studio", "MediaStudioTool")
KnowledgeDomainsTool = _LazyImportProxy("app.tools.knowledge_domains", "KnowledgeDomainsTool")

from app.memory.semantic_rag import SemanticRAGEngine
from app.memory.reflection_engine import ReflectionEngine
from app.memory.decision_constitution import DecisionConstitution

from app.utils.hardware_monitor import HardwareMonitor
from app.utils.notifier import SystemNotifier
from app.scheduler import ProactiveScheduler
MultiAgentTeam = _LazyImportProxy("app.agents.multi_agent", "MultiAgentTeam")

DeepOSController = _LazyImportProxy("app.tools.deep_os_controller", "DeepOSController")
AndroidADBController = _LazyImportProxy("app.tools.android_adb_controller", "AndroidADBController")
UniversalFilesystem = _LazyImportProxy("app.tools.universal_filesystem", "UniversalFilesystem")
DataAnalysisEngine = _LazyImportProxy("app.tools.data_analyzer", "DataAnalysisEngine")
DailyBriefingEngine = _LazyImportProxy("app.tools.daily_briefing", "DailyBriefingEngine")
WorkflowEngine = _LazyImportProxy("app.tools.workflow_engine", "WorkflowEngine")
from app.memory.human_nature_engine import HumanNatureEngine
UniversalMediaLearner = _LazyImportProxy("app.tools.universal_media_learner", "UniversalMediaLearner")
OpSecManagerTool = _LazyImportProxy("app.tools.opsec_manager", "OpSecManagerTool")
PentestCompanyAssistant = _LazyImportProxy("app.tools.pentest_company_assistant", "PentestCompanyAssistant")
DisposableSandbox = _LazyImportProxy("app.tools.disposable_sandbox", "DisposableSandbox")
SkillTeachingEngine = _LazyImportProxy("app.tools.skill_teaching_engine", "SkillTeachingEngine")
SystemAppInventory = _LazyImportProxy("app.tools.app_inventory", "SystemAppInventory")
MasterAgentOrchestrator = _LazyImportProxy("app.agents.master_agent", "MasterAgentOrchestrator")
from app.utils.hardware_governor import HardwareGovernor
SecurityCanaryTrap = _LazyImportProxy("app.tools.security_canary", "SecurityCanaryTrap")
FinancialLegalWellnessSuite = _LazyImportProxy("app.tools.financial_legal_wellness", "FinancialLegalWellnessSuite")
SelfEvolvingAgent = _LazyImportProxy("app.agents.self_evolving_agent", "SelfEvolvingAgent")
from app.scheduler.self_healer import AutonomousSelfHealer
ExperimentEngine = _LazyImportProxy("app.cognition.experiment_engine", "ExperimentEngine")
from app.cognition.capability_factory import CapabilityFactory
ProactiveCoworkerDaemon = _LazyImportProxy("app.agents.proactive_coworker_daemon", "ProactiveCoworkerDaemon")
Win32GhostOperator = _LazyImportProxy("app.tools.win32_ghost_operator", "Win32GhostOperator")
ASTJanitor = _LazyImportProxy("app.tools.ast_janitor", "ASTJanitor")
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.pipeline import CognitivePipeline
from app.cognition.world_model import WorldModel
from app.settings_store import get_settings, update_settings
from app.cognition.owner_control import ControlMode, authorization_store, owner_control_store

# The 127 core REST routes are registered on a router so the unified server
# (app/server.py) can include them alongside the WebSocket/API/SPA routes.
# A backward-compatible `app` is built at the bottom of this module.
router = APIRouter()

# Global System State
SYSTEM_STATE = "active"  # "active" or "sleeping"

# Mount static files directory if it exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    router.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount audio static directory
audio_dir = settings.DATA_DIR / "audio"
audio_dir.mkdir(parents=True, exist_ok=True)
router.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

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

class InferenceProfileUpdate(BaseModel):
    """Owner inference profile update. All fields optional; validated by the store."""
    main_model: Optional[str] = None
    fast_model: Optional[str] = None
    provider_url: Optional[str] = None
    context_window_tokens: Optional[int] = Field(None, ge=512, le=32768)

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
    voice: Optional[str] = None

class VoiceProfileSelectRequest(BaseModel):
    profile_name: str

class MobileLocationRequest(BaseModel):
    latitude: float
    longitude: float
    city: Optional[str] = None

class SystemSleepRequest(BaseModel):
    mode: str = Field(..., description="'sleeping' or 'active'")

class OwnerControlUpdate(BaseModel):
    mode: Optional[ControlMode] = None
    paused: Optional[bool] = None
    max_autonomous_level: Optional[int] = Field(default=None, ge=0, le=3)
    allow_sensitive_autonomy: Optional[bool] = None
    require_approval_actions: Optional[List[str]] = None
    blocked_actions: Optional[List[str]] = None
    custom_autonomous_actions: Optional[List[str]] = None

class OwnerPauseRequest(BaseModel):
    paused: bool

class ApprovalDecisionRequest(BaseModel):
    approved: bool
    note: str = ""
    ttl_seconds: int = Field(default=300, ge=1, le=3600)

class ExplorationBudgetRequest(BaseModel):
    max_exploration_goals: int = Field(ge=0, le=10)








class AuthorizationIssueRequest(BaseModel):
    action_type: str = Field(min_length=1)
    payload: Dict[str, Any]
    ttl_seconds: int = Field(default=300, ge=1, le=3600)
    max_uses: int = Field(default=1, ge=1, le=100)
    plan_id: Optional[str] = None
    override_owner_policy: bool = False


class AuthorizedExecutionRequest(BaseModel):
    authorization_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    payload: Dict[str, Any]
    user_text: str = "Owner-authorized action"
    complexity: str = "fast"
    plan_id: Optional[str] = None

class PlanEditRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    steps: List[Dict[str, Any]] = Field(min_length=1, max_length=100)

class PlanDecisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    approved: bool
    note: str = ""

class PlanRevokeRequest(BaseModel):
    note: str = ""

class VisionOCRRequest(BaseModel):
    image_path: str

class VisionAnalyzeRequest(BaseModel):
    image_path: str
    prompt_focus: Optional[str] = None
    auto_save_memory: bool = True










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
@router.get("/")
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

@router.get("/api/status")
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
    """
    Canonical Cognitive Route Delegation.
    Delegates 100% to CognitivePipeline -> CognitiveRuntime, ensuring a single unified cognitive authority.
    """
    res = CognitivePipeline.process_request(user_text, complexity="fast")
    if res.get("executed_actions"):
        return f"[ACTION EXECUTED BY COGNITIVE RUNTIME]: " + "; ".join(res["executed_actions"])
    return None

def _enrich_messages_with_local_tools_and_rag(user_text: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Canonical Cognitive Route Delegation.
    Delegates 100% to CognitivePipeline -> CognitiveRuntime, ensuring a single unified cognitive authority.
    """
    res = CognitivePipeline.process_request(user_text, complexity="fast")
    enriched = list(messages)
    reply = res.get("assistant_reply", "")
    if enriched and enriched[0]["role"] == "system":
        enriched[0]["content"] += f"\n\n[COGNITIVE RUNTIME CONTEXT]: {reply}"
    else:
        enriched.insert(0, {"role": "system", "content": f"[COGNITIVE RUNTIME CONTEXT]: {reply}"})
    return enriched

# 2. Local Chat Completions Route
@router.post("/chat")
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
@router.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_persistent_task(task_in: TaskCreate):
    try:
        return TaskManager.create_task(task_in)
    except Exception as e:
        app_logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks", response_model=List[Task])
def list_tasks(status: Optional[str] = Query(None, description="Filter tasks by status")):
    return TaskManager.get_all_tasks(status=status)

@router.get("/tasks/{task_id}", response_model=Task)
def get_single_task(task_id: str):
    task = TaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.patch("/tasks/{task_id}", response_model=Task)
def update_existing_task(task_id: str, updates: TaskUpdate):
    task = TaskManager.update_task(task_id, updates)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or update failed")
    return task

@router.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK)
def delete_task_by_id(task_id: str):
    if not TaskManager.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found or deletion failed")
    return {"message": f"Task {task_id} deleted successfully."}

@router.post("/tasks/{task_id}/acquire-skill")
def acquire_skill_for_task_endpoint(task_id: str):
    res = TaskManager.acquire_skill_for_task(task_id)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error", "Task not found"))
    return res

@router.post("/tasks/resume-all")
def resume_all_tasks_endpoint():
    return TaskManager.resume_interrupted_tasks()

# 4. Audit Log Endpoint
@router.get("/audit-logs")
def view_audit_logs(limit: int = Query(50, ge=1, le=500)):
    return db.get_audit_logs(limit=limit)

# 5. Memories Endpoints
@router.post("/memories", status_code=status.HTTP_201_CREATED)
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

@router.get("/memories")
def list_memories(category: Optional[str] = Query(None, description="Filter memories by category")):
    """Backward-compatible unpaged memory list."""
    return db.get_memories(category=category)


@router.get("/memories/page")
def list_memories_page(
    category: Optional[str] = Query(None, description="Filter memories by category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return a bounded stable page for large Pansophy collections."""
    memories = db.get_memories(category=category, limit=limit, offset=offset)
    total = db.count_memories(category=category)
    return {
        "memories": memories,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(memories) < total,
        "next_offset": offset + len(memories)
        if offset + len(memories) < total else None,
    }


@router.get("/knowledge/graph")
def get_knowledge_graph(limit: int = Query(500, ge=1, le=2000)):
    """Return the world-model knowledge graph as {entities, relationships}."""
    try:
        wm = WorldModel(str(settings.DB_PATH))
        graph = wm.get_graph(limit=limit)
        return {
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "type": e.entity_type,
                    "confidence": e.confidence,
                    "first_seen": e.first_seen,
                    "last_seen": e.last_seen,
                    "attributes": e.attributes,
                }
                for e in graph["entities"]
            ],
            "relationships": [
                {
                    "id": r.id,
                    "subject_id": r.subject_id,
                    "predicate": r.predicate,
                    "object_id": r.object_id,
                    "confidence": r.confidence,
                    "created_at": r.created_at,
                    "last_confirmed": r.last_confirmed,
                }
                for r in graph["relationships"]
            ],
        }
    except Exception as e:
        app_logger.error(f"Knowledge graph query failed: {e}")
        return {"entities": [], "relationships": [], "error": str(e)}


# ── Projects (P2 AGI: long-horizon + multi-session) ──────────────────────────
class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    priority: str = "normal"
    milestones: Optional[List[str]] = None
    tags: Optional[List[str]] = None

class ProjectScheduleRequest(BaseModel):
    enabled: bool

class ProjectRunRequest(BaseModel):
    max_steps: int = Field(default=1, ge=1, le=10)

@router.get("/projects")
def list_projects_endpoint(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List a stable page of persistent multi-session projects."""
    try:
        from app.cognition.runtime import CognitiveRuntime
        runtime = CognitiveRuntime.get_instance()
        projects = list(runtime.project_manager._projects.values())
        if status:
            projects = [project for project in projects if project.status.value == status]
        projects.sort(
            key=lambda project: (project.updated_at, project.project_id), reverse=True
        )
        total = len(projects)
        page = projects[offset:offset + limit]
        return {
            "projects": [
                {
                    "project_id": p.project_id,
                    "name": p.name,
                    "description": p.description,
                    "status": p.status.value,
                    "priority": p.priority,
                    "progress_percent": p.progress_percent,
                    "milestones_total": p.milestones_total,
                    "milestones_reached": p.milestones_reached,
                    "total_sessions": p.total_sessions,
                    "tags": p.tags,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                }
                for p in page
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
            "next_offset": offset + len(page) if offset + len(page) < total else None,
        }
    except Exception as e:
        app_logger.error(f"List projects failed: {e}")
        return {
            "projects": [], "total": 0, "limit": limit, "offset": offset,
            "has_more": False, "next_offset": None, "error": str(e),
        }

@router.get("/projects/{project_id}")
def get_project_endpoint(project_id: str):
    """Get project + resume context."""
    try:
        from app.cognition.runtime import CognitiveRuntime
        runtime = CognitiveRuntime.get_instance()
        proj = runtime.project_manager.get_project(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        resume = runtime.project_manager.get_resume_context(project_id)
        decomp = runtime.goal_decomposer.get_project(resume.get("context", {}).get("decomposition_id", "")) if resume else None
        return {
            "project": {
                "project_id": proj.project_id,
                "name": proj.name,
                "description": proj.description,
                "status": proj.status.value,
                "priority": proj.priority,
                "progress_percent": proj.progress_percent,
                "milestones": [{
                    "id": m.milestone_id,
                    "description": m.description,
                    "status": m.status,
                    "source_sub_goal_id": m.source_sub_goal_id,
                    "reached_at": m.reached_at,
                    "notes": m.notes,
                } for m in proj.milestones],
                "sessions": len(proj.sessions),
                "context": proj.context,
                "tags": proj.tags,
            },
            "resume_context": resume,
            "decomposition": runtime.goal_decomposer.get_progress_report(decomp.project_id) if decomp else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Get project failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/projects")
def create_project_endpoint(req: ProjectCreateRequest):
    """Create a persistent project."""
    try:
        from app.cognition.runtime import CognitiveRuntime
        runtime = CognitiveRuntime.get_instance()
        proj = runtime.project_manager.create_project(
            name=req.name,
            description=req.description,
            priority=req.priority,
            milestones=req.milestones,
            tags=req.tags,
        )
        return {"success": True, "project_id": proj.project_id, "project": {"name": proj.name, "status": proj.status.value}}
    except Exception as e:
        app_logger.error(f"Create project failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/scheduler")
def configure_project_scheduler_endpoint(project_id: str, req: ProjectScheduleRequest):
    """Owner opt-in/out for persistent background DAG scheduling."""
    from app.cognition.runtime import CognitiveRuntime
    runtime = CognitiveRuntime.get_instance()
    project = runtime.project_manager.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.decomposition_id:
        raise HTTPException(status_code=409, detail="Project has no goal decomposition")
    runtime.project_manager.update_context(project_id, {"auto_schedule": req.enabled})
    return {
        "success": True,
        "project_id": project_id,
        "auto_schedule": req.enabled,
    }


@router.post("/projects/{project_id}/run-ready")
def run_project_ready_steps_endpoint(project_id: str, req: ProjectRunRequest):
    """Run a bounded batch of dependency-ready sub-goals now."""
    from app.cognition.runtime import CognitiveRuntime
    runtime = CognitiveRuntime.get_instance()
    return runtime.project_scheduler.run_project(
        runtime, project_id, max_steps=req.max_steps
    )


# ── Capability availability ─────────────────────────────────────────────────
@router.get("/tools/availability")
def tool_availability_endpoint(
    tool: Optional[str] = Query(None),
    probe: bool = Query(False),
):
    """Report tool-local dependency status without eager probing by default."""
    from app.cognition.runtime import CognitiveRuntime

    registry = CognitiveRuntime.get_instance().registry
    if tool:
        record = registry.get_tool_availability(tool, probe=probe)
        if record["status"] == "not_registered":
            raise HTTPException(status_code=404, detail=record["error"])
        return {"success": True, "tool": record}
    records = registry.list_tool_availability(probe=probe)
    return {
        "success": True,
        "probe": probe,
        "count": len(records),
        "available": sum(item["available"] is True for item in records),
        "unavailable": sum(item["available"] is False for item in records),
        "not_checked": sum(item["available"] is None for item in records),
        "tools": records,
    }


# ── Evidence-linked functional self-awareness ────────────────────────────────



























# ── Longitudinal intelligence benchmarks ────────────────────────────────────
@router.post("/benchmarks/intelligence/run")
def run_intelligence_benchmark_endpoint():
    from app.cognition.runtime import CognitiveRuntime
    report = CognitiveRuntime.get_instance().intelligence_benchmarks.run()
    return {"success": True, "report": report.to_dict()}


@router.get("/benchmarks/intelligence/latest")
def latest_intelligence_benchmark_endpoint():
    from app.cognition.runtime import CognitiveRuntime
    report = CognitiveRuntime.get_instance().intelligence_benchmarks.history_store.latest()
    return {
        "success": True,
        "report": report.to_dict() if report else None,
    }


@router.get("/benchmarks/intelligence/history")
def intelligence_benchmark_history_endpoint(
    limit: int = Query(20, ge=1, le=200),
):
    from app.cognition.runtime import CognitiveRuntime
    reports = CognitiveRuntime.get_instance().intelligence_benchmarks.history_store.history(limit)
    return {
        "success": True,
        "reports": [report.to_dict() for report in reports],
    }


# ── Shared settings (cross-platform: web / desktop / Android) ────────────────
@router.get("/settings")
def get_settings_endpoint():
    return get_settings()


@router.post("/settings")
async def update_settings_endpoint(payload: Dict[str, Any]):
    updated = update_settings(payload)
    await _apply_settings_live(payload)
    return updated


# ── Owner control plane ──────────────────────────────────────────────────────
@router.get("/owner-control")
def get_owner_control_endpoint():
    """Return the effective owner authorization policy."""
    return {"success": True, "policy": owner_control_store.get_policy().to_dict()}


@router.put("/owner-control")
def update_owner_control_endpoint(req: OwnerControlUpdate):
    """Atomically update owner authority; omitted fields remain unchanged."""
    try:
        patch = req.model_dump(exclude_none=True)
        if "mode" in patch and isinstance(patch["mode"], ControlMode):
            patch["mode"] = patch["mode"].value
        policy = owner_control_store.update(patch)
        return {"success": True, "policy": policy.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/owner-control/pause")
def pause_owner_control_endpoint(req: OwnerPauseRequest):
    """Emergency stop/resume for all capability execution and issued grants."""
    policy = owner_control_store.set_paused(req.paused)
    return {
        "success": True,
        "paused": policy.paused,
        "policy": policy.to_dict(),
        "message": "All action execution paused and grants revoked." if policy.paused else "Action execution resumed under owner policy.",
    }


@router.get("/owner-control/adaptive-autonomy")
def get_adaptive_autonomy_endpoint():
    from app.cognition.runtime import CognitiveRuntime
    runtime = CognitiveRuntime.get_instance()
    profile = runtime.adaptive_autonomy.get_profile()
    return {"success": True, "profile": profile.to_dict()}



@router.put("/owner-control/adaptive-autonomy/exploration-budget")
def set_exploration_budget_endpoint(req: ExplorationBudgetRequest):
    from app.cognition.runtime import CognitiveRuntime
    profile = CognitiveRuntime.get_instance().adaptive_autonomy.set_owner_max_exploration_goals(
        req.max_exploration_goals
    )
    return {"success": True, "profile": profile.to_dict()}


@router.get("/owner-control/executions")
def list_controlled_executions_endpoint(
    active_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
):
    from app.cognition.execution_control import execution_control_registry
    records = execution_control_registry.list(active_only=active_only, limit=limit)
    return {"success": True, "executions": [record.to_dict() for record in records]}


@router.post("/owner-control/executions/{execution_id}/cancel")
def cancel_controlled_execution_endpoint(execution_id: str):
    from app.cognition.execution_control import execution_control_registry
    record = execution_control_registry.request_cancel(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {
        "success": True,
        "execution": record.to_dict(),
        "note": (
            "Cancellation is cooperative. A running tool stops only at a cancellation "
            "checkpoint; side effects before that checkpoint may already exist."
        ),
    }


@router.post("/owner-control/executions/{execution_id}/request-rollback")
def request_execution_rollback_endpoint(execution_id: str):
    from app.cognition.approval_store import approval_store
    from app.cognition.execution_control import execution_control_registry
    record = execution_control_registry.get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    receipt = record.rollback_receipt
    if receipt is None or not receipt.supported or not receipt.compensation_action:
        raise HTTPException(
            status_code=409,
            detail=receipt.reason if receipt else "No rollback receipt exists",
        )
    request = approval_store.add(
        conversation_id=f"rollback:{execution_id}",
        action_type=receipt.compensation_action,
        payload=receipt.compensation_payload,
        reason=f"Rollback requested for {execution_id}: {receipt.reason}",
        goal_text=f"Rollback {record.action_type} execution {execution_id}",
    )
    return {
        "success": True,
        "rollback_receipt": receipt.to_dict(),
        "approval": request.to_dict(),
    }


@router.get("/owner-control/approvals")
def list_pending_approvals_endpoint():
    from app.cognition.approval_store import approval_store
    return {
        "success": True,
        "approvals": [request.to_dict() for request in approval_store.list_pending()],
        "history": [request.to_dict() for request in approval_store.list_all(limit=500)],
    }


@router.post("/owner-control/approvals/{action_id}/decision")
def decide_pending_approval_endpoint(action_id: str, req: ApprovalDecisionRequest):
    from app.cognition.approval_store import approval_store
    request = approval_store.decide(
        action_id,
        approved=req.approved,
        note=req.note,
        ttl_seconds=req.ttl_seconds,
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {"success": True, "approval": request.to_dict()}


@router.get("/owner-control/authorizations")
def list_authorizations_endpoint():
    """List active grants and recover their exact reviewed scope when available."""
    from app.cognition.approval_store import approval_store
    from app.cognition.owner_control import payload_digest

    authorizations = []
    for grant in authorization_store.list_active():
        item = grant.to_dict()
        approval = (
            approval_store.get(grant.source_approval_id)
            if grant.source_approval_id else None
        )
        # The approval payload is returned only when it still hashes to the
        # immutable grant digest. This gives owner clients an executable exact
        # scope without broadening or reconstructing authority from a hash.
        if (
            approval is not None
            and approval.action_type == grant.action_type
            and payload_digest(approval.payload) == grant.payload_sha256
        ):
            item["payload"] = approval.payload
            item["scope_recoverable"] = True
        else:
            item["scope_recoverable"] = False
        authorizations.append(item)
    return {"success": True, "authorizations": authorizations}


@router.post("/owner-control/authorizations")
def issue_authorization_endpoint(req: AuthorizationIssueRequest):
    """Owner-authorize one exact action/payload scope for a short period."""
    try:
        grant = authorization_store.issue(
            req.action_type,
            req.payload,
            ttl_seconds=req.ttl_seconds,
            max_uses=req.max_uses,
            plan_id=req.plan_id,
            override_owner_policy=req.override_owner_policy,
        )
        return {"success": True, "authorization": grant.to_dict()}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/owner-control/sovereign-authorizations")
def issue_sovereign_authorization_endpoint(req: AuthorizationIssueRequest):
    """Owner override of owner-authored policy for one exact action; does not execute."""
    try:
        grant=authorization_store.issue(
            req.action_type,req.payload,ttl_seconds=req.ttl_seconds,
            max_uses=req.max_uses,plan_id=req.plan_id,override_owner_policy=True,
        )
        return {"success":True,"authorization":grant.to_dict(),"executed":False,
          "note":"Exact sovereign override issued. Emergency pause, resource gates, capability availability, and verification remain enforced."}
    except (TypeError,ValueError) as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.delete("/owner-control/authorizations/{authorization_id}")
def revoke_authorization_endpoint(authorization_id: str):
    if not authorization_store.revoke(authorization_id):
        raise HTTPException(status_code=404, detail="Authorization not found")
    return {"success": True, "authorization_id": authorization_id, "revoked": True}


@router.post("/owner-control/execute-authorized")
def execute_authorized_endpoint(req: AuthorizedExecutionRequest):
    """Run an exact scoped action through execution, observation, and verification."""
    from app.cognition.action_proposal import ActionProposal
    from app.cognition.runtime import CognitiveRuntime

    proposal = ActionProposal(
        action_type=req.action_type,
        payload=req.payload,
        authorization_id=req.authorization_id,
        plan_id=req.plan_id,
        decision_stage="authorization",
    )
    # Restore the original recommendation record when this grant came from a
    # pending chat approval. This keeps consideration → recommendation →
    # authorization → execution linked under the original proposal ID.
    execution_goal_text = req.user_text
    grant_decision = authorization_store.validate(
        req.authorization_id,
        req.action_type,
        req.payload,
        plan_id=req.plan_id,
    )
    if grant_decision.valid and grant_decision.grant and grant_decision.grant.source_approval_id:
        from app.cognition.approval_store import approval_store
        approval = approval_store.get(grant_decision.grant.source_approval_id)
        if approval is not None:
            proposal.proposal_id = approval.proposal_id or proposal.proposal_id
            proposal.recommendation_reason = approval.recommendation_reason
            proposal.alternatives_considered = list(approval.alternatives_considered)
            proposal.predicted_outcome = dict(approval.predicted_outcome)
            if approval.goal_text:
                execution_goal_text = approval.goal_text

    return CognitiveRuntime.get_instance().execute_authorized_proposal(
        proposal,
        user_text=execution_goal_text,
        complexity=req.complexity,
    )


@router.get("/owner-control/plans")
def list_plan_reviews_endpoint(status_filter: Optional[str] = Query(default=None, alias="status")):
    from app.cognition.plan_control import PlanReviewStatus, plan_review_store
    try:
        status_value = PlanReviewStatus(status_filter) if status_filter else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown plan status: {status_filter}") from exc
    return {
        "success": True,
        "plans": [review.to_dict() for review in plan_review_store.list(status_value)],
    }


@router.get("/owner-control/plans/{plan_id}/freshness")
def get_plan_freshness_endpoint(plan_id: str):
    from app.cognition.plan_control import plan_review_store
    from app.cognition.runtime import CognitiveRuntime
    review=plan_review_store.get(plan_id)
    if review is None:raise HTTPException(status_code=404,detail="Plan review not found")
    return {"success":True,"freshness":CognitiveRuntime.get_instance().plan_freshness.validate(review,CognitiveRuntime.get_instance()).to_dict()}

@router.get("/owner-control/plans/{plan_id}")
def get_plan_review_endpoint(plan_id: str):
    from app.cognition.plan_control import plan_review_store
    review = plan_review_store.get(plan_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Plan review not found")
    return {"success": True, "plan": review.to_dict()}


@router.put("/owner-control/plans/{plan_id}")
def edit_plan_review_endpoint(plan_id: str, req: PlanEditRequest):
    from app.cognition.plan_control import plan_review_store
    from app.cognition.runtime import CognitiveRuntime
    try:
        current_review = plan_review_store.get(plan_id)
        if current_review is None:
            raise KeyError(plan_id)
        execution_plan = CognitiveRuntime.get_instance().goal_executor.get_plan(plan_id)
        if execution_plan and execution_plan.started_at:
            old_steps = {
                step["step_id"]: step for step in current_review.snapshot.get("steps", [])
            }
            new_steps = {str(step.get("step_id", "")): step for step in req.steps}
            for executed_step in execution_plan.steps:
                if executed_step.status.value != "pending":
                    if new_steps.get(executed_step.step_id) != old_steps.get(executed_step.step_id):
                        raise ValueError(
                            f"Already-started step '{executed_step.step_id}' is immutable"
                        )
        review = plan_review_store.edit(plan_id, req.expected_revision, req.steps)
        return {"success": True, "plan": review.to_dict()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Plan review not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/owner-control/plans/{plan_id}/decision")
def decide_plan_review_endpoint(plan_id: str, req: PlanDecisionRequest):
    from app.cognition.plan_control import plan_review_store
    try:
        review = plan_review_store.decide(
            plan_id, req.expected_revision, req.approved, req.note
        )
        freshness = None
        if req.approved:
            from app.cognition.runtime import CognitiveRuntime
            runtime = CognitiveRuntime.get_instance()
            freshness = runtime.plan_freshness.capture(review, runtime).to_dict()
        return {"success": True, "plan": review.to_dict(), "freshness": freshness}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Plan review not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/owner-control/plans/{plan_id}/revoke")
def revoke_plan_review_endpoint(plan_id: str, req: PlanRevokeRequest):
    from app.cognition.plan_control import plan_review_store
    try:
        review = plan_review_store.revoke(plan_id, req.note)
        return {"success": True, "plan": review.to_dict()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Plan review not found") from exc


@router.post("/owner-control/plans/{plan_id}/execute")
def execute_approved_plan_endpoint(plan_id: str):
    from app.cognition.plan_control import PlanReviewStatus, plan_review_store
    from app.cognition.runtime import CognitiveRuntime

    review = plan_review_store.get(plan_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Plan review not found")
    if review.status != PlanReviewStatus.APPROVED:
        raise HTTPException(status_code=409, detail=f"Plan is {review.status.value}, not approved")
    runtime = CognitiveRuntime.get_instance()
    freshness = runtime.plan_freshness.validate(review, runtime)
    if not freshness.fresh:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Approved plan assumptions changed; revise and approve a fresh plan before execution.",
                "freshness": freshness.to_dict(),
                "executed": False,
            },
        )
    try:
        runtime.commitments.upsert(
            review.goal_title or plan_id, source_type="approved_plan",
            source_id=plan_id, status="active",
            evidence=[f"approved_plan_revision:{review.revision}"],
        )
    except Exception as exc:
        app_logger.warning(f"Could not record approved-plan commitment: {exc}")
    if plan_id.startswith("project_dag_"):
        project_id = plan_id[len("project_dag_"):]
        result = runtime.project_scheduler.run_project(
            runtime, project_id, max_steps=10
        )
        runtime.refresh_commitments()
        return result
    plan = runtime.goal_executor.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Execution plan not found")
    result = runtime.goal_executor.execute_plan(plan, runtime)
    try:
        if result.status.value == "completed":
            runtime.commitments.upsert(
                review.goal_title or plan_id, source_type="approved_plan",
                source_id=plan_id, status="completed",
                evidence=[f"execution_plan_status:{result.status.value}"],
                completion_verified=True,
            )
        elif result.status.value in ("blocked", "paused"):
            runtime.commitments.upsert(
                review.goal_title or plan_id, source_type="approved_plan",
                source_id=plan_id, status="blocked",
                evidence=[f"execution_plan_status:{result.status.value}"],
                blocked_reason=f"Execution plan is {result.status.value}.",
            )
        elif result.status.value == "failed":
            runtime.commitments.upsert(
                review.goal_title or plan_id, source_type="approved_plan",
                source_id=plan_id, status="failed",
                evidence=["execution_plan_status:failed"],
            )
    except Exception as exc:
        app_logger.warning(f"Could not update approved-plan commitment: {exc}")
    return {
        "success": True,
        "request_success": True,
        "execution_success": result.status.value == "completed",
        "plan_status": result.status.value,
        "plan": result.to_dict(),
    }


async def _apply_settings_live(patch: Dict[str, Any]) -> None:
    """Apply a settings patch to the running subsystems (best-effort).

    - `voice` → persist the active Piper voice (drives /voice/synthesize).
    - `wake_word` / `voice` / `voice_speed` / `vad_sensitivity` /
      `noise_suppression` / `voice_enabled` / `response_delay` → live-update the
      running voice pipeline when one is active (closes G2 — no dead settings).
    """
    # Piper voice selection is a file-backed setting consumed at synth time, so
    # persist it regardless of whether the pipeline is currently running.
    if patch.get("voice"):
        try:
            LocalTextToSpeech.set_active_piper_voice(str(patch["voice"]))
        except Exception as e:  # noqa: BLE001
            app_logger.warning(f"Could not set active Piper voice: {e}")

    live: Dict[str, Any] = {}
    if "wake_word" in patch:
        live["wakeWord"] = patch["wake_word"]
    if "voice" in patch:
        live["selectedVoice"] = patch["voice"]
    if "voice_speed" in patch:
        live["voiceSpeed"] = patch["voice_speed"]
    if "vad_sensitivity" in patch:
        live["vadSensitivity"] = patch["vad_sensitivity"]
    if "noise_suppression" in patch:
        live["noiseSuppression"] = patch["noise_suppression"]
    if "voice_enabled" in patch:
        live["voiceEnabled"] = patch["voice_enabled"]
    if "response_delay" in patch:
        live["responseDelay"] = patch["response_delay"]
    if not live:
        return

    try:
        # Imported lazily: the voice service pulls in the pipeline/orchestrator
        # stack, which is only needed here when a live update is requested.
        from backend.voice.service import voice_service
        await voice_service.update_settings(live)
    except Exception as e:  # noqa: BLE001
        app_logger.warning(f"Could not apply live voice settings: {e}")


@router.delete("/memories/{memory_id}")
def delete_memory_record(memory_id: int):
    if not db.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found or deletion failed")
    return {"message": f"Memory {memory_id} deleted successfully."}

# 6. Policy & Rules Evaluation Endpoint
@router.post("/policies/evaluate")
def evaluate_action_policy(req: ActionEvaluationRequest):
    allowed, reason, level = PolicyEvaluator.evaluate_action(req.action_type, req.details)
    return {
        "allowed": allowed,
        "reason": reason,
        "authority_level": level,
        "action": req.action_type
    }

# 7. File Readers & Editors for Context Docs (Manual and Rules)
@router.get("/manual")
def get_user_manual():
    try:
        with open(settings.USER_MANUAL_PATH, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="User Operating Manual not found")

@router.post("/manual")
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

@router.get("/rules")
def get_rules():
    try:
        with open(settings.RULES_PATH, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Rules and boundaries document not found")

@router.post("/rules")
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
@router.get("/models")
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

@router.post("/models/config")
def update_model_config(config: ModelConfigUpdate):
    # Legacy entry point: writes through the owner inference profile store so
    # there is exactly one persisted source of truth for model configuration.
    from app.cognition.inference_profile import apply_profile, inference_profile_store
    try:
        patch = {}
        if config.fast_model:
            patch["fast_model"] = config.fast_model.strip()
        if config.main_model:
            patch["main_model"] = config.main_model.strip()
        if config.lm_studio_url:
            patch["provider_url"] = config.lm_studio_url.rstrip('/').strip()
        profile = inference_profile_store.update(patch) if patch else inference_profile_store.get()
        applied = apply_profile(profile)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    db.create_audit_log("update_model_config", "success", f"Fast Model: {applied['fast_model']}, Main Model: {applied['main_model']}, Endpoint: {applied['lm_studio_url']}", level=1)

    return {
        "message": "Model settings updated successfully.",
        "success": True,
        "configured_fast_model": applied["fast_model"],
        "configured_main_model": applied["main_model"],
        "lm_studio_url": applied["lm_studio_url"],
        "context_window_tokens": applied["context_window_tokens"],
        "profile_revision": profile.revision
    }

@router.get("/owner-control/inference-profile")
def get_inference_profile_endpoint():
    from app.cognition.inference_profile import inference_profile_store
    profile = inference_profile_store.get()
    return {
        "success": True,
        "profile": profile.to_dict(),
        "divergence": inference_profile_store.divergence(profile),
        "note": "Recommendations derive from the measured hardware tier; only a live provider load/completion proves capability.",
    }

@router.put("/owner-control/inference-profile")
def update_inference_profile_endpoint(req: InferenceProfileUpdate):
    from app.cognition.inference_profile import apply_profile, inference_profile_store
    try:
        profile = inference_profile_store.update(req.model_dump(exclude_unset=True))
        applied = apply_profile(profile)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "profile": profile.to_dict(),
        "applied": applied,
        "divergence": inference_profile_store.divergence(profile),
    }

@router.post("/owner-control/inference-profile/probe")
def probe_inference_profile_endpoint():
    from app.cognition.inference_profile import inference_profile_store, probe_provider
    evidence = probe_provider(inference_profile_store.get())
    return {
        "success": True,
        "evidence": evidence,
        "note": "Measured live provider evidence; offline or unprobed states remain unknown.",
    }

@router.post("/models/unload")
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
@router.post("/tools/youtube-learn")
def youtube_learn_endpoint(req: YouTubeLearnRequest):
    result = YouTubeLearner.learn_from_video(req.url, prompt_focus=req.prompt_focus)
    if result.get("success") and req.auto_save_memory:
        mem_id = KnowledgeIndexer.index_youtube_knowledge(result)
        result["memory_id"] = mem_id
    return result

@router.post("/tools/web-learn")
def web_learn_endpoint(req: WebLearnRequest):
    result = WebResearcher.learn_from_article(req.url)
    if result.get("success") and req.auto_save_memory:
        mem_id = KnowledgeIndexer.index_web_knowledge(result)
        result["memory_id"] = mem_id
    return result

@router.post("/tools/web-search")
def web_search_endpoint(req: WebSearchRequest):
    return WebResearcher.search_and_scrape(req.query, max_results=req.max_results)

@router.get("/tools/approved-docs")
def list_approved_docs_endpoint():
    return DocumentManager.list_workspace_files()

@router.get("/tools/workspace-files")
def list_workspace_files_endpoint():
    """Backward-compatible unpaged workspace listing."""
    return DocumentManager.list_workspace_files()


@router.get("/tools/workspace-files/page")
def list_workspace_files_page_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    extension: Optional[str] = Query(None),
):
    """Return a stable bounded page of workspace and approved files."""
    files = DocumentManager.list_workspace_files()
    if extension:
        normalized = extension.lower().strip()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        files = [item for item in files if item.get("extension") == normalized]
    files.sort(key=lambda item: (item.get("relative_path", ""), item.get("file_name", "")))
    total = len(files)
    page = files[offset:offset + limit]
    return {
        "files": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < total,
        "next_offset": offset + len(page) if offset + len(page) < total else None,
    }

@router.post("/tools/read-doc")
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
            ai_summary = require_real_completion(llm_res)
            mem_id = KnowledgeIndexer.index_doc_knowledge(result, ai_summary)
            result["memory_id"] = mem_id
            result["ai_summary"] = ai_summary
        except Exception as e:
            app_logger.error(f"Error summarizing document: {e}")
    return result

@router.post("/tools/create-doc")
def create_doc_endpoint(req: DocCreateRequest):
    return DocumentManager.create_document(req.file_path, req.content, overwrite=req.overwrite)

@router.post("/tools/edit-doc")
def edit_doc_endpoint(req: DocEditRequest):
    return DocumentManager.edit_document(
        req.file_path,
        new_content=req.new_content,
        append_content=req.append_content,
        search_target=req.search_target,
        replace_text=req.replace_text
    )

# 10. Phase 3 Perception: Local Speech-to-Text & Text-to-Speech Endpoints
@router.post("/voice/transcribe")
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

@router.post("/voice/synthesize")
def voice_synthesize_endpoint(req: TTSSynthesizeRequest):
    res = LocalTextToSpeech.synthesize_speech(req.text, voice=req.voice)
    db.create_audit_log(
        "voice_synthesize",
        "success" if res.get("success") else "failed",
        (
            f"Synthesized speech for text: '{req.text[:80]}'"
            if res.get("success")
            else f"Speech synthesis unavailable: {res.get('error', 'unknown error')}"
        ),
        level=0,
    )
    return res


@router.get("/voice/piper-voices")
def list_piper_voices_endpoint():
    """List available Piper voice models (discovered from disk)."""
    return {"voices": LocalTextToSpeech.list_piper_voices(), "active_voice": LocalTextToSpeech.get_active_piper_voice()}


@router.post("/voice/piper/select")
def select_piper_voice_endpoint(req: VoiceProfileSelectRequest):
    ok = LocalTextToSpeech.set_active_piper_voice(req.profile_name)
    # Keep the shared settings store in sync so web/desktop/Android see the same voice.
    update_settings({"voice": LocalTextToSpeech.get_active_piper_voice()})
    db.create_audit_log("select_piper_voice", "success", f"Selected Piper voice: '{req.profile_name}'", level=0)
    return {"success": ok, "active_voice": LocalTextToSpeech.get_active_piper_voice()}

@router.post("/voice/clone-reference")
async def upload_voice_clone_reference(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    ref_path = LocalTextToSpeech.set_custom_voice_reference(audio_bytes)
    db.create_audit_log("upload_voice_clone_reference", "success", f"Saved custom voice cloning reference ({len(audio_bytes)} bytes)", level=0)
    return {
        "success": True,
        "message": "Custom voice cloning reference updated successfully!",
        "file_path": ref_path
    }

@router.get("/voice/profiles")
def get_voice_profiles_endpoint():
    return LocalTextToSpeech.list_voice_profiles()

@router.post("/voice/profiles/select")
def select_voice_profile_endpoint(req: VoiceProfileSelectRequest):
    success = LocalTextToSpeech.set_active_voice_profile(req.profile_name)
    db.create_audit_log("select_voice_profile", "success", f"Selected voice profile: '{req.profile_name}'", level=0)
    return {"success": success, "active_profile": req.profile_name}

@router.post("/voice/profiles/record")
async def record_voice_profile_endpoint(file: UploadFile = File(...), profile_name: str = Query(...)):
    audio_bytes = await file.read()
    res = LocalTextToSpeech.save_voice_profile(profile_name, audio_bytes)
    db.create_audit_log("record_voice_profile", "success", f"Recorded custom voice profile: '{profile_name}'", level=0)
    return res

@router.post("/voice/chat")
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
        "speaker_verified": speaker_check.get("verified", False),
        "speaker_verification": speaker_check,
    }

# 11. Mobile Network & Remote Access Endpoints
@router.get("/api/network-info")
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

@router.post("/mobile/location")
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

@router.post("/mobile/camera")
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
@router.post("/vision/capture")
def capture_screen_endpoint():
    res = ScreenCaptureTool.capture_screen()
    db.create_audit_log("capture_screen", "success", f"Captured screen: {res.get('file_name')}", level=0)
    return res

@router.post("/vision/ocr")
def vision_ocr_endpoint(req: VisionOCRRequest):
    return OCRReaderTool.extract_text_from_image(req.image_path)

@router.post("/vision/analyze")
def vision_analyze_endpoint(req: VisionAnalyzeRequest):
    # Analyzing an explicit (user-uploaded) image — never apply the screen-delta
    # dedup, which would wrongly skip analysis when the live screen is unchanged.
    return VisionAnalyzerTool.analyze_screen_image(
        req.image_path, 
        prompt_focus=req.prompt_focus, 
        auto_save_memory=req.auto_save_memory,
        skip_delta_check=True,
    )

@router.post("/vision/capture-and-analyze")
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

# P1-1 AGI: Perception → Grounding — object/face detection endpoints
class VisionDetectRequest(BaseModel):
    image_path: str
    conf_threshold: float = 0.5
    auto_create_groundings: bool = True

@router.post("/vision/detect-objects")
def vision_detect_objects_endpoint(req: VisionDetectRequest):
    """Detect objects + auto-create language groundings (perception→grounding loop)."""
    try:
        from app.tools.object_detector import ObjectDetectorTool
        if req.auto_create_groundings:
            return ObjectDetectorTool.analyze_image_grounded(req.image_path, auto_create_groundings=True)
        return ObjectDetectorTool.detect_objects(req.image_path, conf_threshold=req.conf_threshold)
    except Exception as e:
        app_logger.error(f"Object detection endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vision/detect-faces")
def vision_detect_faces_endpoint(req: VisionOCRRequest):
    """Detect faces in an image."""
    try:
        from app.tools.object_detector import ObjectDetectorTool
        return ObjectDetectorTool.detect_faces(req.image_path)
    except Exception as e:
        app_logger.error(f"Face detection endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/vision/groundings")
def list_groundings_endpoint(symbol: Optional[str] = Query(None), modality: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500)):
    """List language groundings (perceptual) — shows how words are grounded to vision."""
    try:
        from app.cognition.runtime import CognitiveRuntime
        runtime = CognitiveRuntime.get_instance()
        groundings = runtime.language_grounding.get_perceptual_groundings(symbol=symbol, modality=modality, limit=limit)
        return {
            "groundings": [g.to_dict() for g in groundings],
            "count": len(groundings),
            "summary": runtime.language_grounding.get_grounding_summary(),
        }
    except Exception as e:
        app_logger.error(f"Groundings list failed: {e}")
        return {"groundings": [], "count": 0, "error": str(e)}


@router.get("/vision/temporal-scene")
def temporal_scene_endpoint(stream_id: str = Query("desktop_screen")):
    """Return active object tracks for one explicit visual stream."""
    from app.cognition.runtime import CognitiveRuntime
    return {
        "success": True,
        "scene": CognitiveRuntime.get_instance().temporal_vision.scene_summary(stream_id),
    }


@router.get("/vision/temporal-events")
def temporal_events_endpoint(limit: int = Query(50, ge=1, le=500)):
    """Return provenance-carrying appeared/moved/disappeared events."""
    from app.cognition.runtime import CognitiveRuntime
    events = CognitiveRuntime.get_instance().temporal_vision.recent_events(limit=limit)
    return {"success": True, "events": events, "count": len(events)}

# VLM integration (P2 AGI: true visual understanding)
@router.get("/vision/vlm-status")
def vlm_status_endpoint():
    """Check VLM availability — honest status (Moondream2/Llava)."""
    try:
        from app.tools.vlm_analyzer import VlmAnalyzerTool
        return VlmAnalyzerTool.get_status()
    except Exception as e:
        app_logger.error(f"VLM status failed: {e}")
        return {"available": False, "error": str(e), "engine": "none"}

@router.post("/vision/vlm-analyze")
def vlm_analyze_endpoint(req: VisionAnalyzeRequest):
    """True VLM analysis with OCR+LLM fallback."""
    try:
        from app.tools.vlm_analyzer import VlmAnalyzerTool
        return VlmAnalyzerTool.analyze_image(req.image_path, prompt=req.prompt_focus or "Describe this image in detail")
    except Exception as e:
        app_logger.error(f"VLM analyze failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# LoRA continual learning (P2 AGI)
class LoraActivateRequest(BaseModel):
    adapter_name: str

class LoraDatasetRequest(BaseModel):
    skill_name: str
    examples: List[Dict[str, str]]

class LoraJobRequest(BaseModel):
    adapter_name: str
    base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    skill_name: str = "general"
    r: int = 8
    lora_alpha: int = 16
    epochs: int = 3
    learning_rate: float = 2e-4

class TrainingCandidateEditRequest(BaseModel):
    prompt: str
    response: str
    skill_name: str
    note: str = ""

class TrainingCandidateDecisionRequest(BaseModel):
    approved: bool
    note: str = ""

class OwnerCorrectionRequest(BaseModel):
    prompt: str
    response: str
    skill_name: str = "general"
    note: str = ""

class TrainingDatasetExportRequest(BaseModel):
    skill_name: str

class LoraEvaluationRequest(BaseModel):
    adapter_name: str
    base_model: str
    adapter_model: str
    skill_name: str
    unrelated_skill_name: str
    minimum_improvement: float = Field(0.02, ge=0.0, le=1.0)
    maximum_regression: float = Field(0.03, ge=0.0, le=1.0)

class LoraDeploymentRequest(BaseModel):
    report_id: str

@router.get("/loras")
def list_loras_endpoint():
    """List LoRA adapters."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.list_adapters()
    except Exception as e:
        app_logger.error(f"List loras failed: {e}")
        return {"success": False, "error": str(e), "adapters": []}

@router.get("/loras/status")
def lora_status_endpoint():
    """Get LoRA system status."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.get_status()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/loras/active")
def get_active_lora_endpoint():
    """Get active LoRA adapter."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.get_active_adapter()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/loras/activate")
def activate_lora_endpoint(req: LoraActivateRequest):
    """Activate LoRA adapter."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.activate_adapter(req.adapter_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/loras/deactivate")
def deactivate_lora_endpoint():
    """Deactivate LoRA adapter."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.deactivate_adapter()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/loras/training-candidates")
def list_training_candidates_endpoint(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    skill_name: Optional[str] = Query(default=None),
):
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.training_examples import TrainingExampleStatus
    try:
        status_value = TrainingExampleStatus(status_filter) if status_filter else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown candidate status: {status_filter}") from exc
    candidates = CognitiveRuntime.get_instance().training_examples.list(
        status=status_value, skill_name=skill_name
    )
    return {"success": True, "candidates": [item.to_dict() for item in candidates]}


@router.post("/loras/training-candidates/owner-correction")
def create_owner_correction_endpoint(req: OwnerCorrectionRequest):
    from app.cognition.runtime import CognitiveRuntime
    candidate = CognitiveRuntime.get_instance().training_examples.propose_owner_correction(
        prompt=req.prompt,
        response=req.response,
        skill_name=req.skill_name,
        note=req.note,
    )
    if candidate is None:
        raise HTTPException(status_code=400, detail="Prompt and response must each contain at least 3 characters")
    return {"success": True, "candidate": candidate.to_dict()}


@router.put("/loras/training-candidates/{candidate_id}")
def edit_training_candidate_endpoint(candidate_id: str, req: TrainingCandidateEditRequest):
    from app.cognition.runtime import CognitiveRuntime
    try:
        candidate = CognitiveRuntime.get_instance().training_examples.edit(
            candidate_id,
            prompt=req.prompt,
            response=req.response,
            skill_name=req.skill_name,
            note=req.note,
        )
        return {"success": True, "candidate": candidate.to_dict()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Training candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/loras/training-candidates/{candidate_id}/decision")
def decide_training_candidate_endpoint(candidate_id: str, req: TrainingCandidateDecisionRequest):
    from app.cognition.runtime import CognitiveRuntime
    try:
        candidate = CognitiveRuntime.get_instance().training_examples.decide(
            candidate_id, approved=req.approved, note=req.note
        )
        return {"success": True, "candidate": candidate.to_dict()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Training candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/loras/training-candidates/export")
def export_training_candidates_endpoint(req: TrainingDatasetExportRequest):
    from app.cognition.runtime import CognitiveRuntime
    return CognitiveRuntime.get_instance().training_examples.export_approved(req.skill_name)


@router.post("/loras/evaluations")
def evaluate_lora_adapter_endpoint(req: LoraEvaluationRequest):
    """Run base-vs-adapter held-out and unrelated-domain evaluation."""
    from app.cognition.lora_evaluation import LoraEvaluationManager

    return LoraEvaluationManager.evaluate(
        adapter_name=req.adapter_name,
        base_model=req.base_model,
        adapter_model=req.adapter_model,
        skill_name=req.skill_name,
        unrelated_skill_name=req.unrelated_skill_name,
        minimum_improvement=req.minimum_improvement,
        maximum_regression=req.maximum_regression,
    )


@router.get("/loras/evaluations/{report_id}")
def get_lora_evaluation_endpoint(report_id: str):
    from app.cognition.lora_evaluation import LoraEvaluationManager

    report = LoraEvaluationManager.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="LoRA evaluation report not found")
    return {"success": True, "report": report}


@router.post("/loras/deploy-evaluated")
def deploy_evaluated_lora_endpoint(req: LoraDeploymentRequest):
    """Apply only an evaluation-gated provider model after a fresh probe."""
    from app.cognition.lora_evaluation import LoraEvaluationManager

    return LoraEvaluationManager.deploy(req.report_id)


@router.post("/loras/dataset")
def prepare_lora_dataset_endpoint(req: LoraDatasetRequest):
    """Prepare dataset for LoRA training."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.prepare_dataset(req.skill_name, req.examples)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/loras/train-job")
def create_lora_job_endpoint(req: LoraJobRequest):
    """Create LoRA training job config."""
    try:
        from app.tools.lora_manager import LoraManagerTool
        return LoraManagerTool.create_training_job(
            req.adapter_name, req.base_model, req.skill_name, req.r, req.lora_alpha, req.epochs, req.learning_rate
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 13. Phase 5 Automation: Browser & Desktop Automation Endpoints

# 14. Phase 6 Domain Specialist Intelligence Endpoints
@router.post("/specialists/security/scan")
def security_scan_endpoint(req: SecurityScanRequest):
    return SecurityLabTool.scan_lab_target(req.target)

@router.post("/specialists/finance/risk-calc")
def finance_risk_calc_endpoint(req: PositionSizeRequest):
    return FinanceTraderTool.calculate_position_size(
        req.bankroll, 
        risk_percent=req.risk_percent, 
        entry_price=req.entry_price, 
        stop_loss_price=req.stop_loss_price
    )

@router.post("/specialists/finance/ev-calc")
def finance_ev_calc_endpoint(req: EVCalcRequest):
    return FinanceTraderTool.calculate_expected_value(
        req.odds_decimal, 
        req.estimated_win_probability, 
        req.stake
    )

@router.post("/specialists/finance/paper-trade")
def finance_paper_trade_endpoint(req: PaperTradeRequest):
    return FinanceTraderTool.log_paper_trade(
        req.asset_or_event, 
        req.direction, 
        req.entry_val, 
        req.target_val, 
        req.stop_val, 
        notes=req.notes or ""
    )

@router.post("/specialists/music/vocal-guide")
def music_vocal_guide_endpoint(req: VocalGuideRequest):
    return MusicStudioTool.generate_vocal_chain_guide(
        genre=req.genre, 
        vocal_type=req.vocal_type, 
        daw_name=req.daw_name
    )

@router.post("/specialists/content/script")
def content_script_endpoint(req: ContentScriptRequest):
    return ContentCreatorTool.generate_content_script(
        req.topic, 
        platform=req.platform, 
        target_audience=req.target_audience, 
        auto_save_workspace=req.auto_save_workspace
    )

@router.post("/specialists/security/parse-intent")
def security_parse_intent_endpoint(req: SecurityNLURequest):
    return CybersecurityBrainTool.parse_natural_security_intent(req.prompt, target_scope=req.target_scope)

@router.post("/specialists/security/generate-yara")
def security_generate_yara_endpoint(req: YaraRuleRequest):
    return CybersecurityBrainTool.generate_yara_rule(req.rule_name, req.strings_list, meta_description=req.meta_description)

@router.post("/specialists/security/generate-sigma")
def security_generate_sigma_endpoint(req: SigmaRuleRequest):
    return CybersecurityBrainTool.generate_sigma_rule(req.title, req.logsource_category, req.detection_selection)

@router.post("/specialists/security/defensive-audit")
def security_defensive_audit_endpoint(req: DefensiveAuditRequest):
    return SecurityEducationTool.audit_code_defensively(req.code_snippet, language=req.language)

@router.post("/specialists/coder/debug")
def coder_debug_endpoint(req: CodeDebugRequest):
    return CoderBrainTool.explain_and_debug_code(req.code_snippet, language=req.language)

@router.post("/specialists/coder/generate-tests")
def coder_generate_tests_endpoint(req: UnitTestsRequest):
    return CoderBrainTool.generate_unit_tests(req.code_snippet, language=req.language)

@router.post("/specialists/media/generate-svg")
def media_generate_svg_endpoint(req: SVGGenerateRequest):
    return MediaStudioTool.generate_svg_graphic(req.description)

@router.post("/specialists/legal/consult")
def legal_consult_endpoint(req: LegalConsultRequest):
    return KnowledgeDomainsTool.legal_compliance_consult(req.topic_or_question)

@router.post("/specialists/counseling/reflect")
def counseling_reflect_endpoint(req: CounselingRequest):
    return KnowledgeDomainsTool.psychological_counseling_partner(req.user_reflection)

@router.post("/specialists/finance/pnl-calc")
def finance_pnl_calc_endpoint(req: PnLCalcRequest):
    return KnowledgeDomainsTool.accounting_finance_calc(
        req.revenue, 
        req.operating_expenses, 
        tax_rate_percent=req.tax_rate_percent
    )

@router.post("/tools/daily-briefing")
def daily_briefing_endpoint(req: BriefingRequest):
    return DailyBriefingEngine.generate_briefing(
        custom_topics=req.custom_topics,
        generate_audio=req.generate_audio
    )

@router.post("/tools/workflow-execute")
def workflow_execute_endpoint(req: WorkflowExecuteRequest):
    return WorkflowEngine.execute_workflow(req.workflow_name, req.steps)

@router.post("/human/assimilate")
def human_assimilate_endpoint(req: HumanAssimilateRequest):
    return HumanNatureEngine.assimilate_human_experience(
        req.user_text, req.assistant_response, feedback=req.feedback
    )

@router.post("/tools/universal-media-learn")
def universal_media_endpoint(req: UniversalMediaRequest):
    return UniversalMediaLearner.analyze_media_target(
        req.target_url_or_path, prompt_focus=req.prompt_focus
    )

@router.post("/opsec/audit-footprint")
def opsec_audit_endpoint(req: OpSecAuditRequest):
    return OpSecManagerTool.audit_digital_footprint(req.query_identifier)

@router.post("/opsec/generate-erasure")
def opsec_erasure_endpoint(req: OpSecErasureRequest):
    return OpSecManagerTool.generate_erasure_requests(
        req.target_service_name, req.user_identifier, jurisdiction=req.jurisdiction or "GDPR Article 17 / CCPA"
    )

@router.post("/specialists/security/pentest-report")
def pentest_report_endpoint(req: PentestReportRequest):
    return PentestCompanyAssistant.generate_pentest_report(
        req.client_company_name,
        assessment_type=req.assessment_type or "External Network & Web Application Penetration Test",
        target_scope=req.target_scope,
        vulnerabilities_found=req.vulnerabilities_found
    )

@router.post("/specialists/security/draft-roe")
def pentest_roe_endpoint(req: PentestRoERequest):
    return PentestCompanyAssistant.draft_rules_of_engagement(
        req.client_company_name,
        req.authorized_ip_ranges,
        testing_window=req.testing_window or "Monday - Friday, 09:00 - 17:00 EST"
    )

@router.post("/sandbox/create")
def sandbox_create_endpoint(req: Optional[SandboxCreateRequest] = None):
    name = req.sandbox_name if req else None
    return DisposableSandbox.create_sandbox(sandbox_name=name)

@router.post("/sandbox/run")
def sandbox_run_endpoint(req: SandboxRunRequest):
    return DisposableSandbox.run_in_sandbox(
        req.sandbox_id,
        req.command,
        target_guest_os=req.target_guest_os or "auto",
        timeout_seconds=req.timeout_seconds
    )

@router.post("/sandbox/destroy")
def sandbox_destroy_endpoint(req: SandboxDestroyRequest):
    return DisposableSandbox.destroy_sandbox(req.sandbox_id)

@router.post("/skills/teach")
def skills_teach_endpoint(req: SkillTeachRequest):
    return SkillTeachingEngine.teach_skill(
        req.skill_name,
        category=req.category or "cybersecurity_pentesting",
        trigger_keywords=req.trigger_keywords,
        instructions=req.instructions,
        sample_commands=req.sample_commands,
        safety_rules=req.safety_rules or "Authorized testing scope only."
    )

@router.get("/skills/list")
def skills_list_endpoint(category: Optional[str] = Query(None)):
    return {"skills": SkillTeachingEngine.list_taught_skills(category=category)}

@router.post("/skills/execute")
def skills_execute_endpoint(req: SkillExecuteRequest):
    return SkillTeachingEngine.execute_taught_skill(
        req.skill_name,
        target_parameter=req.target_parameter or "",
        run_in_sandbox=req.run_in_sandbox
    )

@router.get("/system/apps")
def get_system_apps_endpoint():
    return SystemAppInventory.scan_installed_applications()

@router.post("/system/apps/scan")
def rescan_system_apps_endpoint():
    return SystemAppInventory.scan_installed_applications()

@router.post("/system/apps/launch")
def launch_system_app_endpoint(req: AppLaunchQueryRequest):
    return SystemAppInventory.launch_any_app(req.app_query)

@router.post("/system/governor/p-cores")
def set_p_cores_endpoint():
    return HardwareGovernor.set_thread_affinity(p_cores_only=True)

@router.get("/system/governor/hardware-tier")
def get_hardware_tier_endpoint():
    return HardwareGovernor.detect_hardware_tier()

@router.post("/system/governor/purge-vram")
def purge_vram_endpoint():
    return HardwareGovernor.purge_vram_and_system_memory()

@router.post("/opsec/spawn-canaries")
def spawn_canaries_endpoint():
    return SecurityCanaryTrap.spawn_canary_honeypots()

@router.post("/opsec/inspect-clipboard")
def inspect_clipboard_endpoint():
    return SecurityCanaryTrap.inspect_clipboard_entropy()

@router.post("/tools/audit-subscriptions")
def audit_subscriptions_endpoint(req: SubscriptionAuditRequest):
    return FinancialLegalWellnessSuite.audit_subscriptions_and_trials(req.subscriptions_list)

@router.post("/tools/audit-tos")
def audit_tos_endpoint(req: ToSAuditRequest):
    return FinancialLegalWellnessSuite.audit_tos_and_privacy_policy(req.policy_text_or_url)

@router.post("/tools/tone-critique")
def tone_critique_endpoint(req: ToneCritiqueRequest):
    return FinancialLegalWellnessSuite.socratic_tone_sounding_board(req.draft_message, recipient_context=req.recipient_context)

@router.post("/tools/generate-anki")
def generate_anki_endpoint(req: AnkiExportRequest):
    return FinancialLegalWellnessSuite.generate_anki_flashcards(req.study_material, deck_name=req.deck_name or "Personal_AI_Knowledge")

@router.post("/agent/self-evolve")
def self_evolve_endpoint(req: SelfEvolveRequest):
    return SelfEvolvingAgent.synthesize_and_hotload_tool(req.task_objective, tool_name_query=req.tool_name_query or "custom_tool")

@router.post("/system/self-heal")
async def trigger_self_heal_endpoint():
    return await AutonomousSelfHealer.run_maintenance_cycle()

@router.post("/cognition/experiment")
def test_experiment_endpoint(req: ExperimentRequest):
    return ExperimentEngine.test_hypothesis_in_sandbox(
        req.hypothesis_name,
        req.command_or_script,
        target_guest_os=req.target_guest_os or "auto"
    )

@router.post("/cognition/synthesize-capability")
def synthesize_capability_endpoint(req: CapabilitySynthesizeRequest):
    return CapabilityFactory.synthesize_capability(
        req.capability_name,
        req.description,
        sample_params=req.sample_params
    )

@router.post("/cognition/simulate-branches")
def simulate_branches_endpoint(req: SimulationRequest):
    return CounterfactualSimulator.simulate_competing_branches(
        req.target_goal,
        req.candidate_actions
    )

@router.post("/cognition/self-play-explore")
def self_play_explore_endpoint():
    return ExperimentEngine.run_self_play_sandbox_exploration()

@router.get("/agent/proactive-greeting")
def proactive_greeting_endpoint():
    return {"proactive_greeting": ProactiveCoworkerDaemon.get_proactive_greeting()}

@router.post("/coder/ast-audit")
def ast_audit_endpoint(req: ASTAuditRequest):
    return ASTJanitor.audit_and_refactor_code(req.file_path)

@router.post("/coder/ast-generate-test")
def ast_generate_test_endpoint(module_query: str = Query(...)):
    return ASTJanitor.generate_pytest_contract(module_query)

# 15. Phase 7 Meta-Learning & RAG Memory Endpoints
@router.post("/memory/rag-search")
def rag_search_endpoint(req: RAGSearchRequest):
    results = SemanticRAGEngine.search_memories(req.query, limit=req.limit)
    context_str = SemanticRAGEngine.build_rag_context(req.query, limit=req.limit)
    return {
        "query": req.query,
        "results_count": len(results),
        "results": results,
        "rag_prompt_context": context_str
    }

@router.post("/memory/reflect")
def task_reflection_endpoint(req: ReflectionRequest):
    return ReflectionEngine.reflect_on_task_execution(
        req.task_title, 
        req.task_goal, 
        req.outcome_summary, 
        user_feedback=req.user_feedback
    )

@router.get("/memory/constitution")
def get_constitution_endpoint():
    return {
        "constitution_summary": DecisionConstitution.get_constitution_summary(),
        "rules": DecisionConstitution.CORE_VALUES
    }

# 16. Upgrades 1, 4, 5, 6: Hardware Monitor, Notifier, Scheduler & Multi-Agent Endpoints
@router.get("/api/hardware-stats")
def get_hardware_stats_endpoint():
    return HardwareMonitor.get_hardware_stats()

@router.post("/system/notify")
def send_notification_endpoint(req: NotificationRequest):
    return SystemNotifier.send_notification(req.title, req.message)

@router.get("/scheduler/jobs")
def list_scheduler_jobs_endpoint():
    return {"jobs": ProactiveScheduler.list_jobs()}

@router.delete("/scheduler/jobs/{job_id}")
def remove_scheduler_job_endpoint(job_id: str):
    success = ProactiveScheduler.remove_job(job_id)
    return {"success": success, "job_id": job_id}

@router.post("/agents/multi-agent-collaborate")
def run_multi_agent_endpoint(req: MultiAgentRequest):
    return MultiAgentTeam.run_collaborative_workflow(req.objective, complexity=req.complexity)

# 17. Deep OS, Android ADB, Universal Filesystem & Data Science Endpoints
@router.get("/android/devices")
def android_list_devices_endpoint():
    return AndroidADBController.list_connected_devices()

@router.post("/android/tap")
def android_tap_endpoint(req: ADBTapRequest):
    return AndroidADBController.tap_screen(req.x, req.y, target_device=req.target_device)

@router.post("/android/type")
def android_type_endpoint(req: ADBTypeTextRequest):
    return AndroidADBController.type_text(req.text, target_device=req.target_device)

@router.post("/android/screenshot")
def android_screenshot_endpoint(target_device: Optional[str] = Query(None)):
    return AndroidADBController.capture_phone_screenshot(target_device=target_device)

@router.post("/android/launch-app")
def android_launch_app_endpoint(req: ADBLaunchAppRequest):
    return AndroidADBController.launch_android_app(req.package_name, target_device=req.target_device)

@router.post("/filesystem/search")
def fs_search_endpoint(req: FileSearchRequest):
    return UniversalFilesystem.search_filesystem(req.query, root_dir=req.root_dir, max_results=req.max_results)

@router.post("/filesystem/move")
def fs_move_endpoint(req: FileMoveRequest):
    return UniversalFilesystem.rename_or_move(req.source_path, req.destination_path)

@router.post("/filesystem/compress")
def fs_compress_endpoint(req: FileCompressRequest):
    return UniversalFilesystem.compress_zip(req.source_paths, req.output_zip_path)

@router.post("/filesystem/resize-image")
def fs_resize_image_endpoint(req: ImageResizeRequest):
    return UniversalFilesystem.resize_image(req.image_path, req.target_width, req.target_height)

@router.post("/filesystem/play-media")
def fs_play_media_endpoint(req: MediaPlayRequest):
    return UniversalFilesystem.play_media_file(req.media_path)

@router.post("/data/analyze")
def data_analyze_endpoint(req: DataAnalyzeRequest):
    return DataAnalysisEngine.analyze_dataset(req.file_path)

@router.post("/data/chart")
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

@router.get("/system/mode")
def get_system_mode_endpoint():
    global SYSTEM_STATE
    return {"system_mode": SYSTEM_STATE}

@router.post("/system/sleep")
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

@router.post("/system/shutdown")
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


# ── Backward-compatible hardened application object ─────────────────────────
# Production should use app.server:app. This compatibility app now enforces the
# same API-key and unauthenticated localhost boundary so launching the old entry
# point cannot expose capability routes accidentally.
async def _legacy_verify_request(request: Request):
    configured = os.getenv("ARENA_API_KEY", "")
    enforced = os.getenv("ARENA_ENFORCE_AUTH", "").lower() in ("1", "true", "yes")
    if not configured:
        if enforced:
            raise HTTPException(status_code=503, detail="Authentication required but ARENA_API_KEY is not set")
        return
    if request.headers.get("X-API-Key", "") != configured:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

app = FastAPI(
    title=settings.APP_NAME,
    description="Compatibility core API; use app.server:app for unified service",
    version="0.1.0",
)

@app.middleware("http")
async def _legacy_localhost_guard(request: Request, call_next):
    configured = bool(os.getenv("ARENA_API_KEY", ""))
    insecure = os.getenv("ARENA_ALLOW_INSECURE_LAN", "").lower() in ("1", "true", "yes")
    host = request.client.host.lower() if request.client and request.client.host else ""
    if not configured and not insecure and host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        return JSONResponse(status_code=403, content={"detail": "Unauthenticated compatibility API is localhost-only"})
    return await call_next(request)

from app.api.owner_control_autonomy import router as _owner_autonomy_router
from app.api.owner_control_autonomy import (  # re-exported for existing callers/tests
    AutonomousGoalDecisionRequest,
    AutonomousGoalPriorityRequest,
    AutonomyEnvelopeUpdate,
    ConcurrencyBudgetUpdate,
    OwnerAutonomousGoalRequest,
    OwnerDecisionRequest,
    PreemptionRequest,
    ScheduledDirectiveRequest,
    ScheduleStatusRequest,
    create_owner_autonomous_goal_endpoint,
    execute_next_autonomous_goal_endpoint,
)
from app.api import owner_control_autonomy as _owner_autonomy  # re-export surface
app.include_router(router, dependencies=[Depends(_legacy_verify_request)])
app.include_router(_owner_autonomy_router, dependencies=[Depends(_legacy_verify_request)])
from app.api.os_browser_automation import router as _os_browser_router
app.include_router(_os_browser_router, dependencies=[Depends(_legacy_verify_request)])
from app.api.self_awareness import router as _self_awareness_router
from app.api.self_awareness import (  # re-exported for existing callers/tests
    ExplicitCommitmentRequest,
    IdentityCheckpointRequest,
    RecoveryActionRequest,
    RecoveryDecisionRequest,
    create_explicit_commitment_endpoint,
    identity_continuity_checkpoint_endpoint,
    self_agency_history_endpoint,
    self_awareness_endpoint,
    self_belief_revisions_endpoint,
    self_commitments_endpoint,
)
app.include_router(_self_awareness_router, dependencies=[Depends(_legacy_verify_request)])
