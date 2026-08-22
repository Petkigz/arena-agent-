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

from app.utils.logger import app_logger


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
    from app.tools.database_connector import DatabaseConnector
    from app.tools.invoice_generator import InvoiceGenerator
    from app.tools.network_diagnostics import NetworkDiagnostics
    from app.tools.budget_tracker import BudgetTracker
    from app.tools.backup_manager import BackupManager
    from app.tools.presentation_generator import PresentationGenerator
    from app.tools.package_installer import PackageInstaller
    from app.tools.rss_aggregator import RssAggregator
    from app.tools.fact_checker import FactChecker
    from app.tools.price_lookup import PriceLookup
    from app.tools.messaging import Messaging
    from app.tools.recipes import Recipes
    from app.tools.pdf_toolkit import PdfToolkit
    from app.tools.process_manager import ProcessManager
    from app.tools.calendar_service import CalendarService
    from app.tools.document_generator import DocumentGenerator
    from app.tools.local_executor import LocalExecutor
    from app.tools.contacts import ContactsTool
    from app.tools.spreadsheet import SpreadsheetTool
    from app.agents.coding_agent import CodingAgent
    from app.agents.data_analysis_agent import DataAnalysisAgent
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
    from app.tools.object_detector import ObjectDetectorTool
    from app.tools.prosody_analyzer import ProsodyAnalyzerTool
    from app.tools.vlm_analyzer import VlmAnalyzerTool
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
    add("list_processes", "system", 0, "List local processes (CPU/RAM)",
        _wrap(ProcessManager.list_processes, "filter", "limit", "sort_by"))
    add("get_process", "system", 0, "Inspect a process by PID",
        _wrap(ProcessManager.get_process, "pid"))
    add("kill_process", "system", 3, "Terminate/force-kill a process (irreversible)",
        _wrap(ProcessManager.kill_process, "pid", "force"))
    add("restart_process", "system", 3, "Restart a process (irreversible)",
        _wrap(ProcessManager.restart_process, "pid"))

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

    # ── Backup & restore ────────────────────────────────────────────────────
    add("create_backup", "system", 1, "Create a versioned backup snapshot",
        _wrap(BackupManager.create_backup, "sources", "name"))
    add("list_backups", "system", 0, "List backup snapshots",
        _ignore_payload(BackupManager.list_backups))
    add("verify_backup", "system", 0, "Verify a backup's integrity (SHA-256)",
        _wrap(BackupManager.verify_backup, "backup_id"))
    add("restore_backup", "system", 2, "Restore a backup to a directory",
        _wrap(BackupManager.restore_backup, "backup_id", "dest_dir", "overwrite"))
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
