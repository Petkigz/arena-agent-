"""Unified Tool Capability Registry with Gate Verification & Event Emissions."""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
from app.utils.logger import app_logger, audit_logger
from app.cognition.action_proposal import ActionProposal, ActionGate, GateResult
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.event_bus import EventBus

# ---------------------------------------------------------------------------
# ONE runtime ToolRegistry (P0 #20)
#
# The cognitive runtime owns the authoritative ToolRegistry — the one wired to
# the runtime's EventBus. Planners, gates and the executor must REUSE it.
# Constructing ToolRegistry() elsewhere built a duplicate registry (all
# manifest handlers re-registered) on a SECOND EventBus, so dynamic tool
# registrations diverged and tool events from dynamic execution went nowhere.
# ---------------------------------------------------------------------------
_shared_registry = None


def get_shared_registry():
    """The ONE runtime ToolRegistry (lazily constructed if no runtime owns it)."""
    global _shared_registry
    if _shared_registry is None:
        _shared_registry = ToolRegistry()
    return _shared_registry


def set_shared_registry(registry) -> None:
    """The runtime installs its event-bus-wired registry as THE shared one."""
    global _shared_registry
    _shared_registry = registry


class ToolRegistry:
    """Centralized Registry for all system capabilities with gate verification & observation hooks."""

    # Decisive probe results (available True/False) are cached briefly so
    # planner-time probing (P0 #21) doesn't re-import a tool module on every
    # cycle. NOT_CHECKED results are never cached — they carry no information.
    _AVAILABILITY_CACHE_TTL_S = 300.0

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._registry: Dict[str, Dict[str, Any]] = {}
        self.event_bus = event_bus or EventBus()
        self._availability_cache: Dict[str, tuple] = {}
        self._register_default_tools()

    def register_tool(
        self,
        name: str,
        category: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        description: str = "",
        safety_level: int = 0,
        availability: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> None:
        self._registry[name.lower()] = {
            "name": name,
            "category": category,
            "handler": handler,
            "description": description,
            "safety_level": safety_level,
            "availability": availability,
        }

    def _register_default_tools(self) -> None:
        # Register EVERY tool from the unified manifest so the cognitive layer
        # can reach all 45 capabilities (not just the previous 3).
        from app.tools.manifest import get_tool_manifest

        for action_type, entry in get_tool_manifest().items():
            self.register_tool(
                entry["name"],
                entry["category"],
                entry["handler"],
                description=entry.get("description", ""),
                safety_level=entry.get("safety_level", 0),
                availability=entry.get("availability"),
            )

    def get_tool_availability(
        self, tool_name: str, *, probe: bool = False, refresh: bool = False
    ) -> Dict[str, Any]:
        """Report one capability's availability without probing by default.

        ``probe=True`` imports only that tool module, never the rest of the
        manifest. This makes diagnostics explicit while keeping normal startup
        isolated from optional packages and heavyweight model libraries.
        """
        key = tool_name.lower().strip()
        entry = self._registry.get(key)
        if entry is None:
            return {
                "name": key,
                "available": False,
                "status": "not_registered",
                "error": f"Tool '{tool_name}' not registered in capability registry.",
            }
        import time as _time
        now = _time.monotonic()
        if not refresh:
            cached = self._availability_cache.get(key)
            if cached and now - cached[0] < self._AVAILABILITY_CACHE_TTL_S:
                return {"name": key, **cached[1]}

        checker = entry.get("availability")
        if checker is None:
            status = {"available": True, "status": "available"}
        else:
            status = checker(probe=probe)

        # Cache DECISIVE results only. available=None (NOT_CHECKED) must keep
        # flowing through verbatim — never coerced, never frozen as knowledge.
        if isinstance(status, dict) and status.get("available") is not None:
            self._availability_cache[key] = (now, dict(status))
        return {"name": key, **status}

    def list_tool_availability(self, *, probe: bool = False) -> List[Dict[str, Any]]:
        """Return deterministic per-tool availability records."""
        return [
            self.get_tool_availability(name, probe=probe)
            for name in sorted(self._registry)
        ]

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
            from app.cognition.execution_control import (
                ExecutionCancelled,
                execution_control_registry,
            )
            execution_control_registry.checkpoint(f"before_tool:{key}")
            result = tool_entry["handler"](payload)
            execution_control_registry.checkpoint(f"after_tool:{key}")

            # Dependency availability is an execution precondition, not an
            # observed action outcome. Preserve the typed result and do not run
            # prediction scoring over a capability that never executed.
            if isinstance(result, dict) and result.get("available") is False:
                audit_logger.info(
                    f"ToolRegistry could not execute '{key}': dependency unavailable"
                )
                return result

            # Calculate prediction surprisal
            pe = PredictionEngine()
            surprisal = pe.evaluate_surprisal(
                proposal.predicted_outcome if hasattr(proposal, "predicted_outcome") else pe.predict_action(key, payload),
                result if isinstance(result, dict) else {}
            )

            result["prediction_surprisal"] = surprisal

            audit_logger.info(f"ToolRegistry executed tool '{key}' (Surprisal: {surprisal})")
            return result
        except ExecutionCancelled:
            # Cancellation is control flow, not a tool failure. The owning
            # CognitiveRuntime records the persistent cancellation outcome.
            raise
        except ImportError as e:
            # Optional dependencies are capability-local failures.  Import the
            # typed exception lazily so ToolRegistry itself remains core-only.
            from app.tools.manifest import ToolDependencyUnavailable

            if isinstance(e, ToolDependencyUnavailable):
                app_logger.warning(str(e))
                return e.as_result()
            app_logger.error(f"Import error executing registered tool '{key}': {e}")
            return {
                "success": False,
                "available": False,
                "error_type": "dependency_unavailable",
                "error": str(e),
            }
        except Exception as e:
            app_logger.error(f"Error executing registered tool '{key}': {e}")
            return {"success": False, "error": str(e)}
