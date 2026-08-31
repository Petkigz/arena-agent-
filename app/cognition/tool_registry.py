"""Unified Tool Capability Registry with Gate Verification & Event Emissions.

THE capability authority (P0 review #12). One registry feeds every layer:

                      Capability Registry
                             |
        +--------------------+-------------------+
        v                    v                   v
     Discovery            Planning            Execution
   (reads the catalog    (asks the registry  (asks the registry
    for heuristics;       for validity,       for handlers,
    authority questions    safety, provenance) availability)
    go to the registry)         |
        +--------------------+-------------------+
                             v
                          ActionGate

Before this, six layers each re-derived 'what is a valid capability' from
the raw manifest their own way (reasoning_loop, counterfactual_simulator,
action_proposal, plan_freshness, runtime observation execution, the
investigation registry/executor) — slightly different versions of the
capability universe that could not see runtime-installed tools at all.

The authority contract — three DISTINCT notions, never conflated:
  * manifest_entry(name)        -> the static CATALOG entry, read fresh
  * runtime_entry(name)         -> what the live registry carries (boot-time
                                   manifest copies AND runtime installs)
  * capability_entry(name)      -> the EFFECTIVE capability:
                                     1. a runtime INSTALL (provenance
                                        'dynamic') OVERRIDES the catalog —
                                        patching a manifest name at runtime
                                        is intentional, and runtime is the
                                        live truth;
                                     2. else the manifest catalog, read
                                        fresh (a rebuilt/patched manifest is
                                        visible immediately — the registry's
                                        boot-time copies never shadow it);
                                     3. else the registry's copy (names the
                                        catalog no longer lists).
                                   The returned entry is tagged with its
                                   'resolution': runtime_override | manifest
                                   | registry_copy.
  * capability_safety(name)     -> the ONE safety reading (unknown -> 99,
                                   gated: unvetted is not read-only)
  * ToolRegistry.capabilities() -> every known capability, manifest +
                                   runtime, for the layers that need the map
  * NATIVE_EXECUTABLES          -> the ONE list of master-agent-native
                                   execution paths (moved here from the
                                   counterfactual simulator)

The static manifest remains the CATALOG (descriptions, synonyms, domain
keywords — discovery heuristics may read it). Validity, safety,
availability, provenance and execution are registry questions.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
from app.utils.logger import app_logger, audit_logger
from app.cognition.action_proposal import ActionProposal, ActionGate, GateResult
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.event_bus import EventBus

# The master-agent-native execution paths: capabilities Arena executes
# itself, by construction, without a tool handler. ONE list (P0 review #12)
# — the planner's provenance classifier and the counterfactual simulator
# both read it from here.
NATIVE_EXECUTABLES = ("open_application", "launch_app", "search_files",
                      "screen_capture", "list_workspace", "read_file",
                      "formulate_answer")

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


def manifest_entry(name: str) -> Optional[Dict[str, Any]]:
    """The static CATALOG entry, read fresh on every call.

    This is the manifest's own view: what is declared in the catalog right
    now — unaffected by runtime registrations. Discovery heuristics and
    override checks read THIS, not the effective capability.
    """
    try:
        from app.tools.manifest import get_tool_manifest
        return get_tool_manifest().get(str(name or ""))
    except Exception:
        return None


def runtime_entry(name: str) -> Optional[Dict[str, Any]]:
    """What the live REGISTRY carries for this name — a boot-time manifest
    copy (provenance 'manifest') or a runtime install (provenance
    'dynamic'). The registry's own view, unmerged with the catalog."""
    try:
        return get_shared_registry().get_capability(name)
    except Exception:
        return None


def capability_entry(name: str) -> Optional[Dict[str, Any]]:
    """THE EFFECTIVE capability lookup (P0 review #12).

    Every layer that asks 'is this a valid capability, and what are its
    handler/safety/availability/provenance' asks HERE; no layer re-derives
    its own version of the capability universe.

    Resolution — an override is INTENTIONAL, never accidental:
      1. a runtime INSTALL (provenance 'dynamic') overrides the catalog:
         registering a manifest name at runtime patches it on purpose —
         runtime is the live truth;
      2. else the manifest catalog, read FRESH (a rebuilt or patched
         manifest is visible immediately; the registry's boot-time
         manifest copies never shadow the catalog — stale copies and
         test-patch absorption both die here);
      3. else the registry's copy, for names the registry still knows
         but the catalog no longer lists.

    Returns a copy tagged with 'resolution':
    runtime_override | manifest | registry_copy.
    """
    key = str(name or "")
    rt = runtime_entry(key)
    if rt is not None and rt.get("provenance") == "dynamic":
        entry = dict(rt)
        entry["resolution"] = "runtime_override"
        return entry
    catalog = manifest_entry(key)
    if catalog is not None:
        entry = dict(catalog)
        entry["resolution"] = "manifest"
        return entry
    if rt is not None:
        entry = dict(rt)
        entry["resolution"] = "registry_copy"
        return entry
    return None


def capability_safety_or_none(name: str) -> Optional[int]:
    """The authoritative safety reading, or None when the capability is
    unknown. Callers with a historical 'unknown -> free' contract (the
    reasoning loop's internally registered probes) use this so unknown
    INTERNAL probes stay trusted while every KNOWN capability reads the
    one authority."""
    entry = capability_entry(name)
    if entry is None:
        return None
    level = entry.get("safety_level")
    if level is None:
        return 99
    try:
        return int(level)
    except (TypeError, ValueError):
        return 99


def capability_safety(name: str) -> int:
    """THE safety reading for a capability name (unknown -> 99, gated)."""
    try:
        return get_shared_registry().capability_safety(name)
    except Exception:
        level = capability_safety_or_none(name)
        return 99 if level is None else level


def set_shared_registry(registry) -> None:
    """The runtime installs its event-bus-wired registry as THE shared one."""
    global _shared_registry
    _shared_registry = registry


def interpret_availability(checker, probe: bool = False) -> Dict[str, Any]:
    """The ONE canonical availability interpretation (P0 review #1).

    Manifest availability checkers return DICTS:
        {"available": True,  "status": "available"}
        {"available": False, "status": "dependency_unavailable", ...}
        {"available": None,  "status": "not_checked"}
    A dict like {"available": False} is TRUTHY — any truthiness-based reading
    (``if checker():`` / ``if checker() is False:``) silently attempts the
    handler with a missing dependency. Every consumer (registry, planner
    funnel, investigation executor) routes through this function instead of
    maintaining its own interpretation. Plain-boolean and no-kwarg checkers
    keep their verbatim meaning; None is never coerced.
    """
    if not callable(checker):
        return {"available": True, "status": "available"}
    try:
        status = checker(probe=probe)
    except TypeError:
        status = checker()
    if not isinstance(status, dict):
        status = {"available": status}
    return status


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
        provenance: str = "dynamic",
    ) -> None:
        """provenance: 'manifest' (default tool set) or 'dynamic'
        (registered at runtime). Exposed through get_tool_availability so
        capability provenance is explicit end to end (P0 review #2)."""
        self._registry[name.lower()] = {
            "name": name,
            "category": category,
            "handler": handler,
            "description": description,
            "safety_level": safety_level,
            "availability": availability,
            "provenance": provenance,
        }

    def get_capability(self, name: str) -> Optional[Dict[str, Any]]:
        """The capability entry (manifest + runtime), or None if unknown."""
        return self._registry.get(str(name or "").lower())

    def capabilities(self) -> Dict[str, Dict[str, Any]]:
        """Every known capability: manifest-registered plus runtime-installed."""
        return dict(self._registry)

    def capability_safety(self, name: str) -> int:
        """Canonical safety level. Unknown capability -> 99 (gated):
        unvetted is never treated as read-only. Safety level 0 is a REAL
        value (read-only) — never coerced by an `or` default."""
        entry = self.get_capability(name)
        if entry is None:
            return 99
        level = entry.get("safety_level")
        if level is None:
            return 99
        try:
            return int(level)
        except (TypeError, ValueError):
            return 99

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
                provenance="manifest",
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
        _provenance = entry.get("provenance", "manifest")
        if not refresh:
            cached = self._availability_cache.get(key)
            if cached and now - cached[0] < self._AVAILABILITY_CACHE_TTL_S:
                return {"name": key, "provenance": _provenance, **cached[1]}

        checker = entry.get("availability")
        status = interpret_availability(checker, probe=probe)

        # Cache DECISIVE results only. available=None (NOT_CHECKED) must keep
        # flowing through verbatim — never coerced, never frozen as knowledge.
        if isinstance(status, dict) and status.get("available") is not None:
            self._availability_cache[key] = (now, dict(status))
        return {"name": key, "provenance": _provenance, **status}

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

            # Calculate prediction surprisal. proposal.predicted_outcome is
            # a plain dict (the gate stores pred.expected_changes); the
            # engine speaks WorldPrediction — wrap it, never crash scoring.
            pe = PredictionEngine()
            prediction = (
                proposal.predicted_outcome
                if hasattr(proposal, "predicted_outcome")
                else pe.predict_action(key, payload)
            )
            if isinstance(prediction, dict):
                from app.cognition.prediction_engine import WorldPrediction
                prediction = WorldPrediction(action_type=key, expected_changes=prediction)
            surprisal = pe.evaluate_surprisal(
                prediction, result if isinstance(result, dict) else {}
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
