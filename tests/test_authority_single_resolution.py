"""P0 #9: ONE authority — safety, availability and execution resolve the
SAME effective capability.

The registry's architecture documents a single capability authority
(effective_capability: runtime override -> fresh catalog -> registry copy),
and the module-level functions honor it. But the INSTANCE methods the
planner, the probes and the executor actually called read the registry's
boot-time copy directly:

    capability_safety()      -> get_capability()      (registry view)
    get_tool_availability()  -> _registry.get()       (registry view)
    execute_registered_tool()-> _registry.get()       (registry view)

So the planner could see one capability (effective), the gate reason about
another (module path — already effective), and execution invoke a third
version (stale boot copy). A patched catalog or a runtime override was
visible to some consumers and invisible to others — exactly the
multi-authority problem the registry exists to eliminate.

All three now route through _authority_entry() — the ONE internal
resolver. These tests pin each divergence scenario.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

from app.cognition import tool_registry as tr
from app.cognition.tool_registry import ToolRegistry


def make_registry(catalog: Dict[str, Dict[str, Any]]) -> ToolRegistry:
    """A registry whose catalog provider returns the given (mutable) catalog
    — the fresh-catalog view the effective resolution reads on every call."""
    return ToolRegistry(catalog_provider=lambda: catalog)


def gate_sees(registry: ToolRegistry):
    """Context manager: the module-level authority (which ActionGate
    consults through capability_safety_or_none -> capability_entry)
    resolves against THIS registry for the duration — the repo's
    established test seam for authority wiring."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        with patch.object(tr, "get_shared_registry", lambda: registry), \
             patch.object(tr, "_shared_registry", registry, create=True):
            yield
    return _ctx()


def checker(available: bool):
    def _check(*, probe: bool = False):
        return {"available": available,
                "status": "available" if available else "dependency_unavailable"}
    return _check


# ── scenario 1: the finding's exact case — override raises the level ────────

def test_runtime_override_safety_is_what_the_gate_enforces():
    """Manifest declares safety 0; a runtime override registers the same
    name at safety 3. The EFFECTIVE capability is Level 3 — and safety
    readings, availability and EXECUTION must all agree on that. Before the
    fix, execute_registered_tool proposed the stale level and could run a
    now-sensitive capability through the read-only gate."""
    catalog = {"override_me": {"name": "override_me", "category": "x",
                               "safety_level": 0,
                               "handler": lambda p: {"success": True,
                                                     "who": "catalog"}}}
    reg = make_registry(catalog)

    # Before the override: autonomous execution allowed (Level 0).
    assert reg.capability_safety("override_me") == 0
    with gate_sees(reg):
        assert reg.execute_registered_tool("override_me", {})["success"] is True

    # The runtime override patches the SAME name to Level 3.
    reg.register_tool("override_me", "x",
                      lambda p: {"success": True, "who": "override"},
                      safety_level=3, provenance="dynamic")

    assert reg.capability_safety("override_me") == 3, \
        "safety follows the override, not the boot copy"
    with gate_sees(reg):
        blocked = reg.execute_registered_tool("override_me", {})
    assert blocked["success"] is False
    assert blocked.get("requires_approval") is True, \
        "a now-Level-3 capability must hit the approval gate, not run"


# ── scenario 2: patched catalog vs stale boot copy ──────────────────────────

def test_patched_catalog_safety_beats_the_stale_boot_copy():
    """The registry booted when the catalog said safety 0; the catalog is
    later patched to safety 3. capability_safety must serve the FRESH
    catalog reading — before the fix it served the stale boot copy (0)."""
    catalog: Dict[str, Dict[str, Any]] = {
        "patched_tool": {"name": "patched_tool", "category": "x",
                         "safety_level": 0,
                         "handler": lambda p: {"success": True,
                                               "who": "old-handler"}}}
    reg = make_registry(catalog)
    assert reg.capability_safety("patched_tool") == 0

    catalog["patched_tool"] = {"name": "patched_tool", "category": "x",
                               "safety_level": 3,
                               "handler": lambda p: {"success": True,
                                                     "who": "new-handler"}}

    assert reg.capability_safety("patched_tool") == 3
    with gate_sees(reg):
        result = reg.execute_registered_tool("patched_tool", {})
    assert result["success"] is False and result.get("requires_approval")


def test_execution_runs_the_fresh_catalog_handler_not_the_boot_copy():
    """Execution invokes the handler the EFFECTIVE capability carries: a
    patched catalog's new handler runs — the stale boot copy's handler is
    never invoked."""
    catalog: Dict[str, Dict[str, Any]] = {
        "swapped_handler": {"name": "swapped_handler", "category": "x",
                            "safety_level": 0,
                            "handler": lambda p: {"success": True,
                                                  "who": "old"}}}
    reg = make_registry(catalog)
    with gate_sees(reg):
        assert reg.execute_registered_tool("swapped_handler", {})["who"] == "old"

        catalog["swapped_handler"]["handler"] = lambda p: {"success": True,
                                                           "who": "new"}
        assert reg.execute_registered_tool("swapped_handler", {})["who"] == "new"


# ── scenario 3: catalog-only capability (no boot copy at all) ───────────────

def test_catalog_only_capability_is_safety_read_probed_and_executable():
    """A capability present in the FRESH catalog but never registered at
    boot: before the fix it read as unknown (safety 99), availability said
    'not_registered', and execution refused — three consumers blind to a
    capability the authority actually knows."""
    catalog = {"brand_new_tool": {
        "name": "brand_new_tool", "category": "x", "safety_level": 0,
        "handler": lambda p: {"success": True, "ran": True},
        "availability": checker(True)}}
    reg = make_registry(catalog)

    assert reg.capability_safety("brand_new_tool") == 0, \
        "not 99 — the authority knows this capability from the catalog"
    status = reg.get_tool_availability("brand_new_tool", probe=True)
    assert status["available"] is True
    assert status["status"] == "not_registered" or status["status"] == "available"
    assert status.get("provenance") == "manifest"
    with gate_sees(reg):
        result = reg.execute_registered_tool("brand_new_tool", {})
    assert result["success"] is True and result.get("ran") is True


def test_catalog_only_availability_probes_the_catalog_checker():
    catalog = {"probe_only_tool": {
        "name": "probe_only_tool", "category": "x", "safety_level": 0,
        "handler": lambda p: {"success": True},
        "availability": checker(False)}}
    reg = make_registry(catalog)
    status = reg.get_tool_availability("probe_only_tool", probe=True)
    assert status["available"] is False
    assert status["status"] == "dependency_unavailable"


# ── scenario 4: the override's availability checker is the one probed ──────

def test_availability_probes_the_override_checker():
    """A runtime override replaces a capability's checker: the probe must
    run the OVERRIDE's checker (not the boot copy's)."""
    catalog = {"avail_override": {"name": "avail_override", "category": "x",
                                  "safety_level": 0,
                                  "handler": lambda p: {"success": True},
                                  "availability": checker(False)}}
    reg = make_registry(catalog)
    assert reg.get_tool_availability("avail_override", probe=True)["available"] is False

    reg.register_tool("avail_override", "x", lambda p: {"success": True},
                      availability=checker(True), safety_level=0,
                      provenance="dynamic")
    assert reg.get_tool_availability("avail_override", probe=True)["available"] is True


# ── scenario 5: catalog shrink — registry copy stays executable ─────────────

def test_catalog_shrink_keeps_the_registry_copy_executable():
    """The documented invariant survives the fix: a name the catalog no
    longer lists still executes through the registry's wiring (the copy),
    and its safety is still read correctly."""
    catalog: Dict[str, Dict[str, Any]] = {
        "shrinking_tool": {"name": "shrinking_tool", "category": "x",
                           "safety_level": 0,
                           "handler": lambda p: {"success": True,
                                                 "survived": True}}}
    reg = make_registry(catalog)
    # A boot-time manifest-tier registration (what _register_default_tools
    # produces for real catalog entries).
    reg.register_tool("shrinking_tool", "x",
                      lambda p: {"success": True, "survived": True},
                      safety_level=0, provenance="manifest")
    del catalog["shrinking_tool"]  # the catalog shrinks after boot

    entry = reg.effective_capability("shrinking_tool")
    assert entry is not None and entry["resolution"] == "registry_copy"
    assert reg.capability_safety("shrinking_tool") == 0
    with gate_sees(reg):
        result = reg.execute_registered_tool("shrinking_tool", {})
    assert result["success"] is True and result.get("survived") is True


# ── scenario 6: all three consumers agree — the core invariant ─────────────

def test_planner_gate_and_execution_share_one_view():
    """THE invariant: for every name in the universe, the safety the gate
    reasons with, the availability the planner probes, and the handler
    execution invokes all come from the SAME effective resolution."""
    catalog = {
        "shared_view_a": {"name": "shared_view_a", "category": "x",
                          "safety_level": 1,
                          "handler": lambda p: {"success": True},
                          "availability": checker(True)},
        "shared_view_b": {"name": "shared_view_b", "category": "x",
                          "safety_level": 3,
                          "handler": lambda p: {"success": True},
                          "availability": checker(True)},
    }
    reg = make_registry(catalog)
    reg.register_tool("shared_view_c", "x", lambda p: {"success": True},
                      safety_level=2, availability=checker(True),
                      provenance="dynamic")

    for name in ("shared_view_a", "shared_view_b", "shared_view_c"):
        effective = reg.effective_capability(name)
        assert effective is not None, name
        # Safety reading == effective entry's level.
        assert reg.capability_safety(name) == effective["safety_level"], name
        # Availability comes from the same entry's checker.
        status = reg.get_tool_availability(name, probe=True)
        assert status["available"] is True, name
        assert status["provenance"] == effective["provenance"], name


# ── preserved: unknown is still honestly unknown ────────────────────────────

def test_unknown_names_are_still_refused_everywhere():
    reg = make_registry({})
    assert reg.capability_safety("definitely_not_real") == 99
    assert reg.get_tool_availability("definitely_not_real")["status"] == "not_registered"
    result = reg.execute_registered_tool("definitely_not_real", {})
    assert result["success"] is False
    assert "not registered" in result["error"]


# ── plan freshness contracts record the effective safety ────────────────────

def test_plan_freshness_contracts_use_effective_safety(tmp_path):
    """Same bug class, same fix: a plan's action contracts describe the
    capability version that would actually execute."""
    catalog = {"contract_tool": {"name": "contract_tool", "category": "x",
                                 "safety_level": 0,
                                 "handler": lambda p: {"success": True}}}
    reg = make_registry(catalog)

    class FakeReview:
        plan_id, revision, snapshot_sha256 = "p1", 1, "sha"
        snapshot = {"steps": [{"step_id": "s1",
                               "action_type": "contract_tool"}]}

    class FakeRuntime:
        registry = reg
        # no embodied_boundary / goal_generator attributes: the snapshot
        # builder skips what the runtime does not expose.

    from app.cognition.plan_freshness import PlanFreshnessStore
    # tmp_path (not TemporaryDirectory): the store must CLOSE its SQLite
    # connections so the .db is deletable — on Windows a lingering handle
    # blocks eager tempdir cleanup (WinError 32). rmtree below proves it.
    import shutil
    store = PlanFreshnessStore(tmp_path / "fresh.db")
    snap = store.build_snapshot(FakeReview(), FakeRuntime())
    contract = snap["action_contracts"][0]
    assert contract["safety_level"] == 0

    # The runtime raises the tool's safety level: the contract must
    # follow the effective view (3), not the stale boot copy (0).
    reg.register_tool("contract_tool", "x", lambda p: {"success": True},
                      safety_level=3, provenance="dynamic")
    snap2 = store.build_snapshot(FakeReview(), FakeRuntime())
    assert snap2["action_contracts"][0]["safety_level"] == 3
    # Windows hygiene: connections are closed, the db file is deletable.
    shutil.rmtree(tmp_path, ignore_errors=False)


# ── the listing is the SAME authority as discovery (P1 review) ──────────────
# list_tool_availability iterated the registry's wiring table while
# capabilities() and get_tool_availability() resolved the effective view —
# a rebuilt manifest could add a tool the planner found instantly while the
# full listing refused to acknowledge it. Listing == single lookup ==
# discovery universe: ONE authority.

def test_rebuilt_manifest_new_tool_appears_in_listing_immediately():
    """The review's case: the manifest is rebuilt with a NEW tool. The
    planner (capabilities()) sees it instantly — the full availability
    listing must see it in the same call, not after a restart."""
    catalog = {
        "old_tool": {"name": "old_tool", "category": "x", "safety_level": 0,
                     "handler": lambda p: {"success": True},
                     "availability": checker(True)},
    }
    reg = make_registry(catalog)
    listed = {r["name"] for r in reg.list_tool_availability()}
    assert "old_tool" in listed

    # The manifest is REBUILT (the provider's catalog is the fresh view):
    # a new tool with real wiring appears.
    catalog["new_tool"] = {"name": "new_tool", "category": "x",
                           "safety_level": 0,
                           "handler": lambda p: {"success": True},
                           "availability": checker(True)}
    listed_after = {r["name"] for r in reg.list_tool_availability()}
    assert "new_tool" in listed_after, (
        "planner found the new tool, but the listing still denies it")


def test_listing_and_discovery_are_one_universe():
    """The invariant itself: the set of names in the availability listing
    equals capabilities()' effective universe — manifest names, runtime
    installs and registry-only survivors included, exactly once each."""
    catalog = {
        "catalog_a": {"name": "catalog_a", "category": "x", "safety_level": 0,
                      "handler": lambda p: {"success": True},
                      "availability": checker(True)},
        "patched_at_runtime": {
            "name": "patched_at_runtime", "category": "x", "safety_level": 0,
            "handler": lambda p: {"success": True, "who": "catalog"},
            "availability": checker(True)},
    }
    reg = make_registry(catalog)
    reg.register_tool("dynamic_only", "x", lambda p: {"success": True},
                      safety_level=0, availability=checker(True),
                      provenance="dynamic")
    reg.register_tool("patched_at_runtime", "x",
                      lambda p: {"success": True, "who": "override"},
                      safety_level=1, availability=checker(True),
                      provenance="dynamic")

    listed = sorted(r["name"] for r in reg.list_tool_availability())
    universe = sorted(reg.capabilities())
    assert listed == universe, (listed, universe)
    # No duplicates when a runtime override patches a catalog name.
    assert len(listed) == len(set(listed))
    assert "dynamic_only" in listed


def test_discovery_listing_and_execution_agree_on_a_new_tool():
    """End-to-end for the review's complaint: after the manifest rebuild,
    the planner finds the new tool, the listing acknowledges it, and
    execution runs the NEW wiring — all in the same process."""
    catalog = {}
    reg = make_registry(catalog)
    ran = []

    catalog["late_tool"] = {
        "name": "late_tool", "category": "x", "safety_level": 0,
        "handler": lambda p: ran.append("new-wiring") or {"success": True},
        "availability": checker(True),
    }
    # 1. Discovery: the effective universe contains it.
    assert "late_tool" in reg.capabilities()
    # 2. Listing: the availability surface acknowledges it (probe resolves
    #    the real checker — available, not not_registered).
    record = next(r for r in reg.list_tool_availability()
                  if r["name"] == "late_tool")
    assert record["status"] != "not_registered"
    # 3. Execution: the NEW wiring runs (not a stale registration).
    with gate_sees(reg):
        result = reg.execute_registered_tool("late_tool", {})
    assert result["success"] is True
    assert ran == ["new-wiring"]
