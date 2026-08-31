"""Unified tool capability manifest.

Maps every tool in the system to a canonical `action_type` the cognitive layer
can select and execute. This is the single source of truth that lets the agent
reach ALL tools (not just the ~10 hard-coded in MasterAgentOrchestrator).

Each entry: action_type -> dict(name, category, safety_level, description, handler)
where handler(payload: dict) -> dict.

Safety levels mirror policy.py: 0=read, 1=draft, 2=reversible, 3=sensitive.
"""

from __future__ import annotations

import importlib
from threading import RLock
from typing import Any, Callable, Dict, Optional

from app.utils.logger import app_logger


class ToolDependencyUnavailable(ImportError):
    """A tool module could not load because an optional dependency is absent."""

    def __init__(
        self,
        tool_module: str,
        tool_symbol: str,
        cause: ImportError,
    ) -> None:
        self.tool_module = tool_module
        self.tool_symbol = tool_symbol
        self.missing_dependency = getattr(cause, "name", None)
        detail = str(cause) or cause.__class__.__name__
        super().__init__(
            f"Optional tool {tool_module}.{tool_symbol} is unavailable: {detail}"
        )

    def as_result(self) -> Dict[str, Any]:
        return {
            "success": False,
            "available": False,
            "error_type": "dependency_unavailable",
            "error": str(self),
            "tool_module": self.tool_module,
            "tool_symbol": self.tool_symbol,
            "missing_dependency": self.missing_dependency,
        }


class _LazyImportProxy:
    """Resolve a tool class only when one of its actions is actually invoked.

    Manifest construction intentionally performs no tool-module imports.  A
    missing optional package therefore disables only actions backed by that
    module instead of preventing ToolRegistry or CognitiveRuntime startup.
    """

    def __init__(self, module: str, symbol: str) -> None:
        self.module = module
        self.symbol = symbol
        self._resolved: Optional[Any] = None
        self._load_error: Optional[ToolDependencyUnavailable] = None
        self._lock = RLock()

    def _load(self) -> Any:
        with self._lock:
            if self._resolved is not None:
                return self._resolved
            try:
                self._resolved = getattr(importlib.import_module(self.module), self.symbol)
            except ImportError as exc:
                # _load_error is the LAST observed error (cheap reporting for
                # probe=False), NOT a permanent poison (P0 #6): a dependency
                # installed after the first failure must become visible on the
                # next load attempt, so every call re-attempts the import
                # until it succeeds.
                self._load_error = ToolDependencyUnavailable(
                    self.module, self.symbol, exc
                )
                raise self._load_error from exc
            # A successful (re)load clears the last error: the proxy is now
            # live and must never report a resolved capability unavailable.
            self._load_error = None
            return self._resolved

    def availability(self, *, probe: bool = False) -> Dict[str, Any]:
        if self._resolved is not None:
            return {"available": True, "status": "available"}
        if not probe:
            # Unprobed report: last observed error if any (no import attempt),
            # otherwise honestly not_checked.
            if self._load_error is not None:
                return {
                    "available": False,
                    "status": "dependency_unavailable",
                    "error": str(self._load_error),
                    "missing_dependency": self._load_error.missing_dependency,
                }
            return {"available": None, "status": "not_checked"}
        # probe=True RE-attempts the load even past a previous failure — the
        # dependency may have been installed since (a refresh is a re-probe,
        # never a replay of a stale failure).
        try:
            self._load()
        except ToolDependencyUnavailable as exc:
            return {
                "available": False,
                "status": "dependency_unavailable",
                "error": str(exc),
                "missing_dependency": exc.missing_dependency,
            }
        return {"available": True, "status": "available"}

    def __getattr__(self, method_name: str) -> Callable[..., Any]:
        def invoke(*args: Any, **kwargs: Any) -> Any:
            return getattr(self._load(), method_name)(*args, **kwargs)

        invoke.tool_availability = self.availability  # type: ignore[attr-defined]
        return invoke

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._load()(*args, **kwargs)


def _copy_availability(
    handler: Callable[..., Any], source: Callable[..., Any]
) -> Callable[..., Any]:
    checker = getattr(source, "tool_availability", None)
    if checker is not None:
        handler.tool_availability = checker  # type: ignore[attr-defined]
    return handler


def _wrap(fn: Callable[..., Any], *key_args: str) -> Callable[[Dict[str, Any]], Any]:
    """Adapt a keyword-arg method to a payload-dict handler."""
    def handler(payload: Dict[str, Any]) -> Any:
        kwargs = {k: payload.get(k) for k in key_args if payload.get(k) is not None}
        try:
            return fn(**kwargs)
        except ToolDependencyUnavailable as exc:
            return exc.as_result()
    return _copy_availability(handler, fn)


def _ignore_payload(fn: Callable[[], Any]) -> Callable[[Dict[str, Any]], Any]:
    """Adapt a zero-arg classmethod/staticmethod to a payload-dict handler.

    ToolRegistry always calls handler(payload); zero-arg methods must drop it.
    """
    def handler(payload: Dict[str, Any]) -> Any:
        try:
            return fn()
        except ToolDependencyUnavailable as exc:
            return exc.as_result()
    return _copy_availability(handler, fn)


def build_tool_manifest() -> Dict[str, Dict[str, Any]]:
    """Return the full action_type → tool mapping (lazy imports inside)."""
    AndroidADBController = _LazyImportProxy("app.tools.android_adb_controller", "AndroidADBController")
    SystemAppInventory = _LazyImportProxy("app.tools.app_inventory", "SystemAppInventory")
    ASTJanitor = _LazyImportProxy("app.tools.ast_janitor", "ASTJanitor")
    BrowserAutomation = _LazyImportProxy("app.tools.browser_automation", "BrowserAutomation")
    BusinessGrowthEngine = _LazyImportProxy("app.tools.business_growth", "BusinessGrowthEngine")
    CameraCaptureTool = _LazyImportProxy("app.tools.camera_capture", "CameraCaptureTool")
    CoderBrainTool = _LazyImportProxy("app.tools.coder_brain", "CoderBrainTool")
    ConnectorsTool = _LazyImportProxy("app.tools.connectors", "ConnectorsTool")
    ContentCreatorTool = _LazyImportProxy("app.tools.content_creator", "ContentCreatorTool")
    CybersecurityBrainTool = _LazyImportProxy("app.tools.cybersecurity_brain", "CybersecurityBrainTool")
    DailyBriefingEngine = _LazyImportProxy("app.tools.daily_briefing", "DailyBriefingEngine")
    DataAnalysisEngine = _LazyImportProxy("app.tools.data_analyzer", "DataAnalysisEngine")
    DeepOSController = _LazyImportProxy("app.tools.deep_os_controller", "DeepOSController")
    PrivilegeInspectorTool = _LazyImportProxy("app.tools.privilege_inspector", "PrivilegeInspectorTool")
    DisplayTopologyTool = _LazyImportProxy("app.tools.display_topology", "DisplayTopologyTool")
    AccessibilityControlTool = _LazyImportProxy("app.tools.accessibility_control", "AccessibilityControlTool")
    DesktopControl = _LazyImportProxy("app.tools.desktop_control", "DesktopControl")

    def _os_control_execute(plan):
        """Manifest handler: execute an OSActionPlan dict."""
        from app.cognition.os_control_planner import OSActionPlan, execute_os_plan
        if isinstance(plan, dict):
            parsed = OSActionPlan(**{k: v for k, v in plan.items()
                                     if k in OSActionPlan.__dataclass_fields__})
            return execute_os_plan(parsed)
        return {"success": False, "error": "plan dict required"}

    def _os_control_plan_route(request, query, user_text, goal_text):
        """Manifest handler for the ROUTING SIGNAL name itself.

        Live bug (owner audit 2026-08-28): a proposal with action_type
        'os_control_plan' reached the gate, which didn't know the name and
        blocked it as 'Unknown action' — approving it would then have failed
        as 'unsupported capability'. os_control_plan is a routing signal that
        the runtime normally converts to os_control_execute BEFORE proposing;
        this alias makes any leak safe: gate sees a known Level-2 tool, and
        execution plans + executes the request through the normal planner.
        """
        from app.cognition.os_control_planner import plan_os_action, execute_os_plan
        request_text = request or query or user_text or goal_text
        if not request_text:
            return {
                "success": False,
                "error": "os_control_plan needs the request text "
                         "(payload keys: request/query/user_text)",
            }
        plan = plan_os_action(request_text)
        if plan is None:
            return {
                "success": False,
                "error": f"OS-control planner could not produce a command for: {request_text}",
            }
        return execute_os_plan(plan)
    DisposableSandbox = _LazyImportProxy("app.tools.disposable_sandbox", "DisposableSandbox")
    DocumentManager = _LazyImportProxy("app.tools.doc_manager", "DocumentManager")
    FinanceTraderTool = _LazyImportProxy("app.tools.finance_trader", "FinanceTraderTool")
    FinancialLegalWellnessSuite = _LazyImportProxy("app.tools.financial_legal_wellness", "FinancialLegalWellnessSuite")
    GitManagerTool = _LazyImportProxy("app.tools.git_manager", "GitManagerTool")
    KnowledgeDomainsTool = _LazyImportProxy("app.tools.knowledge_domains", "KnowledgeDomainsTool")
    KnowledgeIndexer = _LazyImportProxy("app.tools.knowledge_indexer", "KnowledgeIndexer")
    LocationService = _LazyImportProxy("app.tools.location_service", "LocationService")
    NotesManager = _LazyImportProxy("app.tools.notes_manager", "NotesManager")
    WeatherService = _LazyImportProxy("app.tools.weather_service", "WeatherService")
    TranslatorTool = _LazyImportProxy("app.tools.translator", "TranslatorTool")
    EmailService = _LazyImportProxy("app.tools.email_service", "EmailService")
    SQLQueryTool = _LazyImportProxy("app.tools.sql_query", "SQLQueryTool")
    DatabaseConnector = _LazyImportProxy("app.tools.database_connector", "DatabaseConnector")
    InvoiceGenerator = _LazyImportProxy("app.tools.invoice_generator", "InvoiceGenerator")
    NetworkDiagnostics = _LazyImportProxy("app.tools.network_diagnostics", "NetworkDiagnostics")
    BudgetTracker = _LazyImportProxy("app.tools.budget_tracker", "BudgetTracker")
    BackupManager = _LazyImportProxy("app.tools.backup_manager", "BackupManager")
    crypto_vault = _LazyImportProxy("app.tools.crypto_vault", "crypto_vault")  # singleton instance
    _binary_analyze = _LazyImportProxy("app.tools.binary_analyzer", "analyze_binary")
    _binary_strings = _LazyImportProxy("app.tools.binary_analyzer", "extract_strings")
    PresentationGenerator = _LazyImportProxy("app.tools.presentation_generator", "PresentationGenerator")
    PackageInstaller = _LazyImportProxy("app.tools.package_installer", "PackageInstaller")
    RssAggregator = _LazyImportProxy("app.tools.rss_aggregator", "RssAggregator")
    FactChecker = _LazyImportProxy("app.tools.fact_checker", "FactChecker")
    PriceLookup = _LazyImportProxy("app.tools.price_lookup", "PriceLookup")
    Messaging = _LazyImportProxy("app.tools.messaging", "Messaging")
    Recipes = _LazyImportProxy("app.tools.recipes", "Recipes")
    PdfToolkit = _LazyImportProxy("app.tools.pdf_toolkit", "PdfToolkit")
    ProcessManager = _LazyImportProxy("app.tools.process_manager", "ProcessManager")
    CalendarService = _LazyImportProxy("app.tools.calendar_service", "CalendarService")
    DocumentGenerator = _LazyImportProxy("app.tools.document_generator", "DocumentGenerator")
    LocalExecutor = _LazyImportProxy("app.tools.local_executor", "LocalExecutor")
    ContactsTool = _LazyImportProxy("app.tools.contacts", "ContactsTool")
    SpreadsheetTool = _LazyImportProxy("app.tools.spreadsheet", "SpreadsheetTool")
    CodingAgent = _LazyImportProxy("app.agents.coding_agent", "CodingAgent")
    DataAnalysisAgent = _LazyImportProxy("app.agents.data_analysis_agent", "DataAnalysisAgent")
    MediaStudioTool = _LazyImportProxy("app.tools.media_studio", "MediaStudioTool")
    MusicStudioTool = _LazyImportProxy("app.tools.music_studio", "MusicStudioTool")
    OCRReaderTool = _LazyImportProxy("app.tools.ocr_reader", "OCRReaderTool")
    OpSecManagerTool = _LazyImportProxy("app.tools.opsec_manager", "OpSecManagerTool")
    PentestCompanyAssistant = _LazyImportProxy("app.tools.pentest_company_assistant", "PentestCompanyAssistant")
    ScreenCaptureTool = _LazyImportProxy("app.tools.screen_capture", "ScreenCaptureTool")
    SecurityCanaryTrap = _LazyImportProxy("app.tools.security_canary", "SecurityCanaryTrap")
    SecurityEducationTool = _LazyImportProxy("app.tools.security_education", "SecurityEducationTool")
    SecurityLabTool = _LazyImportProxy("app.tools.security_lab", "SecurityLabTool")
    SkillTeachingEngine = _LazyImportProxy("app.tools.skill_teaching_engine", "SkillTeachingEngine")
    UniversalFilesystem = _LazyImportProxy("app.tools.universal_filesystem", "UniversalFilesystem")
    UniversalMediaLearner = _LazyImportProxy("app.tools.universal_media_learner", "UniversalMediaLearner")
    VisionAnalyzerTool = _LazyImportProxy("app.tools.vision_analyzer", "VisionAnalyzerTool")
    ObjectDetectorTool = _LazyImportProxy("app.tools.object_detector", "ObjectDetectorTool")
    ProsodyAnalyzerTool = _LazyImportProxy("app.tools.prosody_analyzer", "ProsodyAnalyzerTool")
    VlmAnalyzerTool = _LazyImportProxy("app.tools.vlm_analyzer", "VlmAnalyzerTool")
    LoraManagerTool = _LazyImportProxy("app.tools.lora_manager", "LoraManagerTool")
    WebAgent = _LazyImportProxy("app.tools.web_agent", "WebAgent")
    WebResearcher = _LazyImportProxy("app.tools.web_research", "WebResearcher")
    Win32GhostOperator = _LazyImportProxy("app.tools.win32_ghost_operator", "Win32GhostOperator")
    WorkflowEngine = _LazyImportProxy("app.tools.workflow_engine", "WorkflowEngine")
    YouTubeLearner = _LazyImportProxy("app.tools.youtube_learner", "YouTubeLearner")

    manifest: Dict[str, Dict[str, Any]] = {}

    def add(action: str, category: str, level: int, desc: str, handler: Callable) -> None:
        checker = getattr(handler, "tool_availability", None)
        manifest[action] = {
            "name": action,
            "category": category,
            "safety_level": level,
            "description": desc,
            "handler": handler,
            # None means this is an in-manifest/custom/plugin handler rather
            # than a lazily imported optional tool module.
            "availability": checker,
        }

    def _list_capabilities():
        """Manifest handler: the agent's real tool inventory (Level 0).

        'Can you access my computer / use it for tasks?' kept getting 'I
        don't have access' apologies from the small model. The honest answer
        is an observable fact: enumerate the registered tool manifest.
        """
        try:
            from app.tools.manifest import get_tool_manifest
            manifest = get_tool_manifest()
        except Exception as exc:
            return {"success": False, "error": f"Could not read tool manifest: {exc}"}
        categories: Dict[str, list] = {}
        for action, entry in manifest.items():
            categories.setdefault(str(entry.get("category", "other")), []).append(action)
        return {
            "success": True,
            "tool_count": len(manifest),
            "categories": {cat: sorted(names) for cat, names in sorted(categories.items())},
        }

    # ── OS / system ─────────────────────────────────────────────────────────
    _list_caps_handler = _ignore_payload(_list_capabilities)
    # Explicitly probe-free (follow-up review #5): in-process
    # self-introspection over the tool inventory — no external dependency
    # to probe, available by construction. The value is the
    # NO_PROBE_REQUIRED sentinel consumed by interpret_availability
    # (app.cognition.tool_registry); the linkage is pinned by tests.
    _list_caps_handler.tool_availability = "no_probe_required"
    add("list_capabilities", "self_awareness", 0, "Enumerate the agent's registered tool inventory (evidence for capability questions)",
        _list_caps_handler)
    add("launch_app", "os_control", 2, "Launch an installed application",
        _wrap(SystemAppInventory.launch_any_app, "app_query", "app_name"))
    add("list_apps", "os_control", 0, "List installed applications",
        _ignore_payload(SystemAppInventory.scan_installed_applications))
    add("mouse_click", "os_control", 3, "Grounded raw-coordinate click: requires window/process grounding ID, fresh display-topology digest and immediate re-observation",
        _wrap(DeepOSController.mouse_click, "x", "y", "double", "grounding_id", "expected_topology_sha256"))
    add("type_text", "os_control", 3, "Grounded raw typing into an exactly grounded window: requires grounding ID, fresh topology digest and immediate re-observation",
        _wrap(DeepOSController.type_text, "text", "grounding_id", "expected_topology_sha256"))
    add("press_hotkey", "os_control", 3, "Grounded raw hotkey into an exactly grounded window: requires grounding ID, fresh topology digest and immediate re-observation",
        _wrap(DeepOSController.press_hotkey, "keys", "grounding_id", "expected_topology_sha256"))
    add("os_control_execute", "os_control", 2, "Execute a planned OS settings command (LLM-planned, gate-approved, verified); handles ANY OS action cross-platform",
        _wrap(_os_control_execute, "plan")),
    add("os_control_plan", "os_control", 2, "Routing alias: plan and execute a general OS-control request (settings, taskbar, icons) via the LLM planner",
        _wrap(_os_control_plan_route, "request", "query", "user_text", "goal_text")),

    add("set_wallpaper", "os_control", 2, "Set the desktop wallpaper from an image file; verified by re-reading, reversible via the previous wallpaper path",
        _wrap(DesktopControl.set_wallpaper, "image_path", "path"))
    add("open_url", "os_control", 2, "Open a URL in the default browser",
        _wrap(DesktopControl.open_url, "url"))
    add("display_topology", "os_control", 0, "Capture physical multi-monitor topology",
        _ignore_payload(DisplayTopologyTool.capture))
    add("display_scale", "os_control", 0, "Attach verified DPI scale evidence to a display",
        _wrap(DisplayTopologyTool.ingest_verified_scale, "display_id", "scale", "evidence"))
    add("display_transform", "os_control", 0, "Transform window-local coordinates using verified display scale",
        _wrap(DisplayTopologyTool.transform_window_point, "display_id", "window_region", "local_x", "local_y"))
    add("accessibility_status", "os_control", 0, "Check native semantic accessibility adapter availability",
        _ignore_payload(AccessibilityControlTool.status))
    add("accessibility_capture", "os_control", 0, "Capture a bounded native accessibility tree",
        _wrap(AccessibilityControlTool.capture_desktop, "window_id", "max_nodes"))
    add("accessibility_ingest", "os_control", 0, "Ingest an observed accessibility-tree snapshot",
        _wrap(AccessibilityControlTool.ingest_snapshot, "nodes", "interface", "window_id", "evidence"))
    add("accessibility_resolve", "os_control", 0, "Resolve one unique semantic UI target",
        _wrap(AccessibilityControlTool.resolve_target, "role", "name", "window_id"))
    add("accessibility_activate", "os_control", 2, "Activate a uniquely grounded semantic UI target",
        _wrap(AccessibilityControlTool.activate_target, "role", "name", "window_id"))
    add("system_update", "os_control", 3, "Update installed software and verify installed version when observable",
        _wrap(DeepOSController.check_and_update_software, "package_name", "expected_version"))

    # ── Filesystem ──────────────────────────────────────────────────────────
    add("list_directory", "filesystem", 0, "Read-only listing of directory entries (evidence for host-state questions)",
        _wrap(UniversalFilesystem.list_directory, "directories", "include_hidden"))
    add("search_files", "filesystem", 0,
        "Search the filesystem (default: ALL user files across drives; narrow with an explicit "
        "scope — workspace/home/desktop/documents/downloads/music/pictures/videos/all_user_files — "
        "when the user names a location)",
        _wrap(UniversalFilesystem.search_filesystem, "query", "root_dir", "scope", "max_results"))
    add("move_file", "filesystem", 2, "Rename/move a file",
        _wrap(UniversalFilesystem.rename_or_move, "source_path", "destination_path"))
    add("copy_file_verified", "filesystem", 2, "Copy a file without overwrite and verify its hash",
        _wrap(UniversalFilesystem.copy_file_verified, "source_path", "destination_path"))
    add("remove_verified_copy", "filesystem", 3, "Remove an exact unchanged copied artifact",
        _wrap(UniversalFilesystem.remove_verified_copy, "file_path", "expected_sha256"))
    add("delete_files", "filesystem", 3, "Reversible delete: send named files to a recoverable trash area under the home directory (owner approval required)",
        _wrap(UniversalFilesystem.trash_files, "file_paths", "paths", "trash_root"))
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

    # ── PDF toolkit ─────────────────────────────────────────────────────────
    add("pdf_merge", "documents", 2, "Merge multiple PDFs into one",
        _wrap(PdfToolkit.merge_pdfs, "input_paths", "output_path"))
    add("pdf_split", "documents", 2, "Split a PDF into multiple PDFs",
        _wrap(PdfToolkit.split_pdf, "file_path", "output_dir", "pages_per_split"))
    add("pdf_extract_pages", "documents", 2, "Extract specific pages into a new PDF",
        _wrap(PdfToolkit.extract_pages, "file_path", "pages", "output_path"))
    add("pdf_fill_form", "documents", 2, "Fill PDF AcroForm fields",
        _wrap(PdfToolkit.fill_form, "file_path", "field_values", "output_path"))
    add("pdf_metadata", "documents", 0, "Read PDF page count and metadata",
        _wrap(PdfToolkit.get_metadata, "file_path"))
    add("pdf_extract_text", "documents", 0, "Extract text from a PDF",
        _wrap(PdfToolkit.extract_text, "file_path", "page", "max_chars"))

    # ── Process manager ─────────────────────────────────────────────────────
    add("privilege_status", "system", 0, "Inspect current OS privilege without elevation",
        _ignore_payload(PrivilegeInspectorTool.privilege_status))
    add("process_ownership", "system", 0, "Inspect process owner and Arena launch provenance",
        _wrap(PrivilegeInspectorTool.process_ownership, "pid"))
    add("list_processes", "system", 0, "List local processes (CPU/RAM)",
        _wrap(ProcessManager.list_processes, "filter", "limit", "sort_by"))
    add("get_process", "system", 0, "Inspect a process by PID",
        _wrap(ProcessManager.get_process, "pid"))
    add("terminate_process_verified", "system", 3, "Terminate one exact observed process instance and verify it stopped",
        _wrap(ProcessManager.terminate_verified, "pid", "expected_create_time", "expected_executable_path", "force"))
    add("kill_process", "system", 3, "Terminate/force-kill a process (irreversible, legacy PID-only path)",
        _wrap(ProcessManager.kill_process, "pid", "force"))
    add("restart_process", "system", 3, "Restart a process (irreversible)",
        _wrap(ProcessManager.restart_process, "pid"))

    # ── System diagnostics (P0 #8): the read-only probes a performance or
    # stability complaint needs. A matcher cannot discover capabilities that
    # do not exist — these complete the standard diagnostic tree
    # (metrics, thermals, network activity, startup inventory, system logs)
    # as Level-0 observations with honest per-metric platform status.
    SystemDiagnostics = _LazyImportProxy("app.tools.system_diagnostics", "SystemDiagnostics")
    add("system_metrics", "system", 0,
        "System performance metrics: CPU load per core, memory and swap pressure, disk usage and disk IO, uptime, top processes",
        _wrap(SystemDiagnostics.system_metrics, "interval", "top"))
    add("temperature_status", "system", 0,
        "CPU/thermal sensor temperatures (honest platform support; throttling risk flag)",
        _wrap(SystemDiagnostics.temperature))
    add("network_activity", "system", 0,
        "Local network activity: throughput counters since boot, active connections, top remote endpoints",
        _wrap(SystemDiagnostics.network_activity, "top"))
    add("startup_programs", "system", 0,
        "Startup programs and enabled services inventory (boot/login autostart)",
        _wrap(SystemDiagnostics.startup_programs))
    add("recent_logs", "system", 0,
        "Recent system log tail (journalctl / syslog / Event Log) with per-source status",
        _wrap(SystemDiagnostics.recent_logs, "lines", "source"))

    # ── Vision / media ──────────────────────────────────────────────────────
    add("screen_capture", "vision", 0, "Capture the screen",
        _ignore_payload(ScreenCaptureTool.capture_screen_delta))
    add("camera_photo", "vision", 0, "Capture a webcam photo",
        _ignore_payload(CameraCaptureTool.capture_photo))
    add("vision_analyze", "vision", 0, "Analyze an image",
        _wrap(VisionAnalyzerTool.analyze_screen_image, "image_path"))
    add("ocr_read", "vision", 0, "Extract text from an image",
        _wrap(OCRReaderTool.extract_text_from_image, "image_path"))
    add("detect_objects", "vision", 0, "Detect objects in an image (YOLO/SSD/face fallback) + auto-grounding",
        _wrap(ObjectDetectorTool.detect_objects, "image_path", "conf_threshold"))
    add("detect_faces", "vision", 0, "Detect faces in an image (Haar cascade)",
        _wrap(ObjectDetectorTool.detect_faces, "image_path"))
    add("analyze_image_grounded", "vision", 0, "Detect objects + create language groundings (perception→grounding loop)",
        _wrap(ObjectDetectorTool.analyze_image_grounded, "image_path", "auto_create_groundings"))
    add("analyze_prosody", "audio", 0, "Analyze voice prosody (pitch, energy, rate) → emotion from real signals",
        _wrap(ProsodyAnalyzerTool.analyze_file, "file_path", "sample_rate"))
    add("vlm_analyze", "vision", 0, "True VLM analysis (Moondream2/Llava) with OCR+LLM fallback — true visual understanding",
        _wrap(VlmAnalyzerTool.analyze_image, "image_path", "prompt", "max_tokens"))
    add("vlm_status", "vision", 0, "Check VLM availability (Moondream2/Llava) — honest status",
        _ignore_payload(VlmAnalyzerTool.get_status))
    # LoRA continual learning (P2 AGI)
    add("list_loras", "learning", 0, "List LoRA adapters (continual learning without forgetting)",
        _ignore_payload(LoraManagerTool.list_adapters))
    add("lora_status", "learning", 0, "Get LoRA system status (adapters, active, datasets)",
        _ignore_payload(LoraManagerTool.get_status))
    add("activate_lora", "learning", 2, "Activate a LoRA adapter (reversible)",
        _wrap(LoraManagerTool.activate_adapter, "adapter_name"))
    add("deactivate_lora", "learning", 1, "Deactivate LoRA adapter — use base model",
        _ignore_payload(LoraManagerTool.deactivate_adapter))
    add("prepare_lora_dataset", "learning", 1, "Prepare dataset for LoRA training from examples",
        _wrap(LoraManagerTool.prepare_dataset, "skill_name", "examples"))
    add("create_lora_job", "learning", 1, "Create LoRA training job config (scaffolding)",
        _wrap(LoraManagerTool.create_training_job, "adapter_name", "base_model", "skill_name", "r", "lora_alpha", "epochs", "learning_rate"))

    # ── Location ────────────────────────────────────────────────────────────
    add("resolve_location", "location", 0, "Resolve geographic location",
        _ignore_payload(LocationService.resolve_location))

    # ── Web / research ──────────────────────────────────────────────────────
    add("web_search", "web", 0, "Search the web",
        _wrap(WebResearcher.search_and_scrape, "query"))
    add("web_workflow", "web", 2, "Run an autonomous multi-step web workflow",
        _wrap(WebAgent.execute_web_workflow, "objective", "target_url", "steps", "complexity"))
    add("browser_extract", "web", 0, "Navigate and extract a page (use_profile reuses the owner login session)",
        _wrap(BrowserAutomation.navigate_and_extract, "url", "use_profile"))
    add("browser_session_open", "web", 2, "Open a visible browser with the persistent owner profile for one-time logins",
        _wrap(BrowserAutomation.open_session, "url", "headless"))
    add("browser_session_close", "web", 1, "Close the open owner profile session, persisting login state",
        _ignore_payload(BrowserAutomation.close_session))
    add("browser_download", "web", 2, "Disk-reserved, in-flight-cancellable download verified by path/hash",
        _wrap(BrowserAutomation.download_file, "url", "click_selector", "expected_size_bytes", "use_profile"))
    add("browser_upload", "web", 3, "In-flight-cancellable upload with observed success selector",
        _wrap(BrowserAutomation.upload_file, "url", "input_selector", "file_path", "submit_selector", "success_selector", "use_profile"))
    add("browser_delete_upload", "web", 3, "Owner-adapter service-specific deletion of an uploaded receipt, confirmed by observation",
        _wrap(BrowserAutomation.delete_uploaded_file, "service_id", "receipt_id"))
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
    add("clipboard_inspect", "security", 0, "Inspect clipboard entropy without changing content",
        _ignore_payload(SecurityCanaryTrap.inspect_clipboard_entropy))
    add("clipboard_clear_sensitive", "security", 3, "Clear sensitive-looking clipboard and verify empty state",
        _ignore_payload(SecurityCanaryTrap.clear_sensitive_clipboard))
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
        _wrap(ContentCreatorTool.generate_content_script, "topic", "platform", "target_audience"))
    add("generate_content", "productivity", 1, "Generate content (any supported type)",
        _wrap(ContentCreatorTool.generate_content, "topic", "content_type", "target_audience", "tone", "auto_save"))
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
    add("db_query", "data", 0, "Read-only SQL query (Postgres/MySQL/SQLite)",
        _wrap(DatabaseConnector.query, "engine", "sql", "host", "port", "database", "user", "password", "limit"))
    add("db_list_tables", "data", 0, "List tables in a database",
        _wrap(DatabaseConnector.list_tables, "engine", "host", "port", "database", "user", "password"))
    add("db_execute", "data", 3, "Run a write SQL statement (irreversible; requires approval)",
        _wrap(DatabaseConnector.execute, "engine", "sql", "host", "port", "database", "user", "password",
              "allow_unfiltered", "allow_destructive", "limit"))
    add("generate_invoice", "documents", 1, "Generate a PDF invoice/quote/receipt",
        _wrap(InvoiceGenerator.generate_invoice, "to_name", "line_items", "from_name",
              "invoice_number", "date", "currency", "tax_rate", "notes", "document_type", "output_path"))

    # ── Network diagnostics ─────────────────────────────────────────────────
    add("resolve_dns", "network", 0, "Resolve a hostname to IP addresses",
        _wrap(NetworkDiagnostics.resolve_dns, "host"))
    add("check_port", "network", 0, "Check if a TCP port is open",
        _wrap(NetworkDiagnostics.check_port, "host", "port", "timeout"))
    add("ping", "network", 0, "Ping a host",
        _wrap(NetworkDiagnostics.ping, "host", "count", "timeout"))
    add("traceroute", "network", 0, "Trace the route to a host",
        _wrap(NetworkDiagnostics.traceroute, "host", "max_hops"))
    add("whois", "network", 0, "Look up domain WHOIS info",
        _wrap(NetworkDiagnostics.whois, "domain", "timeout"))

    # ── Budget tracker ──────────────────────────────────────────────────────
    add("add_transaction", "finance", 2, "Add an income/expense transaction to the ledger",
        _wrap(BudgetTracker.add_transaction, "amount", "category", "description", "date", "kind", "file_path"))
    add("budget_summary", "finance", 0, "Summarize income/expense/overspend",
        _wrap(BudgetTracker.summary, "file_path", "month", "budgets"))
    add("list_transactions", "finance", 0, "List ledger transactions",
        _wrap(BudgetTracker.list_transactions, "file_path", "category", "month", "limit"))

    # ── Binary structure analysis (triage; not disassembly) ─────────────────
    add("binary_analyze", "system", 0, "Identify a binary and parse ELF/PE/Mach-O headers, sections, and hashes",
        _wrap(_binary_analyze, "path"))
    add("binary_strings", "system", 0, "Extract ASCII/UTF-16LE strings from a file (extraction only, nothing inferred)",
        _wrap(_binary_strings, "path", "min_length", "limit"))

    # ── Encrypted vault (owner secrets & messages) ──────────────────────────
    add("vault_status", "system", 0, "Vault state: initialized, item count, KDF/cipher parameters (no secrets)",
        _ignore_payload(crypto_vault.status))
    add("vault_initialize", "system", 2, "Initialize the encrypted vault with an owner passphrase (master key never stored)",
        _wrap(crypto_vault.initialize, "passphrase"))
    add("vault_encrypt_item", "system", 2, "Encrypt and store one secret under a name (overwrite requires explicit flag)",
        _wrap(crypto_vault.encrypt_item, "name", "plaintext", "passphrase", "overwrite"))
    add("vault_decrypt_item", "system", 2, "Decrypt one stored secret with the vault passphrase",
        _wrap(crypto_vault.decrypt_item, "name", "passphrase"))
    add("vault_list_items", "system", 0, "List stored vault items (names/metadata only, never plaintext)",
        _ignore_payload(crypto_vault.list_items))
    add("vault_delete_item", "system", 3, "Permanently delete one stored secret",
        _wrap(crypto_vault.delete_item, "name"))
    add("vault_rotate_passphrase", "system", 2, "Re-key the vault and re-encrypt every item under a new passphrase",
        _wrap(crypto_vault.rotate_passphrase, "old_passphrase", "new_passphrase"))
    add("vault_encrypt_message", "system", 1, "Statelessly encrypt a message into an armored blob (nothing stored)",
        _wrap(crypto_vault.encrypt_message, "plaintext", "passphrase"))
    add("vault_decrypt_message", "system", 1, "Decrypt an Arena V1 armored message with the passphrase",
        _wrap(crypto_vault.decrypt_message, "armored", "passphrase"))

    # ── Backup & restore ────────────────────────────────────────────────────
    add("create_backup", "system", 1, "Create a versioned backup snapshot",
        _wrap(BackupManager.create_backup, "sources", "name"))
    add("list_backups", "system", 0, "List backup snapshots",
        _ignore_payload(BackupManager.list_backups))
    add("verify_backup", "system", 0, "Verify a backup's integrity (SHA-256)",
        _wrap(BackupManager.verify_backup, "backup_id"))
    add("restore_backup", "system", 2, "Restore a backup only into an empty destination",
        _wrap(BackupManager.restore_backup, "backup_id", "dest_dir", "overwrite"))
    add("restore_backup_overwrite", "system", 3, "Restore a backup with destination overwrite; pre_snapshot captures the overwritten files first",
        _wrap(BackupManager.restore_backup_overwrite, "backup_id", "dest_dir", "pre_snapshot"))
    add("delete_backup", "system", 3, "Delete a backup (irreversible)",
        _wrap(BackupManager.delete_backup, "backup_id"))

    # ── Presentation generator ──────────────────────────────────────────────
    add("generate_presentation", "documents", 1, "Generate a .pptx from an outline",
        _wrap(PresentationGenerator.generate_presentation, "title", "slides", "output_path", "subtitle", "author"))

    # ── Package installer ───────────────────────────────────────────────────
    add("list_packages", "system", 0, "List installed pip/npm packages",
        _wrap(PackageInstaller.list_packages, "manager"))
    add("check_package", "system", 0, "Check if a package is installed",
        _wrap(PackageInstaller.check_package, "package", "manager"))
    add("install_package", "system", 3, "Install a package (irreversible; requires approval)",
        _wrap(PackageInstaller.install_package, "package", "manager", "upgrade"))
    add("uninstall_package", "system", 3, "Uninstall a package (irreversible; requires approval)",
        _wrap(PackageInstaller.uninstall_package, "package", "manager"))

    # ── News/RSS aggregator ─────────────────────────────────────────────────
    add("fetch_feed", "web", 0, "Fetch and parse an RSS/Atom feed",
        _wrap(RssAggregator.fetch_feed, "url", "limit", "timeout"))
    add("summarize_feed", "web", 0, "Fetch a feed and summarize its items",
        _wrap(RssAggregator.summarize_feed, "url", "limit"))

    # ── Fact-check / citation ───────────────────────────────────────────────
    add("fact_check", "web", 0, "Assess a claim against web sources with citations",
        _wrap(FactChecker.fact_check, "claim", "max_results"))

    # ── Price / portfolio lookup ────────────────────────────────────────────
    add("crypto_price", "finance", 0, "Get a cryptocurrency price (CoinGecko)",
        _wrap(PriceLookup.get_crypto_price, "coin_id", "currency"))
    add("stock_price", "finance", 0, "Get a stock quote (Stooq)",
        _wrap(PriceLookup.get_stock_price, "symbol"))

    # ── Messaging ───────────────────────────────────────────────────────────
    add("send_telegram", "messaging", 3, "Send a Telegram message (requires approval)",
        _wrap(Messaging.send_telegram, "message", "chat_id"))
    add("send_whatsapp", "messaging", 3, "Send a WhatsApp message (requires approval)",
        _wrap(Messaging.send_whatsapp, "message", "to"))

    # ── Recipes (deterministic multi-step composition) ──────────────────────
    add("portfolio_snapshot", "recipe", 0, "Value a portfolio of stocks/cryptos in one call",
        _wrap(Recipes.portfolio_snapshot, "holdings"))
    add("data_story", "recipe", 1, "Inspect a dataset and produce a chart in one call",
        _wrap(Recipes.data_story, "file_path", "x_col", "y_col", "chart_type", "chart_title"))
    add("research_digest", "recipe", 0, "Search the web and digest the top sources",
        _wrap(Recipes.research_digest, "query", "max_results"))
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

    # ── Generic local executor (the "escape hatch") ─────────────────────────
    add("local_execute", "integration", 3, "Run a local command/script/localhost request",
        _wrap(LocalExecutor.execute, "action", "command", "code", "url", "method", "body", "timeout_seconds"))

    # ── Deterministic coworker tools (no LLM — exact results) ───────────────
    add("add_contact", "productivity", 1, "Add/update a contact",
        _wrap(ContactsTool.add_contact, "name", "phone", "email", "company", "notes"))
    add("list_contacts", "productivity", 0, "List/search contacts",
        _wrap(ContactsTool.list_contacts, "query"))
    add("delete_contact", "productivity", 2, "Delete a contact",
        _wrap(ContactsTool.delete_contact, "contact_id"))
    add("import_contacts_csv", "productivity", 1, "Import contacts from CSV",
        _wrap(ContactsTool.import_csv, "csv_path"))
    add("export_contacts_csv", "productivity", 0, "Export contacts to CSV",
        _wrap(ContactsTool.export_csv, "output_path"))
    add("export_contacts_vcard", "productivity", 0, "Export contacts to vCard",
        _wrap(ContactsTool.export_vcard, "output_path"))
    add("read_spreadsheet", "data", 0, "Read an .xlsx sheet",
        _wrap(SpreadsheetTool.read_sheet, "file_path", "sheet_name", "limit_rows"))
    add("write_spreadsheet", "data", 1, "Write rows to an .xlsx sheet",
        _wrap(SpreadsheetTool.write_rows, "file_path", "rows", "sheet_name", "overwrite"))
    add("aggregate_column", "data", 0, "Sum/avg/min/max/count a column",
        _wrap(SpreadsheetTool.aggregate_column, "file_path", "column", "operation", "sheet_name"))

    # ── Agents (multi-step loops, Level 2 reversible via checkpoint) ────────
    def _run_coding_agent(task, target_file=None, test_command=None, context_files=None):
        # Inject the ONE brain so the agent records outcomes into it (never a
        # second runtime/model).
        try:
            from app.cognition.runtime import CognitiveRuntime
            runtime = CognitiveRuntime.get_instance()
        except Exception:
            runtime = None
        return CodingAgent(runtime=runtime).run(
            task=task,
            target_file=target_file,
            test_command=test_command,
            context_files=context_files or [],
        )
    _run_coding_agent.tool_availability = CodingAgent.availability  # type: ignore[attr-defined]
    add("run_coding_agent", "agent", 2, "Plan→write→test→iterate on a coding task",
        _wrap(_run_coding_agent, "task", "target_file", "test_command", "context_files"))

    def _run_data_analysis_agent(dataset_path, question=None):
        # Read-only by construction; shares the ONE brain + ONE model (no second
        # runtime/model), mirroring the coding agent's wiring.
        try:
            from app.cognition.runtime import CognitiveRuntime
            runtime = CognitiveRuntime.get_instance()
        except Exception:
            runtime = None
        return DataAnalysisAgent(runtime=runtime).run(
            dataset_path=dataset_path,
            question=question or "",
        )
    _run_data_analysis_agent.tool_availability = DataAnalysisAgent.availability  # type: ignore[attr-defined]
    add("run_data_analysis", "agent", 0, "Read-only dataset analysis (inspect→query→answer)",
        _wrap(_run_data_analysis_agent, "dataset_path", "question"))

    # ── User plugins (auto-discovered from DATA_DIR/plugins) ────────────────
    try:
        from app.tools.plugin_registry import PluginRegistry
        for pname, pentry in PluginRegistry.discover_plugins().items():
            manifest[pname] = pentry
    except Exception as e:
        # Plugin discovery is best-effort; a failure must not break the manifest.
        app_logger.warning(f"Plugin discovery failed (continuing without plugins): {e}")

    return manifest


# Built lazily and cached at first import to avoid importing every tool module
# until the registry actually needs them.
_TOOL_MANIFEST: Dict[str, Dict[str, Any]] | None = None


def get_tool_manifest() -> Dict[str, Dict[str, Any]]:
    global _TOOL_MANIFEST
    if _TOOL_MANIFEST is None:
        _TOOL_MANIFEST = build_tool_manifest()
    return _TOOL_MANIFEST
