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
  * internal_probe_safety(name) -> trusted level of a POSITIVELY
                                   REGISTERED internal probe, else None —
                                   trust is registered, never inferred
                                   from 'not found' (the loop's probes
                                   declare themselves at their
                                   registration seams)
  * ToolRegistry.capabilities() -> the ONE capability universe, the
                                   EFFECTIVE view rebuilt fresh on every
                                   call — identical semantics to
                                   capability_entry(), never a boot-time
                                   snapshot
  * NATIVE_EXECUTABLES          -> the ONE list of master-agent-native
                                   execution paths (moved here from the
                                   counterfactual simulator)

The static manifest remains the CATALOG (descriptions, synonyms, domain
keywords — discovery heuristics may read it). Validity, safety,
availability, provenance and execution are registry questions.
"""

from __future__ import annotations
import threading
from typing import Dict, Any, List, Optional, Callable
from app.utils.logger import app_logger, audit_logger
from app.cognition.action_proposal import ActionProposal, ActionGate, GateResult
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.event_bus import EventBus

# The master-agent-native execution paths: capabilities Arena executes
# itself, by construction, without a tool handler. ONE list (P0 review #12)
# — the planner's provenance classifier and the counterfactual simulator
# both read it from here.
#
# Contents are the VERIFIED set this list had when it lived in the
# counterfactual simulator (all 15 paths remain live action types across
# the runtime, planner and gate paths). The move to tool_registry must
# never change membership: a dropped name silently reclassifies a native
# path as registry/unknown (different provenance, different surprisal
# treatment), an added name shadows a manifest tool as native. The exact
# set is pinned by tests/test_capability_authority.py.
NATIVE_EXECUTABLES = ("open_application", "launch_app", "search_files",
                      "phone_command", "make_phone_call", "send_sms",
                      "screen_capture", "opsec_audit", "daily_briefing",
                      "investigate", "diagnostic", "formulate_answer",
                      "answer", "workflow_execute", "observe")

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

    Delegates to ToolRegistry.effective_capability — there is exactly ONE
    implementation of the resolution; this function is the import seam.
    """
    try:
        return get_shared_registry().effective_capability(name)
    except Exception:
        # Registry unavailable (early import, headless test): the static
        # catalog view is still better than a wrong answer.
        catalog = manifest_entry(name)
        if catalog is not None:
            entry = dict(catalog)
            entry.setdefault("provenance", "manifest")
            entry["resolution"] = "manifest"
            return entry
        return None


# ---------------------------------------------------------------------------
# Internal probes (P0 review, follow-up #4): trust is POSITIVE, never
# inferred from 'not found'. The cognitive loop runs probes that live
# OUTSIDE the capability universe (registered planner/handler pairs, not
# manifest or runtime-installed tools). A name earns Level-0 trust only
# because a registration seam DECLARED it here — anything the authority
# and this registry both do not know is gated (capability_safety -> 99).
# ---------------------------------------------------------------------------
_INTERNAL_PROBES: Dict[str, Dict[str, Any]] = {}


def register_internal_probe(name: str, safety_level: int = 0, source: str = "") -> None:
    """Positively declare a cognitive-loop internal probe and the safety
    level its autonomous execution is trusted at (default 0: read-only).

    The registration seams are InvestigationRegistry.register (a plan
    from an explicitly REGISTERED probe planner) and
    InvestigationExecutor.register (an explicitly registered handler).
    Nothing else may declare trust."""
    _INTERNAL_PROBES[str(name or "").lower()] = {
        "name": str(name or ""),
        "safety_level": int(safety_level),
        "provenance": "internal_probe",
        "declared_by": source or "unspecified",
    }


def internal_probe_safety(name: str) -> Optional[int]:
    """The trusted safety level of a REGISTERED internal probe, or None.

    This is the ONLY path by which a name outside the capability
    universe earns trust. 'Not found anywhere' is never evidence of
    safety — callers must fall back to capability_safety (unknown -> 99,
    gated), never to zero."""
    entry = _INTERNAL_PROBES.get(str(name or "").lower())
    if entry is None:
        return None
    return int(entry.get("safety_level", 0))


def reset_internal_probes() -> None:
    """Test seam: drop all internal-probe declarations."""
    _INTERNAL_PROBES.clear()


def capability_safety_or_none(name: str) -> Optional[int]:
    """The authoritative safety reading, or None when the capability is
    unknown TO THE AUTHORITY. None means 'not found' — it is NEVER
    evidence of safety. A caller may treat a None as trusted ONLY for
    names it has positively established elsewhere (see
    internal_probe_safety); treating every not-found name as free
    recreates the unknown-is-free hole."""
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


# Sentinel (follow-up review #5): the catalog's EXPLICIT declaration that a
# capability needs no availability probe — in-process, zero external
# dependencies, available by construction (e.g. list_capabilities). Only
# this declaration makes a checker-less capability available; absence of a
# checker never does.
NO_PROBE_REQUIRED = "no_probe_required"


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

    NO checker is NOT availability (follow-up review #5): 'no probe
    exists' means UNKNOWN — {"available": None, "status": "not_checked"} —
    never assumed True. Assuming available conflates 'no probe exists'
    with 'probe succeeded', which this architecture explicitly refuses
    (NOT_CHECKED is not AVAILABLE). The single exception is the explicit
    NO_PROBE_REQUIRED declaration above: a capability the catalog
    positively marks probe-free is available by construction.
    """
    if checker == NO_PROBE_REQUIRED:
        return {
            "available": True,
            "status": "no_probe_required",
            "reason": "explicitly declared probe-free: in-process capability, "
                      "no external dependency to probe",
        }
    if not callable(checker):
        return {
            "available": None,
            "status": "not_checked",
            "reason": "no availability probe declared — availability is "
                      "UNKNOWN, not assumed",
        }
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
    #
    # The TTL is a BACKSTOP, not the invalidation mechanism (P0 #6): a pure
    # TTL lets a runtime-installed capability stay cached available=False for
    # up to five minutes AFTER its dependency arrives — unusable for an
    # autonomous system. Every cached entry is therefore tagged with the
    # ENVIRONMENT REVISION observed at probe time, and the entry is served
    # only while that revision is still current. Anything that can change
    # what a probe would observe bumps the revision:
    #   * a runtime (de)registration            -> register_tool()
    #   * a dependency install/uninstall        -> PackageInstaller -> note_environment_change()
    #   * any other environment change          -> note_environment_change()
    #   * execution that contradicts the cache  -> invalidate_tool_availability()
    # (a package the owner installs in a terminal without Arena seeing it
    # still heals via the TTL backstop).
    _AVAILABILITY_CACHE_TTL_S = 300.0

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        catalog_provider: Optional[Callable[[], Dict[str, Dict[str, Any]]]] = None,
    ) -> None:
        # Architecture (P0 review, follow-up): the registry COMPOSES
        #   * a static catalog provider  — the manifest, read FRESH on
        #     every lookup (injectable, so tests and alternate catalogs
        #     plug in without monkeypatching module globals);
        #   * runtime registrations       — the execution table (handlers
        #     wired at boot + tools installed while running);
        #   * effective_capability(name)  — the ONE authoritative lookup.
        # The boot-time registration below only wires EXECUTION handlers;
        # it is a cache, never the source of truth for the universe.
        self._registry: Dict[str, Dict[str, Any]] = {}
        self.event_bus = event_bus or EventBus()
        # Environment revision epoch (P0 #6): monotonic counter bumped on
        # every event that can change what an availability probe would
        # observe. Cache entries record the revision they were probed at and
        # are stale the moment the revision moves — no waiting out a TTL.
        self._environment_revision = 0
        self._env_lock = threading.RLock()
        self._availability_cache: Dict[str, tuple] = {}
        self._catalog_provider = catalog_provider or self._static_catalog
        self._register_default_tools()

    @staticmethod
    def _static_catalog() -> Dict[str, Dict[str, Any]]:
        """The static catalog, read lazily so a rebuilt or patched
        manifest is visible on the next lookup (never a boot copy)."""
        try:
            from app.tools.manifest import get_tool_manifest
            return get_tool_manifest() or {}
        except Exception:
            return {}

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
        capability provenance is explicit end to end (P0 review #2).

        A registration CHANGES the capability surface (P0 #6): the new entry
        may carry a different handler AND a different availability checker,
        so the previous registration's cached availability for this name is
        dropped immediately and the environment revision advances — the
        planner re-probes on its next lookup instead of reading facts about
        a capability that no longer exists in that form.
        """
        key = str(name or "").lower()
        self._registry[key] = {
            "name": name,
            "category": category,
            "handler": handler,
            "description": description,
            "safety_level": safety_level,
            "availability": availability,
            "provenance": provenance,
        }
        with self._env_lock:
            self._availability_cache.pop(key, None)
            self._environment_revision += 1

    @property
    def environment_revision(self) -> int:
        """Current environment revision. Availability facts carry the
        revision they were probed at (probed_at_revision); a fact whose
        revision differs from the current one is stale by definition."""
        with self._env_lock:
            return self._environment_revision

    def note_environment_change(self, reason: str, source: str = "system") -> int:
        """Declare that the dependency/environment surface changed.

        Callers: package installs/uninstalls, plugin installs, device
        topology changes, owner-declared manual changes, or any subsystem
        that observes the environment move. Effects:

          * every cached availability fact becomes stale immediately (the
            cache is cleared — no TTL wait, no per-entry bookkeeping),
          * the environment revision advances so results record fresh
            provenance, and
          * an ``environment_changed`` event is emitted on the registry's
            event bus so other subsystems (world model, embodied boundary)
            can react to the same fact.

        Returns the new revision.
        """
        with self._env_lock:
            self._environment_revision += 1
            revision = self._environment_revision
            self._availability_cache.clear()
        audit_logger.info(
            f"Environment revision {revision} — availability cache cleared "
            f"(reason: {reason}; source: {source})"
        )
        try:
            self.event_bus.emit(
                "environment_changed",
                {"reason": reason, "revision": revision},
                source=source,
            )
        except Exception as exc:  # event plumbing must never break the notifier
            app_logger.warning(f"environment_changed event emission failed: {exc}")
        return revision

    def invalidate_tool_availability(self, tool_name: str, reason: str = "") -> None:
        """Drop ONE capability's cached availability (P0 #6).

        Used when execution evidence contradicts a cached probe (the tool
        reported dependency-unavailable at execution time): ground truth
        beats the cache, so the entry is dropped and the next lookup
        re-runs the real checker. This is per-tool evidence — it does NOT
        bump the environment revision, because one tool's failure says
        nothing about other capabilities' dependencies.
        """
        key = str(tool_name or "").lower().strip()
        with self._env_lock:
            dropped = self._availability_cache.pop(key, None)
        if dropped is not None:
            audit_logger.info(
                f"Availability cache invalidated for '{key}' — {reason}"
            )

    def get_capability(self, name: str) -> Optional[Dict[str, Any]]:
        """The REGISTRY'S OWN entry (execution wiring: boot-time manifest
        handlers + runtime installs), or None. This is the runtime view —
        NOT the authority. Layers asking 'what is true of this capability'
        call effective_capability() / module capability_entry() instead."""
        return self._registry.get(str(name or "").lower())

    def effective_capability(self, name: str) -> Optional[Dict[str, Any]]:
        """THE authoritative capability lookup (P0 review #12).

        Resolution — an override is INTENTIONAL, never accidental:
          1. a runtime INSTALL (provenance 'dynamic') overrides the
             catalog: registering a manifest name at runtime patches it
             on purpose — runtime is the live truth;
          2. else the static catalog, read FRESH through the provider (a
             rebuilt or patched manifest is visible immediately; the
             registry's boot-time copies never shadow it);
          3. else the registry's own copy, for names the registry still
             knows but the catalog no longer lists (execution wiring
             survives a catalog shrink).

        Returns a copy tagged with 'resolution':
        runtime_override | manifest | registry_copy.
        """
        key = str(name or "").lower()
        runtime = self._registry.get(key)
        if runtime is not None and runtime.get("provenance") == "dynamic":
            entry = dict(runtime)
            entry["resolution"] = "runtime_override"
            return entry
        try:
            catalog = self._catalog_provider() or {}
        except Exception:
            catalog = {}
        catalog_entry = catalog.get(key)
        if catalog_entry is not None:
            entry = dict(catalog_entry)
            entry.setdefault("provenance", "manifest")
            entry["resolution"] = "manifest"
            return entry
        if runtime is not None:
            entry = dict(runtime)
            entry["resolution"] = "registry_copy"
            return entry
        return None

    def capabilities(self) -> Dict[str, Dict[str, Any]]:
        """The ONE capability universe — the EFFECTIVE view, rebuilt fresh
        on every call with IDENTICAL semantics to effective_capability():

          * every catalog capability, read fresh through the provider
            (a rebuilt or patched manifest is visible immediately);
          * runtime installs layered on top — a dynamic registration of
            a manifest name is an intentional override and WINS;
          * registry-only names (catalog shrank or runtime-registered
            with manifest provenance) survive as registry_copy.

        The boot-time registration table alone is NOT the universe: it is
        an execution-wiring cache that must never shadow the live catalog.
        Each entry is a copy tagged with 'resolution'.
        """
        try:
            catalog = self._catalog_provider() or {}
        except Exception:
            catalog = {}
        merged: Dict[str, Dict[str, Any]] = {}
        for name, entry in catalog.items():
            view = dict(entry)
            view.setdefault("provenance", "manifest")
            view["resolution"] = "manifest"
            merged[str(name).lower()] = view
        for name, entry in self._registry.items():
            if entry.get("provenance") == "dynamic":
                view = dict(entry)
                view["resolution"] = "runtime_override"
                merged[name] = view
            elif name not in merged:
                view = dict(entry)
                view["resolution"] = "registry_copy"
                merged[name] = view
        return merged

    def _authority_entry(self, name: str) -> Optional[Dict[str, Any]]:
        """The ONE internal resolver for every authority question (P0 #9).

        Safety readings, availability probes and EXECUTION all resolve the
        capability through effective_capability() — so the planner, the
        gate and the executor can never disagree about WHICH VERSION of a
        capability they are reasoning about. Before this choke point
        existed, capability_safety() / get_tool_availability() /
        execute_registered_tool() each read the registry's boot-time copy
        directly: a patched catalog or a runtime override could be visible
        to one consumer and invisible to another — the multi-authority
        problem the registry was built to eliminate.

        Resolution (identical to effective_capability, because it IS it):
          1. runtime INSTALL (provenance 'dynamic') overrides the catalog;
          2. else the static catalog, read FRESH (a rebuilt/patched
             manifest is visible immediately);
          3. else the registry's own copy (execution wiring survives a
             catalog shrink).
        """
        return self.effective_capability(name)

    @staticmethod
    def _coerce_safety_level(level: Any) -> int:
        """Robust safety coercion shared by every authority consumer:
        missing/unparseable -> 99 (gated) — unvetted is never read-only,
        and 0 is a REAL value never coerced by an `or` default."""
        if level is None:
            return 99
        try:
            return int(level)
        except (TypeError, ValueError):
            return 99

    def capability_safety(self, name: str) -> int:
        """Canonical safety level. Unknown capability -> 99 (gated):
        unvetted is never treated as read-only. Safety level 0 is a REAL
        value (read-only) — never coerced by an `or` default.

        Resolved through the ONE authority resolver: a runtime override or
        a freshly patched catalog entry changes this reading immediately
        (P0 #9) — it never serves the registry's stale boot-time copy."""
        entry = self._authority_entry(name)
        if entry is None:
            return 99
        return self._coerce_safety_level(entry.get("safety_level"))

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

        Cached results are served only while BOTH hold (P0 #6):
          * within the TTL backstop, and
          * probed at the CURRENT environment revision.
        Any environment change (registration, dependency install, declared
        environment change) makes every entry stale immediately.

        The entry is resolved through the ONE authority resolver (P0 #9):
        a runtime override's checker and a freshly patched catalog entry's
        checker are what gets probed — never the registry's stale boot-time
        copy of a previous registration.
        """
        key = tool_name.lower().strip()
        entry = self._authority_entry(key)
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
        with self._env_lock:
            revision = self._environment_revision
        if not refresh:
            with self._env_lock:
                cached = self._availability_cache.get(key)
            if (
                cached is not None
                and now - cached[0] < self._AVAILABILITY_CACHE_TTL_S
                and cached[1] == revision
            ):
                return {"name": key, "provenance": _provenance, **cached[2]}

        checker = entry.get("availability")
        status = interpret_availability(checker, probe=probe)

        # Cache DECISIVE results only. available=None (NOT_CHECKED) must keep
        # flowing through verbatim — never coerced, never frozen as knowledge.
        if isinstance(status, dict) and status.get("available") is not None:
            recorded = dict(status)
            recorded["probed_at_revision"] = revision
            with self._env_lock:
                # Race guard: if the environment moved while the probe ran,
                # the fresh result is returned but NOT cached — an entry born
                # stale would defeat the revision check entirely.
                if self._environment_revision == revision:
                    self._availability_cache[key] = (now, revision, recorded)
            return {"name": key, "provenance": _provenance, **recorded}
        return {"name": key, "provenance": _provenance, **status}

    def list_tool_availability(self, *, probe: bool = False) -> List[Dict[str, Any]]:
        """Return deterministic per-tool availability records for the SAME
        capability universe discovery sees (P1 review).

        This iterated the registry's wiring table while capabilities() and
        get_tool_availability() resolved the EFFECTIVE view — so a rebuilt
        manifest could add a tool the planner found instantly, while the
        full listing (the /tools/availability surface) still refused to
        acknowledge it existed: 'the planner found the new tool, but the
        listing says it isn't there.' The listing, the single lookup and
        the discovery universe are ONE authority: iterate the effective
        universe, and each record resolves through _authority_entry like
        every other authority consumer."""
        return [
            self.get_tool_availability(name, probe=probe)
            for name in sorted(self.capabilities())
        ]

    def execute_registered_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        key = tool_name.lower().strip()
        # Execution resolves through the ONE authority resolver (P0 #9):
        # the handler invoked and the safety level proposed are the
        # EFFECTIVE capability's — a runtime override's handler runs (not
        # the boot copy it replaced), a freshly patched catalog entry's
        # handler runs (not the stale boot copy), and a catalog shrink
        # still leaves the registry copy executable. Before this, the
        # planner could see one capability, the gate reason about another,
        # and execution invoke a third version.
        tool_entry = self._authority_entry(key)

        if not tool_entry:
            return {"success": False, "error": f"Tool '{tool_name}' not registered in capability registry."}

        proposal = ActionProposal(
            action_type=key,
            payload=payload,
            safety_level=self._coerce_safety_level(tool_entry.get("safety_level"))
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
                # Execution evidence CONTRADICTS any cached 'available' probe
                # (P0 #6): ground truth wins, the cached fact is dropped, and
                # the next lookup re-runs the real checker instead of re-freezing
                # this failure.
                self.invalidate_tool_availability(
                    key, "execution reported dependency unavailable"
                )
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

            # Same rule as the available=False result path above: the handler
            # could not even import its dependency, so any cached probe that
            # said this capability was available is contradicted by ground
            # truth and must not survive (P0 #6).
            self.invalidate_tool_availability(
                key, f"import error during execution: {e}"
            )
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
