"""Unified tool capability manifest.

Maps every tool in the system to a canonical `action_type` the cognitive layer
can select and execute. This is the single source of truth that lets the agent
reach ALL tools (not just the ~10 hard-coded in MasterAgentOrchestrator).

Each entry: action_type -> dict(name, category, safety_level, description, handler)
where handler(payload: dict) -> dict.

Safety levels mirror policy.py: 0=read, 1=draft, 2=reversible, 3=sensitive.
"""

from __future__ import annotations

from typing import Any, Callable, Dict


def _wrap(fn: Callable[..., Any], *key_args: str) -> Callable[[Dict[str, Any]], Any]:
    """Adapt a keyword-arg method to a payload-dict handler."""
    def handler(payload: Dict[str, Any]) -> Any:
        kwargs = {k: payload.get(k) for k in key_args if payload.get(k) is not None}
        return fn(**kwargs)
    return handler


def _ignore_payload(fn: Callable[[], Any]) -> Callable[[Dict[str, Any]], Any]:
    """Adapt a zero-arg classmethod/staticmethod to a payload-dict handler.

    ToolRegistry always calls handler(payload); zero-arg methods must drop it.
    """
    def handler(payload: Dict[str, Any]) -> Any:
        return fn()
    return handler


def build_tool_manifest() -> Dict[str, Dict[str, Any]]:
    """Return the full action_type → tool mapping (lazy imports inside)."""
    from app.tools.android_adb_controller import AndroidADBController
    from app.tools.app_inventory import SystemAppInventory
    from app.tools.ast_janitor import ASTJanitor
    from app.tools.browser_automation import BrowserAutomation
    from app.tools.business_growth import BusinessGrowthEngine
    from app.tools.camera_capture import CameraCaptureTool
    from app.tools.coder_brain import CoderBrainTool
    from app.tools.connectors import ConnectorsTool
    from app.tools.content_creator import ContentCreatorTool
    from app.tools.cybersecurity_brain import CybersecurityBrainTool
    from app.tools.daily_briefing import DailyBriefingEngine
    from app.tools.data_analyzer import DataAnalysisEngine
    from app.tools.deep_os_controller import DeepOSController
    from app.tools.desktop_control import DesktopControl
    from app.tools.disposable_sandbox import DisposableSandbox
    from app.tools.doc_manager import DocumentManager
    from app.tools.finance_trader import FinanceTraderTool
    from app.tools.financial_legal_wellness import FinancialLegalWellnessSuite
    from app.tools.git_manager import GitManagerTool
    from app.tools.knowledge_domains import KnowledgeDomainsTool
    from app.tools.knowledge_indexer import KnowledgeIndexer
    from app.tools.location_service import LocationService
    from app.tools.notes_manager import NotesManager
    from app.tools.weather_service import WeatherService
    from app.tools.translator import TranslatorTool
    from app.tools.email_service import EmailService
    from app.tools.sql_query import SQLQueryTool
    from app.tools.calendar_service import CalendarService
    from app.tools.document_generator import DocumentGenerator
    from app.tools.media_studio import MediaStudioTool
    from app.tools.music_studio import MusicStudioTool
    from app.tools.ocr_reader import OCRReaderTool
    from app.tools.opsec_manager import OpSecManagerTool
    from app.tools.pentest_company_assistant import PentestCompanyAssistant
    from app.tools.screen_capture import ScreenCaptureTool
    from app.tools.security_canary import SecurityCanaryTrap
    from app.tools.security_education import SecurityEducationTool
    from app.tools.security_lab import SecurityLabTool
    from app.tools.skill_teaching_engine import SkillTeachingEngine
    from app.tools.universal_filesystem import UniversalFilesystem
    from app.tools.universal_media_learner import UniversalMediaLearner
    from app.tools.vision_analyzer import VisionAnalyzerTool
    from app.tools.web_agent import WebAgent
    from app.tools.web_research import WebResearcher
    from app.tools.win32_ghost_operator import Win32GhostOperator
    from app.tools.workflow_engine import WorkflowEngine
    from app.tools.youtube_learner import YouTubeLearner

    manifest: Dict[str, Dict[str, Any]] = {}

    def add(action: str, category: str, level: int, desc: str, handler: Callable) -> None:
        manifest[action] = {
            "name": action,
            "category": category,
            "safety_level": level,
            "description": desc,
            "handler": handler,
        }

    # ── OS / system ─────────────────────────────────────────────────────────
    add("launch_app", "os_control", 2, "Launch an installed application",
        _wrap(SystemAppInventory.launch_any_app, "app_query", "app_name"))
    add("list_apps", "os_control", 0, "List installed applications",
        _ignore_payload(SystemAppInventory.scan_installed_applications))
    add("mouse_click", "os_control", 2, "Click at screen coordinates",
        _wrap(DeepOSController.mouse_click, "x", "y", "double"))
    add("type_text", "os_control", 2, "Type text into the active window",
        _wrap(DeepOSController.type_text, "text"))
    add("press_hotkey", "os_control", 2, "Press a hotkey combination",
        _wrap(DeepOSController.press_hotkey, "keys"))
    add("open_url", "os_control", 2, "Open a URL in the default browser",
        _wrap(DesktopControl.open_url, "url"))
    add("system_update", "os_control", 3, "Update installed software",
        _wrap(DeepOSController.check_and_update_software, "package_name"))

    # ── Filesystem ──────────────────────────────────────────────────────────
    add("search_files", "filesystem", 0, "Search the filesystem",
        _wrap(UniversalFilesystem.search_filesystem, "query", "root_dir", "max_results"))
    add("move_file", "filesystem", 2, "Rename/move a file",
        _wrap(UniversalFilesystem.rename_or_move, "source_path", "destination_path"))
    add("compress_files", "filesystem", 2, "Compress files to a zip",
        _wrap(UniversalFilesystem.compress_zip, "source_paths", "output_zip_path"))
    add("resize_image", "filesystem", 2, "Resize an image",
        _wrap(UniversalFilesystem.resize_image, "image_path", "target_width", "target_height"))
    add("read_document", "filesystem", 0, "Read a document",
        _wrap(DocumentManager.read_document, "file_path"))
    add("create_document", "filesystem", 1, "Create a document",
        _wrap(DocumentManager.create_document, "file_path", "content"))
    add("list_workspace", "filesystem", 0, "List workspace files",
        _ignore_payload(DocumentManager.list_workspace_files))

    # ── Vision / media ──────────────────────────────────────────────────────
    add("screen_capture", "vision", 0, "Capture the screen",
        _ignore_payload(ScreenCaptureTool.capture_screen_delta))
    add("camera_photo", "vision", 0, "Capture a webcam photo",
        _ignore_payload(CameraCaptureTool.capture_photo))
    add("vision_analyze", "vision", 0, "Analyze an image",
        _wrap(VisionAnalyzerTool.analyze_screen_image, "image_path"))
    add("ocr_read", "vision", 0, "Extract text from an image",
        _wrap(OCRReaderTool.extract_text_from_image, "image_path"))

    # ── Location ────────────────────────────────────────────────────────────
    add("resolve_location", "location", 0, "Resolve geographic location",
        _ignore_payload(LocationService.resolve_location))

    # ── Web / research ──────────────────────────────────────────────────────
    add("web_search", "web", 0, "Search the web",
        _wrap(WebResearcher.search_and_scrape, "query"))
    add("web_workflow", "web", 2, "Run an autonomous multi-step web workflow",
        _wrap(WebAgent.execute_web_workflow, "objective", "target_url", "steps", "complexity"))
    add("browser_extract", "web", 0, "Navigate and extract a page",
        _wrap(BrowserAutomation.navigate_and_extract, "url"))
    add("youtube_learn", "web", 0, "Learn from a YouTube video",
        _wrap(YouTubeLearner.learn_from_video, "video_url"))
    add("media_learn", "web", 0, "Analyze a media target",
        _wrap(UniversalMediaLearner.analyze_media_target, "target"))

    # ── Data / code ─────────────────────────────────────────────────────────
    add("analyze_data", "data", 0, "Analyze a dataset",
        _wrap(DataAnalysisEngine.analyze_dataset, "file_path"))
    add("code_audit", "code", 1, "Audit and refactor code",
        _wrap(ASTJanitor.audit_and_refactor_code, "code", "language"))
    add("generate_tests", "code", 1, "Generate pytest contracts",
        _wrap(ASTJanitor.generate_pytest_contract, "code", "language"))
    add("code_explain", "code", 0, "Explain/debug code",
        _wrap(CoderBrainTool.explain_and_debug_code, "code", "issue"))
    add("git_checkpoint", "code", 2, "Create a git checkpoint",
        _wrap(GitManagerTool.create_checkpoint, "message"))
    add("git_rollback", "code", 3, "Roll back a git checkpoint",
        _wrap(GitManagerTool.rollback_checkpoint, "checkpoint_id"))

    # ── Security ────────────────────────────────────────────────────────────
    add("lab_scan", "security", 3, "Scan an authorized lab target",
        _wrap(SecurityLabTool.scan_lab_target, "target", "ports"))
    add("opsec_audit", "security", 1, "Audit digital footprint",
        _ignore_payload(OpSecManagerTool.audit_digital_footprint))
    add("yara_rule", "security", 1, "Generate a YARA rule",
        _wrap(CybersecurityBrainTool.generate_yara_rule, "description"))
    add("sigma_rule", "security", 1, "Generate a Sigma rule",
        _wrap(CybersecurityBrainTool.generate_sigma_rule, "description"))
    add("pentest_report", "security", 1, "Generate a pentest report",
        _wrap(PentestCompanyAssistant.generate_pentest_report, "target", "findings"))

    # ── Productivity / content ──────────────────────────────────────────────
    add("daily_briefing", "productivity", 0, "Generate a daily briefing",
        _ignore_payload(DailyBriefingEngine.generate_briefing))
    add("content_script", "productivity", 1, "Generate a content script",
        _wrap(ContentCreatorTool.generate_content_script, "topic", "platform", "audience"))
    add("business_opportunities", "productivity", 0, "Discover business opportunities",
        _wrap(BusinessGrowthEngine.discover_opportunities, "niche"))
    add("workflow_execute", "productivity", 2, "Execute a multi-step workflow",
        _wrap(WorkflowEngine.execute_workflow, "workflow_name", "steps"))
    add("finance_calc", "productivity", 0, "Financial calculations",
        _wrap(KnowledgeDomainsTool.accounting_finance_calc, "query"))
    add("subscription_audit", "productivity", 0, "Audit subscriptions/trials",
        _wrap(FinancialLegalWellnessSuite.audit_subscriptions_and_trials, "context"))

    # ── Sandbox ─────────────────────────────────────────────────────────────
    add("sandbox_run", "sandbox", 2, "Run code in a disposable sandbox",
        _wrap(DisposableSandbox.run_in_sandbox, "sandbox_id", "command", "target_guest_os"))

    # ── Phone (ADB) ─────────────────────────────────────────────────────────
    add("phone_command", "phone", 2, "Control a phone via ADB",
        _wrap(AndroidADBController.run_adb_cmd, "args"))
    add("phone_sms", "phone", 3, "Send an SMS",
        _wrap(AndroidADBController.send_sms, "phone_number", "message"))
    add("phone_call", "phone", 3, "Make a phone call",
        _wrap(AndroidADBController.make_phone_call, "phone_number"))
    add("phone_screenshot", "phone", 0, "Capture phone screenshot",
        _ignore_payload(AndroidADBController.capture_phone_screenshot))

    # ── Knowledge / skill ───────────────────────────────────────────────────
    add("index_knowledge", "knowledge", 0, "Index knowledge from a source",
        _wrap(KnowledgeIndexer.index_doc_knowledge, "source", "content"))
    add("teach_skill", "knowledge", 1, "Teach the agent a skill",
        _wrap(SkillTeachingEngine.teach_skill, "skill_name", "steps"))
    add("execute_skill", "knowledge", 2, "Execute a taught skill",
        _wrap(SkillTeachingEngine.execute_taught_skill, "skill_name", "params"))

    # ── Ghost operator / notifications ──────────────────────────────────────
    add("list_windows", "os_control", 0, "List open windows",
        _ignore_payload(Win32GhostOperator.list_open_windows))
    add("trigger_webhook", "integration", 3, "Trigger a webhook",
        _wrap(ConnectorsTool.trigger_webhook, "url", "payload"))

    # ── Coworker essentials (notes / weather / translation / email / SQL /
    #    calendar / documents) ───────────────────────────────────────────────
    add("create_note", "productivity", 1, "Create a note",
        _wrap(NotesManager.create_note, "title", "content", "tags"))
    add("list_notes", "productivity", 0, "List notes",
        _ignore_payload(NotesManager.list_notes))
    add("search_notes", "productivity", 0, "Search notes",
        _wrap(NotesManager.search_notes, "query"))
    add("read_note", "productivity", 0, "Read a note",
        _wrap(NotesManager.read_note, "note_id_or_file"))
    add("weather", "productivity", 0, "Get weather for a city",
        _wrap(WeatherService.get_weather, "city"))
    add("translate", "productivity", 0, "Translate text",
        _wrap(TranslatorTool.translate, "text", "target_language", "source_language"))
    add("send_email", "productivity", 3, "Send an email",
        _wrap(EmailService.send_email, "to", "subject", "body", "cc"))
    add("read_inbox", "productivity", 0, "Read email inbox",
        _ignore_payload(EmailService.read_inbox))
    add("sql_query", "data", 0, "Read-only SQL query (SQLite)",
        _wrap(SQLQueryTool.query_sqlite, "db_path", "sql", "limit"))
    add("sql_query_csv", "data", 0, "Read-only SQL query (CSV)",
        _wrap(SQLQueryTool.query_csv, "csv_path", "sql", "limit"))
    add("add_event", "productivity", 1, "Add a calendar event",
        _wrap(CalendarService.add_event, "title", "start", "end", "location"))
    add("add_reminder", "productivity", 1, "Add a reminder",
        _wrap(CalendarService.add_reminder, "title", "due", "note"))
    add("list_events", "productivity", 0, "List calendar events",
        _ignore_payload(CalendarService.list_events))
    add("due_reminders", "productivity", 0, "List due reminders",
        _ignore_payload(CalendarService.due_reminders))
    add("generate_document", "productivity", 1, "Generate a document from markdown",
        _wrap(DocumentGenerator.generate, "title", "markdown", "fmt"))

    return manifest


# Built lazily and cached at first import to avoid importing every tool module
# until the registry actually needs them.
_TOOL_MANIFEST: Dict[str, Dict[str, Any]] | None = None


def get_tool_manifest() -> Dict[str, Dict[str, Any]]:
    global _TOOL_MANIFEST
    if _TOOL_MANIFEST is None:
        _TOOL_MANIFEST = build_tool_manifest()
    return _TOOL_MANIFEST
