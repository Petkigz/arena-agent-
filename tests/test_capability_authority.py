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
