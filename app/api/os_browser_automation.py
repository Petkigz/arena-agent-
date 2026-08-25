"""OS grounding, browser/desktop automation, and raw-input API routes.

Extracted verbatim from app/main.py (composition refactor step 10b). Safety
semantics unchanged: raw input executes only through the grounding guard;
browser transfers are disk-reserved and cancellable; OS privilege is observed,
never assumed.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from app.tools.manifest import _LazyImportProxy

BrowserAutomation = _LazyImportProxy("app.tools.browser_automation", "BrowserAutomation")
DeepOSController = _LazyImportProxy("app.tools.deep_os_controller", "DeepOSController")
DesktopControl = _LazyImportProxy("app.tools.desktop_control", "DesktopControl")
WebAgent = _LazyImportProxy("app.tools.web_agent", "WebAgent")
Win32GhostOperator = _LazyImportProxy("app.tools.win32_ghost_operator", "Win32GhostOperator")

router = APIRouter()

# ── request models ──────────────────────────────────────────────────────────
class BrowserTakeoverRequest(BaseModel):
    active: bool

class BrowserEventRequest(BaseModel):
    event_type: str
    state: str
    evidence: List[str]

class BrowserDownloadRequest(BaseModel):
    url: str
    click_selector: str
    expected_size_bytes: Optional[int] = Field(None, ge=1)

class BrowserDeleteUploadRequest(BaseModel):
    service_id: str = Field(min_length=1, max_length=100)
    receipt_id: str = Field(min_length=1, max_length=500)

class BrowserServiceAdapterRequest(BaseModel):
    service_id: str = Field(min_length=1, max_length=100)
    url_pattern: str = Field(min_length=1, max_length=500)
    receipt_selector: str = Field(default="", max_length=300)
    receipt_attribute: str = Field(default="text", max_length=100)
    delete_url_template: str = Field(default="", max_length=1000)
    confirm_selector: str = Field(default="", max_length=300)
    note: str = Field(default="", max_length=2000)

class BrowserUploadRequest(BaseModel):
    url: str
    input_selector: str
    file_path: str
    submit_selector: str
    success_selector: str

class BrowserSessionOpenRequest(BaseModel):
    url: str = Field(min_length=1)
    headless: bool = False

class BrowserNavigateRequest(BaseModel):
    url: str
    fill_inputs: Optional[Dict[str, str]] = None
    click_selectors: Optional[List[str]] = None
    submit_form: bool = False
    use_profile: bool = False

class AppLaunchRequest(BaseModel):
    app_name: str

class WebAgentRequest(BaseModel):
    objective: str
    target_url: str
    complexity: str = "main"

class GhostMessageRequest(BaseModel):
    window_title_query: str
    message_type: Optional[str] = "click"
    text_payload: Optional[str] = None

class OSMouseClickRequest(BaseModel):
    x: int
    y: int
    double: bool = False
    grounding_id: Optional[str] = None
    expected_topology_sha256: Optional[str] = None

class OSTypeTextRequest(BaseModel):
    text: str
    grounding_id: Optional[str] = None
    expected_topology_sha256: Optional[str] = None

class OSHotkeyRequest(BaseModel):
    keys: List[str]
    grounding_id: Optional[str] = None
    expected_topology_sha256: Optional[str] = None

class SoftwareUpdateRequest(BaseModel):
    package_name: str = "vlc"


# ── endpoints ───────────────────────────────────────────────────────────────
@router.get("/os-grounding/browser-tabs")
def list_browser_tabs_endpoint(session_id:Optional[str]=Query(None),limit:int=Query(200,ge=1,le=1000)):
    from app.tools.browser_automation import BrowserAutomation
    return {"success":True,"tabs":[t.to_dict() for t in BrowserAutomation.GROUNDING.list(session_id,limit)]}

@router.get("/os-grounding/browser-tabs/resolve")
def resolve_browser_tab_endpoint(url:Optional[str]=Query(None),title:Optional[str]=Query(None),session_id:Optional[str]=Query(None)):
    from app.tools.browser_automation import BrowserAutomation
    return BrowserAutomation.GROUNDING.resolve(url=url,title=title,session_id=session_id)

@router.post("/os-grounding/browser-tabs/{tab_id}/owner-takeover")
def browser_owner_takeover_endpoint(tab_id:str,req:BrowserTakeoverRequest):
    from app.tools.browser_automation import BrowserAutomation
    try:tab=BrowserAutomation.GROUNDING.set_owner_takeover(tab_id,req.active)
    except KeyError as exc:raise HTTPException(status_code=404,detail="Browser tab not found") from exc
    return {"success":True,"tab":tab.to_dict(),"automation_paused":req.active}

@router.post("/os-grounding/browser-tabs/{tab_id}/event")
def record_browser_transfer_event_endpoint(tab_id:str,req:BrowserEventRequest):
    from app.tools.browser_automation import BrowserAutomation
    try:return BrowserAutomation.GROUNDING.record_event(tab_id,req.event_type,req.state,evidence=req.evidence)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.get("/os-control/privilege")
def os_privilege_endpoint():
    from app.cognition.privilege_model import PrivilegeModel
    return {"success":True,"privilege":PrivilegeModel.probe().to_dict(),"note":"Owner authorization does not create OS elevation."}

@router.get("/os-control/process-ownership/{pid}")
def process_ownership_endpoint(pid:int):
    from app.cognition.runtime import CognitiveRuntime
    return CognitiveRuntime.get_instance().process_ownership.inspect(pid)

@router.get("/os-grounding/accessibility/status")
def accessibility_status_endpoint():
    from app.tools.accessibility_control import AccessibilityControlTool
    return AccessibilityControlTool.status()

@router.post("/os-grounding/accessibility/capture")
def accessibility_capture_endpoint(window_id:Optional[str]=Query(None),max_nodes:int=Query(1000,ge=1,le=5000)):
    from app.tools.accessibility_control import AccessibilityControlTool
    return AccessibilityControlTool.capture_desktop(window_id,max_nodes)

@router.get("/os-grounding/accessibility/resolve")
def accessibility_resolve_endpoint(role:str=Query(...),name:str=Query(...),window_id:Optional[str]=Query(None)):
    from app.tools.accessibility_control import AccessibilityControlTool
    return AccessibilityControlTool.resolve_target(role,name,window_id)

@router.get("/os-grounding")
def list_os_groundings_endpoint(app_name:Optional[str]=Query(None),limit:int=Query(200,ge=1,le=1000)):
    from app.cognition.runtime import CognitiveRuntime
    return {"success":True,"groundings":[g.to_dict() for g in CognitiveRuntime.get_instance().os_grounding.list(app_name,limit)]}

@router.get("/os-grounding/resolve")
def resolve_os_grounding_endpoint(app_name:str=Query(...),require_window:bool=Query(False)):
    from app.cognition.runtime import CognitiveRuntime
    return CognitiveRuntime.get_instance().os_grounding.resolve_target(app_name,require_window=require_window)

@router.post("/automation/browser/download")
def browser_download_endpoint(req: BrowserDownloadRequest):
    return BrowserAutomation.download_file(req.url, req.click_selector, expected_size_bytes=req.expected_size_bytes)

@router.post("/automation/browser/delete-upload")
def browser_delete_upload_endpoint(req: BrowserDeleteUploadRequest):
    return BrowserAutomation.delete_uploaded_file(req.service_id, req.receipt_id)

@router.post("/owner-control/browser-service-adapters")
def upsert_browser_service_adapter_endpoint(req: BrowserServiceAdapterRequest):
    from app.cognition.browser_adapters import browser_adapter_store
    try:
        adapter = browser_adapter_store.upsert(req.model_dump())
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "adapter": adapter.to_dict(),
            "note": "Owner-declared service knowledge; delete flows still require separate Level-3 authorization per use."}

@router.get("/owner-control/browser-service-adapters")
def list_browser_service_adapters_endpoint():
    from app.cognition.browser_adapters import browser_adapter_store
    return {"success": True, "adapters": [a.to_dict() for a in browser_adapter_store.list()]}

@router.delete("/owner-control/browser-service-adapters/{service_id}")
def remove_browser_service_adapter_endpoint(service_id: str):
    from app.cognition.browser_adapters import browser_adapter_store
    removed = browser_adapter_store.remove(service_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Adapter not found")
    return {"success": True, "removed": service_id}

@router.get("/automation/browser/disk-status")
def browser_disk_status_endpoint():
    # Real import (not the lazy proxy): DOWNLOADS_DIR is a class attribute the
    # proxy cannot resolve — attribute access needs the concrete class.
    from app.tools.browser_automation import BrowserAutomation
    from app.cognition.disk_reservation import disk_reservation_ledger
    BrowserAutomation.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)  # probe target must exist
    ledger = disk_reservation_ledger
    probe = ledger.probe(BrowserAutomation.DOWNLOADS_DIR)
    return {
        "success": True,
        "probe": probe,
        "safety_margin_bytes": ledger.safety_margin_bytes(),
        "active_reservations": [r.to_dict() for r in ledger.list_active()],
        "active_reserved_bytes": ledger.active_bytes(),
        "note": "Reservations bound concurrent in-flight transfers; refused transfers never start.",
    }

@router.post("/automation/browser/upload")
def browser_upload_endpoint(req: BrowserUploadRequest):
    return BrowserAutomation.upload_file(req.url,req.input_selector,req.file_path,req.submit_selector,req.success_selector)

@router.post("/automation/browser/session/open")
def browser_session_open_endpoint(req: BrowserSessionOpenRequest):
    return BrowserAutomation.open_session(req.url, headless=req.headless)

@router.post("/automation/browser/session/close")
def browser_session_close_endpoint():
    from app.tools.browser_automation import BrowserAutomation as Concrete
    return Concrete.close_session()

@router.post("/automation/browser/navigate")
def browser_navigate_endpoint(req: BrowserNavigateRequest):
    return BrowserAutomation.navigate_and_extract(
        req.url, 
        fill_inputs=req.fill_inputs, 
        click_selectors=req.click_selectors, 
        submit_form=req.submit_form,
        use_profile=req.use_profile
    )

@router.get("/automation/desktop/apps")
def list_approved_apps_endpoint():
    return {"approved_apps": DesktopControl.list_approved_apps()}

@router.post("/automation/desktop/launch")
def launch_app_endpoint(req: AppLaunchRequest):
    return DesktopControl.launch_application(req.app_name)

@router.post("/automation/web-agent")
def web_agent_endpoint(req: WebAgentRequest):
    return WebAgent.execute_web_workflow(req.objective, req.target_url, complexity=req.complexity)

@router.get("/os/ghost-windows")
def list_ghost_windows_endpoint():
    return {"open_windows": Win32GhostOperator.list_open_windows()}

@router.post("/os/ghost-send")
def send_ghost_message_endpoint(req: GhostMessageRequest):
    return Win32GhostOperator.send_background_window_message(
        req.window_title_query,
        message_type=req.message_type or "click",
        text_payload=req.text_payload
    )

@router.post("/os/click")
def os_mouse_click_endpoint(req: OSMouseClickRequest):
    return DeepOSController.mouse_click(
        req.x, req.y, double=req.double,
        grounding_id=req.grounding_id,
        expected_topology_sha256=req.expected_topology_sha256,
    )

@router.post("/os/type")
def os_type_text_endpoint(req: OSTypeTextRequest):
    return DeepOSController.type_text(
        req.text,
        grounding_id=req.grounding_id,
        expected_topology_sha256=req.expected_topology_sha256,
    )

@router.post("/os/hotkey")
def os_press_hotkey_endpoint(req: OSHotkeyRequest):
    return DeepOSController.press_hotkey(
        req.keys,
        grounding_id=req.grounding_id,
        expected_topology_sha256=req.expected_topology_sha256,
    )

@router.post("/os/update-software")
def os_update_software_endpoint(req: SoftwareUpdateRequest):
    return DeepOSController.check_and_update_software(req.package_name)
