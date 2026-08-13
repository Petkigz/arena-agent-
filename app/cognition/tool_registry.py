"""Unified Tool Capability Registry with Gate Verification & Event Emissions."""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
from app.utils.logger import app_logger, audit_logger
from app.cognition.action_proposal import ActionProposal, ActionGate, GateResult
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.event_bus import EventBus

class ToolRegistry:
    """Centralized Registry for all system capabilities with gate verification & observation hooks."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._registry: Dict[str, Dict[str, Any]] = {}
        self.event_bus = event_bus or EventBus()
        self._register_default_tools()

    def register_tool(
        self,
        name: str,
        category: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        description: str = "",
        safety_level: int = 0
    ) -> None:
        self._registry[name.lower()] = {
            "name": name,
            "category": category,
            "handler": handler,
            "description": description,
            "safety_level": safety_level
        }

    def _register_default_tools(self) -> None:
        from app.tools.app_inventory import SystemAppInventory
        from app.tools.universal_filesystem import UniversalFilesystem
        from app.tools.screen_capture import ScreenCaptureTool

        self.register_tool(
            "launch_app", "os_control",
            lambda p: SystemAppInventory.launch_any_app(p.get("app_query", "notepad")),
            "Launches an installed application by query", safety_level=2
        )
        self.register_tool(
            "search_files", "filesystem",
            lambda p: {"files": UniversalFilesystem.search_filesystem(p.get("query", ""))},
            "Searches local filesystem for files", safety_level=0
        )
        self.register_tool(
            "screen_capture", "vision",
            lambda p: ScreenCaptureTool.capture_screen_delta(),
            "Captures screenshot with image delta comparison", safety_level=0
        )

    def execute_registered_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        key = tool_name.lower().strip()
        tool_entry = self._registry.get(key)

        if not tool_entry:
            return {"success": False, "error": f"Tool '{tool_name}' not registered in capability registry."}

        proposal = ActionProposal(
            action_type=key,
            payload=payload,
            safety_level=tool_entry["safety_level"]
        )

        gate_res = ActionGate.evaluate_proposal(proposal)
        if not gate_res.allowed:
            return {
                "success": False,
                "error": f"Gate Blocked ({gate_res.gate_name}): {gate_res.reason}",
                "requires_approval": gate_res.requires_approval
            }

        app_logger.info(f"ToolRegistry executing verified tool '{key}'...")
        try:
            result = tool_entry["handler"](payload)

            # Calculate prediction surprisal
            pe = PredictionEngine()
            surprisal = pe.evaluate_surprisal(
                proposal.predicted_outcome if hasattr(proposal, "predicted_outcome") else pe.predict_action(key, payload),
                result if isinstance(result, dict) else {}
            )

            result["prediction_surprisal"] = surprisal

            audit_logger.info(f"ToolRegistry executed tool '{key}' (Surprisal: {surprisal})")
            return result
        except Exception as e:
            app_logger.error(f"Error executing registered tool '{key}': {e}")
            return {"success": False, "error": str(e)}
