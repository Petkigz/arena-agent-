"""P0 review #12: ONE capability registry feeds Discovery, Planning,
Execution — and ActionGate. No layer keeps its own version of the
capability universe.

The authority contract (app/cognition/tool_registry.py):
  * capability_entry(name)  — THE lookup: manifest catalog first (fresh
    reads), then the registry (runtime-installed capabilities)
  * capability_safety_or_none(name) — THE safety reading; None = unknown
  * ToolRegistry.capabilities() — the full universe (manifest + runtime)
  * NATIVE_EXECUTABLES — the ONE list (planner + counterfactual read it
    from the registry module, not from each other)
"""

from unittest.mock import patch

import app.cognition.tool_registry as tr
from app.cognition.tool_registry import (
    NATIVE_EXECUTABLES,
    ToolRegistry,
    capability_entry,
    capability_safety_or_none,
)


def test_manifest_capabilities_resolve():
    entry = capability_entry("web_search")
    assert entry is not None and entry["name"] == "web_search"


def test_unknown_capability_is_none_not_guessed():
    assert capability_entry("definitely_not_a_capability") is None
    assert capability_safety_or_none("definitely_not_a_capability") is None


def test_safety_zero_is_real_not_defaulted():
    """A read-only tool (level 0) must read as 0 — an `or`-default turns
    0 into 'gated 99' and silently blocks every read-only action."""
    assert capability_safety_or_none("web_search") == 0


def test_runtime_registered_capability_is_authoritative():
    """A tool installed at runtime — in NO manifest — resolves through the
    authority, for entry lookup AND safety."""
    reg = ToolRegistry()
    reg.register_tool("hotloaded_probe", "diagnostic",
                      lambda p: {"success": True}, safety_level=1)
    with patch.object(tr, "get_shared_registry", lambda: reg), \
         patch.object(tr, "_shared_registry", reg, create=True):
        entry = tr.capability_entry("hotloaded_probe")
        assert entry is not None and entry["provenance"] == "dynamic"
        assert tr.capability_safety_or_none("hotloaded_probe") == 1


def test_every_layer_reads_the_one_safety():
    """Delegation proof: patch the authority and the layers follow —
    proof that reasoning_loop and the action gate no longer keep their
    own manifest interpretations."""
    from app.cognition.reasoning_loop import CognitiveReasoningLoop
    from app.cognition.action_proposal import ActionGate

    # Both consumers import the authority at CALL time, so patching the
    # authority module's attribute redirects them — the delegation proof.
    with patch.object(tr, "capability_safety_or_none", return_value=7):
        assert CognitiveReasoningLoop._probe_risk_cost("web_search") == 7.0
        assert ActionGate._manifest_safety_level("web_search") == 7


def test_native_executables_have_one_home():
    """The planner's provenance classifier and the counterfactual
    simulator read the SAME list from the registry module."""
    from app.cognition.counterfactual_simulator import CounterfactualSimulator
    assert CounterfactualSimulator._NATIVE_EXECUTABLES == NATIVE_EXECUTABLES


def test_registry_capabilities_include_runtime_tools():
    reg = ToolRegistry()
    before = set(reg.capabilities())
    reg.register_tool("runtime_only_probe", "diagnostic",
                      lambda p: {"success": True})
    after = set(reg.capabilities())
    assert "runtime_only_probe" in (after - before)
    assert "web_search" in after  # manifest tools are all present


def test_counterfactual_level_map_sees_runtime_tools():
    from app.cognition.counterfactual_simulator import CounterfactualSimulator
    reg = ToolRegistry()
    reg.register_tool("runtime_level_map_probe", "diagnostic",
                      lambda p: {"success": True}, safety_level=1)
    with patch.object(tr, "get_shared_registry", lambda: reg):
        levels = CounterfactualSimulator._snapshot_manifest_levels()
    assert levels.get("runtime_level_map_probe") == 1


def test_executor_executes_a_runtime_registered_capability():
    """End-to-end authority: an investigation against a runtime-installed
    tool (not in any manifest) EXECUTES — before, the executor's manifest
    read made every runtime tool 'not registered'."""
    from app.cognition.action_selection import InvestigationExecutor, InvestigationPlan

    reg = ToolRegistry()
    reg.register_tool("runtime_investigation_probe", "diagnostic",
                      lambda **kw: {"success": True, "probe": kw.get("query")},
                      safety_level=0)
    with patch.object(tr, "get_shared_registry", lambda: reg), \
         patch.object(tr, "_shared_registry", reg, create=True):
        result = InvestigationExecutor().execute(
            InvestigationPlan(tool="runtime_investigation_probe",
                              arguments={"query": "status"},
                              target="status", reason="authority test",
                              priority=1.0))
    assert result.success is True
    assert result.output == {"success": True, "probe": "status"}


def test_patched_manifest_fakes_still_resolve():
    """The catalog is read FRESH: a test (or rebuild) that swaps the
    manifest is seen immediately — the registry's boot-time copy never
    shadows the catalog (the process-wide absorption hazard)."""
    fake = {"freshly_patched_tool": {"name": "freshly_patched_tool",
                                     "category": "x", "safety_level": 0,
                                     "handler": lambda p: {"success": True}}}
    with patch("app.tools.manifest.get_tool_manifest", return_value=fake):
        assert capability_entry("freshly_patched_tool") is not None
        assert capability_safety_or_none("freshly_patched_tool") == 0


# ---------------------------------------------------------------------------
# Three-tier resolution (follow-up review): manifest_entry / runtime_entry /
# capability_entry — an override is INTENTIONAL, never accidental.
# ---------------------------------------------------------------------------

def test_three_tiers_are_distinguishable():
    from app.cognition.tool_registry import manifest_entry, runtime_entry

    m = manifest_entry("web_search")
    r = runtime_entry("web_search")
    effective = capability_entry("web_search")
    assert m is not None and m.get("category") == "web"
    assert r is not None and r.get("provenance") == "manifest"
    assert effective is not None
    assert effective["resolution"] == "manifest"


def test_runtime_install_intentionally_overrides_the_manifest():
    """A dynamic registration of a MANIFEST name is a deliberate patch:
    runtime is the live truth and wins. The override is visible in the
    entry's resolution tag — and in the safety reading."""
    reg = ToolRegistry()
    reg.register_tool("web_search", "web",
                      lambda p: {"success": True, "patched": True},
                      safety_level=2, provenance="dynamic")
    with patch.object(tr, "get_shared_registry", lambda: reg):
        entry = tr.capability_entry("web_search")
        assert entry["resolution"] == "runtime_override"
        assert entry["provenance"] == "dynamic"
        assert entry["safety_level"] == 2
        # the authority's safety reading follows the override…
        assert tr.capability_safety_or_none("web_search") == 2
        # …while the catalog view stays the pristine manifest declaration
        assert tr.manifest_entry("web_search")["safety_level"] == 0


def test_registry_boot_copies_never_shadow_the_fresh_catalog():
    """The registry's manifest-tier entries are boot-time copies: a
    rebuilt or patched catalog is visible immediately and always beats
    them (stale copies and test-patch absorption both die here)."""
    reg = ToolRegistry()
    # Simulate a stale boot copy: registry knows the name, catalog doesn't.
    reg.register_tool("patched_away_tool", "x",
                      lambda p: {"success": True}, safety_level=0,
                      provenance="manifest")
    fake_catalog = {"freshly_patched_tool": {
        "name": "freshly_patched_tool", "category": "x", "safety_level": 0,
        "handler": lambda p: {"success": True}}}
    with patch.object(tr, "get_shared_registry", lambda: reg), \
         patch("app.tools.manifest.get_tool_manifest", return_value=fake_catalog):
        # Fresh catalog entry wins over the registry's manifest-tier copy…
        assert tr.capability_entry("freshly_patched_tool")["resolution"] == "manifest"
        # …and the registry-only name still resolves (tier 3).
        assert tr.capability_entry("patched_away_tool")["resolution"] == "registry_copy"


def test_dynamic_override_does_not_leak_into_the_manifest_view():
    """Patching a capability at runtime changes the EFFECTIVE capability,
    never the catalog itself — manifest_entry stays the static truth."""
    reg = ToolRegistry()
    reg.register_tool("pdf_merge", "documents",
                      lambda p: {"success": True}, safety_level=0,
                      provenance="dynamic")
    with patch.object(tr, "get_shared_registry", lambda: reg):
        # the real catalog still declares pdf_merge at level 2 —
        # untouched by the runtime override (which reads level 0)
        assert tr.manifest_entry("pdf_merge")["safety_level"] == 2
        assert tr.capability_entry("pdf_merge")["resolution"] == "runtime_override"
        assert tr.capability_entry("pdf_merge")["safety_level"] == 0


# ---------------------------------------------------------------------------
# One capability universe (follow-up review): ToolRegistry.capabilities() is
# the EFFECTIVE view — identical semantics to capability_entry(), rebuilt
# fresh — never a boot-time snapshot. Composed from a static catalog
# provider + runtime registrations + effective_capability().
# ---------------------------------------------------------------------------

def _fake_catalog(**overrides):
    catalog = {
        "web_search": {"name": "web_search", "category": "web",
                       "handler": lambda p: {"success": True},
                       "description": "search the web", "safety_level": 0},
        "pdf_merge": {"name": "pdf_merge", "category": "documents",
                      "handler": lambda p: {"success": True},
                      "description": "merge pdfs", "safety_level": 2},
    }
    catalog.update(overrides)
    return catalog


def test_capabilities_sees_manifest_rebuild_immediately():
    """The user-visible contract: after the catalog changes, capabilities()
    and capability_entry() agree IMMEDIATELY — no boot-time snapshot, no
    stale copy, no divergence between the two APIs."""
    reg = ToolRegistry()  # boots against the REAL catalog
    rebuilt = _fake_catalog(
        brand_new_tool={"name": "brand_new_tool", "category": "x",
                        "handler": lambda p: {"success": True},
                        "safety_level": 1},
        web_search={"name": "web_search", "category": "web",
                    "handler": lambda p: {"success": True},
                    "description": "patched description", "safety_level": 3},
    )
    with patch.object(tr, "get_shared_registry", lambda: reg), \
         patch("app.tools.manifest.get_tool_manifest", return_value=rebuilt):
        caps = reg.capabilities()
        # a NEW catalog capability appears without re-registration…
        assert caps["brand_new_tool"]["resolution"] == "manifest"
        # …and a CHANGED safety level is the fresh value, not the boot copy
        assert caps["web_search"]["safety_level"] == 3
        assert caps["web_search"]["description"] == "patched description"
        # the two APIs are the same universe
        assert caps["web_search"] == tr.capability_entry("web_search")
        assert caps["brand_new_tool"] == tr.capability_entry("brand_new_tool")
    # the original boot table is untouched — it is wiring, not truth
    assert reg.get_capability("web_search")["safety_level"] == 0


def test_capabilities_and_capability_entry_never_diverge():
    """For EVERY name in the union of catalog + registry, the map view and
    the per-name lookup return the same entry."""
    reg = ToolRegistry()
    reg.register_tool("web_search", "web",
                      lambda p: {"success": True, "patched": True},
                      safety_level=2, provenance="dynamic")  # override
    reg.register_tool("standalone_probe", "probe",
                      lambda p: {"success": True}, safety_level=0,
                      provenance="dynamic")                  # runtime-only
    fake = _fake_catalog()
    # boot a second registry against the fake catalog, then make it know a
    # name the catalog does NOT list (a boot copy of a catalog-shrunk name)
    reg2 = ToolRegistry(catalog_provider=lambda: fake)
    reg2.register_tool("gone_from_catalog", "x",
                       lambda p: {"success": True}, safety_level=0,
                       provenance="manifest")
    with patch.object(tr, "get_shared_registry", lambda: reg2):
        reg2._registry.update({k: v for k, v in reg._registry.items()})
        caps = reg2.capabilities()
        for name in list(caps) + ["unknown_capability_xyz"]:
            if tr.capability_entry(name) is None:
                assert name not in caps
            else:
                assert caps[name] == tr.capability_entry(name), name
        # the three resolutions all show up in the one universe
        assert caps["web_search"]["resolution"] == "runtime_override"
        assert caps["standalone_probe"]["resolution"] == "runtime_override"
        assert caps["pdf_merge"]["resolution"] == "manifest"
        assert caps["gone_from_catalog"]["resolution"] == "registry_copy"


def test_dynamic_override_visible_in_capabilities():
    reg = ToolRegistry()
    reg.register_tool("web_search", "web",
                      lambda p: {"success": True, "patched": True},
                      safety_level=2, provenance="dynamic")
    caps = reg.capabilities()
    assert caps["web_search"]["resolution"] == "runtime_override"
    assert caps["web_search"]["safety_level"] == 2
    assert caps["web_search"]["provenance"] == "dynamic"
    # the catalog view is untouched
    assert tr.manifest_entry("web_search")["safety_level"] == 0


def test_catalog_provider_is_injectable():
    """The static catalog is a PROVIDER, not a global: an alternate catalog
    plugs in without monkeypatching the manifest module."""
    reg = ToolRegistry(catalog_provider=lambda: _fake_catalog())
    caps = reg.capabilities()
    assert set(caps) >= {"web_search", "pdf_merge"}
    assert caps["pdf_merge"]["resolution"] == "manifest"
    assert tr_effective(reg, "pdf_merge")["safety_level"] == 2


def tr_effective(reg, name):
    return reg.effective_capability(name)


# ---------------------------------------------------------------------------
# NATIVE_EXECUTABLES (follow-up review): the ONE native-path list must carry
# EVERY master-agent-native execution path. The move from the counterfactual
# simulator silently dropped ten of them (and added two unjustified names);
# this pins the exact verified set — every path, not just one regression.
# ---------------------------------------------------------------------------

def test_native_executables_is_the_complete_verified_set():
    """The exact membership, frozen. A dropped name silently reclassifies a
    native path as registry/unknown; an added name shadows a manifest tool
    as native. Any change here must be a deliberate, reviewed decision."""
    assert set(tr.NATIVE_EXECUTABLES) == {
        "open_application", "launch_app", "search_files",
        "phone_command", "make_phone_call", "send_sms",
        "screen_capture", "opsec_audit", "daily_briefing",
        "investigate", "diagnostic", "formulate_answer",
        "answer", "workflow_execute", "observe",
    }


def test_every_native_path_is_classified_native_by_the_planner():
    """End-to-end, not spot-checked: EVERY entry in the ONE list must be
    classified 'native' by the planner's provenance classifier, and the
    counterfactual alias must be the same object (ONE list, not a copy)."""
    from app.cognition.action_planner import ActionPlanner
    from app.cognition.counterfactual_simulator import CounterfactualSimulator

    assert CounterfactualSimulator._NATIVE_EXECUTABLES is tr.NATIVE_EXECUTABLES

    class _Branch:
        def __init__(self, action):
            self.hypothetical_action = action
            self.candidate_payload = {}

    for name in tr.NATIVE_EXECUTABLES:
        provenance, status = ActionPlanner._classify_capability(
            _Branch(name), tr.get_shared_registry())
        assert provenance == "native", name
        assert status["status"] == "native_execution_path", name


def test_counterfactual_level_map_covers_every_native_path():
    """The surprisal snapshot must assign a level to EVERY native path —
    a dropped name vanishes from the map entirely (native-only paths have
    no manifest entry to backstop them) and changes counterfactual
    treatment, not just provenance. Manifest-listed native paths keep
    their DECLARED level (setdefault is a floor, not an override)."""
    from app.cognition.counterfactual_simulator import CounterfactualSimulator

    levels = CounterfactualSimulator._snapshot_manifest_levels()
    for name in tr.NATIVE_EXECUTABLES:
        assert name in levels, (name, "dropped from the native list?")
    from app.tools.manifest import get_tool_manifest
    manifest = get_tool_manifest()
    for name in tr.NATIVE_EXECUTABLES:
        if name in manifest:
            assert levels[name] == int(manifest[name]["safety_level"]), name
        else:
            assert levels[name] == 1, name


# ---------------------------------------------------------------------------
# Positive internal-probe trust (follow-up review #4): never infer trust
# from 'not found'. capability_safety -> unknown = 99 (gated);
# internal_probe_safety -> ONLY names registered at a registration seam.
# ---------------------------------------------------------------------------

def test_unknown_names_are_never_free_probe_risk():
    """An arbitrary unknown action must cost enough to escalate, not zero.
    The old fallback (authority never heard of it -> Level-0 free) was the
    unknown-is-free hole."""
    from app.cognition.reasoning_loop import CognitiveReasoningLoop

    tr.reset_internal_probes()
    try:
        assert tr.internal_probe_safety("arbitrary_unknown_action") is None
        assert tr.capability_safety_or_none("arbitrary_unknown_action") is None
        assert tr.capability_safety("arbitrary_unknown_action") == 99
        assert CognitiveReasoningLoop._probe_risk_cost("arbitrary_unknown_action") == 99.0
    finally:
        tr.reset_internal_probes()


def test_internal_probe_trust_is_registered_not_inferred():
    """The name earns Level-0 trust only when a seam DECLARES it — and the
    declared level is respected (a Level-1 internal probe costs 1)."""
    from app.cognition.reasoning_loop import CognitiveReasoningLoop

    tr.reset_internal_probes()
    try:
        tr.register_internal_probe("declared_internal_probe", safety_level=0,
                                   source="test")
        assert tr.internal_probe_safety("declared_internal_probe") == 0
        assert CognitiveReasoningLoop._probe_risk_cost("declared_internal_probe") == 0.0

        tr.register_internal_probe("heavier_internal_probe", safety_level=1,
                                   source="test")
        assert tr.internal_probe_safety("heavier_internal_probe") == 1
        assert CognitiveReasoningLoop._probe_risk_cost("heavier_internal_probe") == 1.0
    finally:
        tr.reset_internal_probes()


def test_authority_level_wins_over_internal_declaration():
    """A name the authority knows reads its DECLARED capability level even
    if someone also registered it as an internal probe — the authority is
    the truth for real capabilities."""
    from app.cognition.reasoning_loop import CognitiveReasoningLoop

    tr.reset_internal_probes()
    try:
        tr.register_internal_probe("web_search", safety_level=0, source="test")
        # web_search declares Level-0 in the catalog... use pdf_merge (2)
        tr.register_internal_probe("pdf_merge", safety_level=0, source="test")
        assert CognitiveReasoningLoop._probe_risk_cost("pdf_merge") == 2.0
    finally:
        tr.reset_internal_probes()


def test_registration_seams_declare_internal_probes():
    """Both seams: an explicitly registered probe planner declares its
    plan's tool, and an explicitly registered executor handler declares
    its name. Discovery-discovered manifest tools need no declaration."""
    from app.cognition.action_selection import (
        InvestigationExecutor, InvestigationRegistry, InvestigationPlan)
    from app.cognition.reasoning_loop import CognitiveReasoningLoop

    tr.reset_internal_probes()
    try:
        # planner seam
        registry = InvestigationRegistry()
        registry.register("chrome", lambda n: InvestigationPlan(
            tool="probe_chrome", arguments={}, target=n.target,
            reason=n.reason, priority=n.priority))
        plan = registry.plan(_Need("is chrome responsive", "chrome", "r"))
        assert plan.tool == "probe_chrome"
        assert tr.internal_probe_safety("probe_chrome") == 0
        assert CognitiveReasoningLoop._probe_risk_cost("probe_chrome") == 0.0

        # executor seam
        executor = InvestigationExecutor()
        executor.register("probe_widget", lambda **kw: "ok")
        assert tr.internal_probe_safety("probe_widget") == 0
        assert CognitiveReasoningLoop._probe_risk_cost("probe_widget") == 0.0
    finally:
        tr.reset_internal_probes()


class _Need:
    def __init__(self, question, target, reason):
        self.question = question
        self.target = target
        self.reason = reason
        self.priority = 0.5


# ---------------------------------------------------------------------------
# No checker is NOT availability (follow-up review #5): 'no probe exists'
# means UNKNOWN (not_checked), never assumed True. Only an explicit
# NO_PROBE_REQUIRED declaration makes a checker-less capability available.
# ---------------------------------------------------------------------------

def test_no_checker_is_not_checked_not_available():
    """The old fallback returned available=True for availability=None —
    conflating 'no probe exists' with 'probe succeeded'. NOT_CHECKED is
    not AVAILABLE."""
    for checker in (None, "not_the_sentinel", 42, {"available": True}):
        status = tr.interpret_availability(checker)
        assert status["available"] is None, checker
        assert status["status"] == "not_checked", checker


def test_no_probe_required_is_explicitly_available():
    status = tr.interpret_availability(tr.NO_PROBE_REQUIRED)
    assert status["available"] is True
    assert status["status"] == "no_probe_required"


def test_list_capabilities_is_the_declared_probe_free_capability():
    """The catalog's ONE explicitly probe-free capability: in-process
    self-introspection, zero external dependencies. The sentinel linkage
    between manifest and the authority is pinned so it cannot drift."""
    entry = tr.manifest_entry("list_capabilities")
    assert entry["availability"] == tr.NO_PROBE_REQUIRED
    status = tr.get_shared_registry().get_tool_availability("list_capabilities")
    assert status["available"] is True
    assert status["status"] == "no_probe_required"


def test_checkerless_tools_are_honestly_not_checked():
    """os_control_execute / os_control_plan have no availability probe
    (their OS backends are probed at execution): they used to falsely
    report available=True; now they honestly report not_checked."""
    for name in ("os_control_execute", "os_control_plan"):
        assert tr.manifest_entry(name)["availability"] is None, name
        status = tr.get_shared_registry().get_tool_availability(name)
        assert status["available"] is None, name
        assert status["status"] == "not_checked", name


def test_dynamic_tools_without_probe_are_not_checked():
    """Runtime-installed tools with no availability callable are UNKNOWN,
    not assumed available — same rule as manifest tools."""
    reg = ToolRegistry()
    reg.register_tool("probeless_dynamic", "x", lambda p: {"success": True})
    status = reg.get_tool_availability("probeless_dynamic")
    assert status["available"] is None
    assert status["status"] == "not_checked"


def test_not_checked_flows_but_does_not_freeze():
    """not_checked is never cached (it carries no information); a decisive
    no_probe_required result IS cached — knowledge vs. assumption."""
    reg = ToolRegistry()
    reg.register_tool("probeless_dynamic", "x", lambda p: {"success": True})
    reg.get_tool_availability("probeless_dynamic")
    assert "probeless_dynamic" not in reg._availability_cache

    status = reg.get_tool_availability("list_capabilities")
    assert status["status"] == "no_probe_required"
    assert "list_capabilities" in reg._availability_cache


def test_investigation_executor_still_runs_not_checked_tools():
    """not_checked means 'unknown', not 'unavailable': the executor
    attempts the handler and fails honestly if the dependency is missing —
    it does not pre-refuse."""
    from app.cognition.action_selection import InvestigationExecutor, InvestigationPlan

    executor = InvestigationExecutor()
    plan = InvestigationPlan(tool="list_capabilities", arguments={"payload": {}},
                             target="capabilities", reason="test", priority=0.5)
    result = executor.execute(plan)
    assert result.success is True
    assert result.output.get("tool_count", 0) >= 100
