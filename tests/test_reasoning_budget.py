"""P0 bottleneck #13: the reasoning loop is governed by a multi-dimensional
BUDGET (time / tool calls / risk), not an arbitrary step count. 'One more
investigation would solve it' is a resource decision now, honestly named."""
from app.cognition.action_selection import ActionSelector, ActionResult, InvestigationPlan
from app.cognition.belief_engine import BeliefEngine
from app.cognition.information_gain import InformationNeed
from app.cognition.reasoning_loop import CognitiveReasoningLoop, ReasoningBudget


class Exec:
    def __init__(self):
        self.calls = []

    def register(self, name, tool):
        pass

    def execute(self, plan):
        self.calls.append(plan.tool)
        return ActionResult(True, plan.tool, output="ok")


def _loop(n_targets=5):
    selector = ActionSelector()
    for i in range(n_targets):
        selector.registry.register(
            f"target_{i}",
            lambda n, i=i: InvestigationPlan(tool=f"probe_{i}", arguments={},
                                             target=n.target, reason=n.reason,
                                             priority=n.priority))
    return CognitiveReasoningLoop(engine=BeliefEngine(), action_selector=selector, executor=Exec())


def _needs(n=5):
    return [InformationNeed(question=f"q{i}", target=f"target_{i}", reason="r") for i in range(n)]


def test_budget_allows_more_than_three_investigations():
    """The user's exact complaint: the old default stopped at 3 even when
    one more investigation would solve the problem."""
    trace = _loop().run("s", "status", value="v", source="self_reported",
                        confidence=0.2, information_needs=_needs())
    assert len(trace.results) == 5
    assert trace.budget_used["tool_calls"] == 5


def test_tool_call_budget_exhaustion_is_honest_and_named():
    loop = _loop()
    trace = loop.run("s", "status", value="v", source="self_reported", confidence=0.2,
                     information_needs=_needs(),
                     budget=ReasoningBudget(time_s=10, max_tool_calls=2, max_risk=2, max_steps=20))
    assert len(trace.results) == 2
    assert "tool-call budget exhausted" in trace.reason
    assert "remaining information needs: 3" in trace.reason


def test_time_budget_exhaustion_is_honest():
    trace = _loop().run("s", "status", value="v", source="self_reported", confidence=0.2,
                        information_needs=_needs(),
                        budget=ReasoningBudget(time_s=0.0, max_tool_calls=8, max_risk=6, max_steps=20))
    assert len(trace.results) == 0
    assert "time budget exhausted" in trace.reason


def test_risk_budget_gates_level1_probes():
    """A Level-1 planned probe costs risk; with zero risk budget it is
    declined BEFORE execution (honest escalation, never a silent skip)."""
    from unittest.mock import patch
    from app.tools.manifest import get_tool_manifest
    level1 = next(n for n, e in get_tool_manifest().items() if e.get("safety_level") == 1)

    selector = ActionSelector()
    selector.registry.register("t", lambda n: InvestigationPlan(
        tool=level1, arguments={}, target=n.target, reason=n.reason, priority=n.priority))
    loop = CognitiveReasoningLoop(engine=BeliefEngine(), action_selector=selector, executor=Exec())
    trace = loop.run("s", "status", value="v", source="self_reported", confidence=0.2,
                     information_needs=[InformationNeed("q", "t", "r")],
                     budget=ReasoningBudget(time_s=10, max_tool_calls=8, max_risk=0.0, max_steps=20))
    assert "risk budget exhausted" in trace.reason
    assert trace.results == []


def test_budgets_scale_with_complexity():
    fast = ReasoningBudget.for_complexity("fast")
    main = ReasoningBudget.for_complexity("main")
    deep = ReasoningBudget.for_complexity("deep")
    assert fast.max_tool_calls < main.max_tool_calls < deep.max_tool_calls
    assert fast.time_s < main.time_s < deep.time_s
    assert fast.max_tokens is not None  # threaded for LLM-layer enforcement


def test_budget_used_is_reported_on_every_exit():
    trace = _loop(n_targets=1).run(
        "s", "status", value="v", source="self_reported", confidence=0.2,
        information_needs=_needs(1))
    # Even a clean decision exit reports what was spent.
    assert trace.budget_used.get("tool_calls") == 1
    assert "limits" in trace.budget_used


def test_step_ceiling_remains_as_safety_net():
    """The constructor's max_steps still hard-caps iterations regardless of
    budget (a safety net, not the governing bound)."""
    trace = _loop().run("s", "status", value="v", source="self_reported", confidence=0.2,
                        information_needs=_needs(5),
                        budget=ReasoningBudget(time_s=30, max_tool_calls=8, max_risk=6, max_steps=3))
    assert len(trace.results) == 3
