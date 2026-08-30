"""P0 #21: NOT_CHECKED is not AVAILABLE.

Lazy manifest registration keeps startup fast (availability is None /
not_checked until probed) — correct. But the PLANNER must not read that as
"available": a KNOWN-missing dependency loses its candidate slot, an
unchecked one carries its honest state downstream, and the ActionPlanner
probes the chosen branch's dependencies BEFORE committing — falling back to
a probed-available branch instead of discovering the missing dependency
mid-execution.
"""

from types import SimpleNamespace
from unittest.mock import patch

import app.tools.manifest as manifest_mod
from app.cognition.tool_registry import ToolRegistry
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.action_planner import ActionPlanner


def _entry(name, available):
    return {
        "name": name, "category": "system", "handler": lambda **kw: {"success": True},
        "description": "internal handler", "safety_level": 0,
        "availability": (lambda probe=False: {"available": available, "status": "x"}),
    }


def _cap(name, desc):
    return SimpleNamespace(name=name, entity_type="capability",
                           attributes={"description": desc}, confidence=0.5)


def _world(caps):
    wm = SimpleNamespace()
    wm.find_entities = lambda entity_type: list(caps)
    return wm


def _with_manifest(fake, fn, *, use_shared_registry=False):
    """Run fn with a fake manifest. By default an ISOLATED registry is built
    from the fake manifest and passed explicitly — the SHARED registry must
    never be constructed while a test manifest is patched (it would absorb
    the fake tools for the whole process)."""
    original = manifest_mod.get_tool_manifest
    from app.cognition.tool_registry import ToolRegistry
    reg = ToolRegistry()
    manifest_mod.get_tool_manifest = lambda: fake
    try:
        reg._register_default_tools()
        return fn(reg)
    finally:
        manifest_mod.get_tool_manifest = original


def test_known_unavailable_spends_no_candidate_slot():
    fake = {"probe_a": _entry("probe_a", False), "probe_b": _entry("probe_b", True)}
    caps = [_cap("probe_a", "system diagnostic crash logs"), _cap("probe_b", "capture logs")]

    candidates = _with_manifest(fake, lambda reg: SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os", user_text="run a diagnostic on the crash logs",
        world_model=_world(caps), tool_registry=reg))
    actions = [c.get("action_type") for c in candidates]
    assert "probe_a" not in actions
    assert "probe_b" in actions


def test_not_checked_stays_a_candidate_but_is_labeled():
    """NOT_CHECKED != AVAILABLE: the candidate survives (dependency might be
    fine) but its payload must SAY not_checked — never silently 'available'."""
    fake = {"probe_c": _entry("probe_c", None)}
    caps = [_cap("probe_c", "system diagnostic crash logs")]

    candidates = _with_manifest(fake, lambda reg: SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os", user_text="run a diagnostic on the crash logs",
        world_model=_world(caps), tool_registry=reg))
    matching = [c for c in candidates if c.get("action_type") == "probe_c"]
    assert matching, "not_checked capability must remain a candidate"
    assert matching[0]["payload"].get("availability") == "not_checked"


def test_registry_probe_cache_avoids_reimport():
    reg = ToolRegistry()
    calls = []

    def checker(probe=False):
        calls.append(probe)
        return {"available": True, "status": "available"}

    reg.register_tool("cached_probe", "system", lambda p: {"success": True},
                      availability=checker)
    a = reg.get_tool_availability("cached_probe", probe=True)
    b = reg.get_tool_availability("cached_probe", probe=True)
    assert a["available"] is True and b["available"] is True
    assert calls == [True], f"probe re-ran: {calls}"
    # NOT_CHECKED results are never cached — they carry no information.
    calls.clear()

    def null_checker(probe=False):
        calls.append(probe)
        return {"available": None, "status": "not_checked"}

    reg.register_tool("null_probe", "system", lambda p: {"success": True},
                      availability=null_checker)
    reg.get_tool_availability("null_probe", probe=True)
    reg.get_tool_availability("null_probe", probe=True)
    assert calls == [True, True], "not_checked must not be cached"


def _branches(pairs):
    """Fake sim_res with branches (utility, action_type) sorted by utility."""
    branches = []
    for i, (utility, action) in enumerate(pairs):
        branches.append(SimpleNamespace(
            branch_id=f"b{i}", branch_name=f"Branch {action}",
            hypothetical_action=action, utility_score=utility,
            candidate_payload={}, consequences={}, authorization_requirement="none",
        ))
    sim = SimpleNamespace(
        competing_branches=branches,
        winning_branch=branches[0] if branches else None,
    )
    return sim


def test_planner_probes_and_falls_back_to_available_branch():
    """The highest-utility branch's dependency is missing; the planner must
    commit the next branch whose probe passes — not discover the failure at
    execution time."""
    sim = _branches([(0.9, "tool_missing_dep"), (0.7, "tool_available"), (0.5, "tool_native")])
    probes = []

    class FakeRegistry:
        def get_tool_availability(self, name, probe=False, refresh=False):
            probes.append(name)
            if name == "tool_missing_dep":
                return {"name": name, "available": False,
                        "status": "dependency_unavailable", "missing_dependency": "playwright"}
            return {"name": name, "available": True, "status": "available"}

    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: FakeRegistry()):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "tool_available"
    assert "tool_missing_dep" in probes  # the winner WAS probed before fallback


def test_planner_keeps_uncheckable_branch_with_honest_annotation():
    """Nothing probes decisively available: the highest-utility not-checked
    branch is kept, and its payload says so."""
    sim = _branches([(0.9, "tool_uncheckable"), (0.5, "tool_native")])

    class FakeRegistry:
        def get_tool_availability(self, name, probe=False, refresh=False):
            return {"name": name, "available": None, "status": "not_checked"}

    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: FakeRegistry()):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "tool_uncheckable"
    assert chosen.candidate_payload["availability"]["available"] is None


def test_planner_all_dependencies_missing_annotates_winner():
    sim = _branches([(0.9, "tool_a"), (0.5, "tool_b")])

    class FakeRegistry:
        def get_tool_availability(self, name, probe=False, refresh=False):
            return {"name": name, "available": False, "status": "dependency_unavailable"}

    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: FakeRegistry()):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "tool_a"
    assert chosen.candidate_payload["availability"] == {
        "available": False, "status": "dependency_unavailable"}


def test_not_registered_actions_are_never_demoted():
    """not_registered means 'not a registry tool' — a native path, a dynamic
    capability, or a caller-supplied candidate. It is NOT a missing
    dependency; inventing unavailability for it would reroute valid plans."""
    sim = _branches([(0.9, "custom_candidate"), (0.5, "other")])

    class FakeRegistry:
        def get_tool_availability(self, name, probe=False, refresh=False):
            if name == "custom_candidate":
                return {"name": name, "available": False, "status": "not_registered"}
            return {"name": name, "available": False, "status": "dependency_unavailable"}

    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: FakeRegistry()):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "custom_candidate"
    assert "availability" not in chosen.candidate_payload


def test_native_execution_paths_need_no_probe():
    """A native path (not in the registry) is chosen without importing
    anything, even when a higher-utility registry tool is unavailable."""
    sim = _branches([(0.9, "tool_missing_dep"), (0.8, "open_application")])

    class FakeRegistry:
        def get_tool_availability(self, name, probe=False, refresh=False):
            if name == "open_application":
                # Faithful to the real registry: native paths have no entry.
                return {"name": name, "available": False, "status": "not_registered"}
            return {"name": name, "available": False,
                    "status": "dependency_unavailable"}

    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: FakeRegistry()):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "open_application"


# ---------------------------------------------------------------------------
# P0 review #2: explicit capability provenance — 'not registered' never means
# 'definitely executable elsewhere'. Ranked tiers, not first-match returns.
# ---------------------------------------------------------------------------

def _registry_with(**availability_by_tool):
    class FakeRegistry:
        def get_tool_availability(self, name, probe=False, refresh=False):
            if name in availability_by_tool:
                return {"name": name, **availability_by_tool[name]}
            return {"name": name, "available": False, "status": "not_registered"}
    return FakeRegistry()


def test_unregistered_high_utility_cannot_steal_selection():
    """THE review case: A not_registered (utility 0.91) vs B registered and
    probed-available (utility 0.89). B must win — a proven capability beats
    an unverifiable one on mere encounter order."""
    sim = _branches([(0.91, "unregistered_a"), (0.89, "registered_b")])
    fake = _registry_with(
        registered_b={"available": True, "status": "available", "provenance": "manifest"},
    )
    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "registered_b"


def test_native_and_registered_available_compete_by_utility():
    """Both tier-1 (verified executable): utility decides, not provenance."""
    sim = _branches([(0.89, "registered_b"), (0.91, "open_application")])
    fake = _registry_with(
        registered_b={"available": True, "status": "available", "provenance": "manifest"},
    )
    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "open_application"  # higher utility

    sim2 = _branches([(0.92, "registered_b"), (0.91, "open_application")])
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen2 = ActionPlanner._probe_and_select(sim2, sim2.winning_branch)
    assert chosen2.hypothetical_action == "registered_b"


def test_registered_not_checked_outranks_unknown():
    """Tier 2 (registered, NOT_CHECKED after probe) beats tier 3 (unknown)."""
    sim = _branches([(0.95, "mystery_unknown"), (0.60, "registered_unchecked")])
    fake = _registry_with(
        registered_unchecked={"available": None, "status": "not_checked",
                              "provenance": "manifest"},
    )
    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "registered_unchecked"
    assert chosen.candidate_payload["provenance"] == "registry"
    assert chosen.candidate_payload["availability"]["available"] is None


def test_unknown_only_field_annotates_provenance():
    """Nothing backed by the registry exists: the highest-utility unknown
    branch wins and its payload SAYS the provenance is unverifiable."""
    sim = _branches([(0.9, "mystery_a"), (0.5, "mystery_b")])
    fake = _registry_with()
    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "mystery_a"
    assert chosen.candidate_payload["provenance"] == "unknown"


def test_caller_supplied_provenance_is_tagged_and_ranked_last():
    """Explicit candidates are tagged caller_supplied; unregistered ones stay
    tier 3 behind a registered-available branch."""
    sim = _branches([(0.95, "custom_one"), (0.60, "registered_b")])
    sim.competing_branches[0].candidate_payload["provenance"] = "caller_supplied"
    fake = _registry_with(
        registered_b={"available": True, "status": "available", "provenance": "manifest"},
    )
    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "registered_b"

    # And when nothing else exists, the caller-supplied branch is chosen and
    # its provenance is reported honestly.
    sim2 = _branches([(0.9, "custom_one")])
    sim2.competing_branches[0].candidate_payload["provenance"] = "caller_supplied"
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen2 = ActionPlanner._probe_and_select(sim2, sim2.winning_branch)
    assert chosen2.hypothetical_action == "custom_one"
    assert chosen2.candidate_payload["provenance"] == "caller_supplied"


def test_dynamic_registered_tool_is_tier_one():
    """Runtime-registered tools (provenance 'dynamic') count as verified
    executable when their probe passes."""
    sim = _branches([(0.95, "unregistered_a"), (0.89, "hotloaded_tool")])
    fake = _registry_with(
        hotloaded_tool={"available": True, "status": "available",
                        "provenance": "dynamic"},
    )
    import app.cognition.tool_registry as tr_mod
    with patch.object(tr_mod, "get_shared_registry", lambda: fake):
        chosen = ActionPlanner._probe_and_select(sim, sim.winning_branch)
    assert chosen.hypothetical_action == "hotloaded_tool"
