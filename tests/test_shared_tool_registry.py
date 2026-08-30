"""P0 #20: ONE runtime ToolRegistry — planner, gate, executor all reuse it.

The runtime owns the authoritative registry (wired to its EventBus).
MasterAgentOrchestrator's dynamic-tool path and the goal interpreter's
fallback used to construct fresh ToolRegistry() instances — duplicate
registries on second EventBuses: dynamic registrations diverged and tool
events from dynamic execution went nowhere.
"""

from unittest.mock import patch

from app.cognition.tool_registry import (
    ToolRegistry,
    get_shared_registry,
    set_shared_registry,
)


def test_shared_registry_is_stable_and_lazy():
    set_shared_registry(None)
    try:
        a = get_shared_registry()
        b = get_shared_registry()
        assert a is b
        assert isinstance(a, ToolRegistry)
    finally:
        set_shared_registry(None)


def test_runtime_installs_its_event_bus_registry_as_shared(tmp_path):
    import sys
    sys.path.insert(0, ".")
    from app.cognition.runtime import CognitiveRuntime

    rt = CognitiveRuntime(db_path=str(tmp_path / "t.db"))
    assert get_shared_registry() is rt.registry
    assert rt.registry.event_bus is rt.events


def test_no_duplicate_registry_construction_during_execution(tmp_path):
    """Creating a runtime constructs ONE registry; executing a dynamic
    registered tool through the master agent must construct ZERO more."""
    import sys
    sys.path.insert(0, ".")
    from app.cognition.runtime import CognitiveRuntime
    from app.agents.master_agent import MasterAgentOrchestrator
    from app.cognition.action_proposal import ActionProposal

    constructions = []
    original_init = ToolRegistry.__init__

    def counting_init(self, *a, **kw):
        constructions.append(1)
        original_init(self, *a, **kw)

    rt = CognitiveRuntime(db_path=str(tmp_path / "t.db"))
    baseline = len(constructions)

    # A dynamically registered tool (the kind only the runtime's registry has).
    rt.registry.register_tool(
        name="dynamic_probe_tool",
        category="diagnostic",
        handler=lambda payload: {"success": True, "probed": payload.get("x")},
        description="test-only dynamic tool",
        safety_level=0,
    )

    with patch.object(ToolRegistry, "__init__", counting_init):
        proposal = ActionProposal(
            action_type="dynamic_probe_tool",
            payload={"x": 42},
            recommendation_reason="test",
            confidence=0.8,
        )
        res = MasterAgentOrchestrator.execute_proposal(proposal, "run the probe", complexity="fast")

    # ZERO extra registries constructed during execution.
    assert len(constructions) == 0, (
        f"executor constructed {len(constructions)} duplicate registries"
    )

    # The dynamic tool WAS FOUND in the shared registry: it reached the
    # ActionGate (which correctly blocks unknown actions by default). The
    # old duplicate-registry bug produced 'unsupported capability' instead,
    # because a fresh registry never saw the dynamic registration.
    assert "Gate Blocked" in (res.assistant_reply or ""), res.assistant_reply
    assert "unsupported" not in (res.assistant_reply or "").lower()


def test_goal_interpreter_fallback_never_builds_a_fresh_registry(tmp_path):
    import sys
    sys.path.insert(0, ".")
    from app.cognition.goal_interpreter import SemanticGoalInterpreter

    constructions = []
    original_init = ToolRegistry.__init__

    def counting_init(self, *a, **kw):
        constructions.append(1)
        original_init(self, *a, **kw)

    with patch.object(ToolRegistry, "__init__", counting_init):
        # No tool_registry passed: must fall back to the SHARED registry.
        SemanticGoalInterpreter.interpret_goal("check my cpu usage")
    assert constructions == []
