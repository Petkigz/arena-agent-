from unittest.mock import patch
from app.cognition.runtime import CognitiveRuntime
from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
from app.cognition.reasoning_loop import CycleTrace
from app.cognition.action_proposal import ActionProposal, GateResult


def test_defer_decision_transitions_to_deferred_lifecycle_state(tmp_path):
    """
    Verify DEFER decisions transition GoalTracker to GoalLifecycleState.DEFERRED
    rather than FAILED.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.DEFER, confidence=0.0, reason="Capability phone.adb unavailable")]
    )

    with patch.object(runtime.loop, "run", return_value=mock_trace):
        res = runtime.process_cognitive_cycle(user_text="Call John on mobile phone")

        assert res["goal_lifecycle_state"] == GoalLifecycleState.DEFERRED.value
        assert res["reasoning_action"] == "defer"


def test_gate_block_transitions_to_blocked_lifecycle_state(tmp_path):
    """
    Verify ActionGate blocking transitions GoalTracker to GoalLifecycleState.BLOCKED.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ACT, confidence=0.9, reason="Action required")]
    )

    gate_block = GateResult(allowed=False, gate_name="policy_gate", reason="Action blocked by security policy", requires_approval=False)

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.cognition.action_proposal.ActionGate.evaluate_proposal", return_value=gate_block):

        res = runtime.process_cognitive_cycle(user_text="launch_app notepad")

        assert res["success"] is False
        assert res["goal_lifecycle_state"] == GoalLifecycleState.BLOCKED.value


def test_gate_approval_transitions_to_waiting_for_user_lifecycle_state(tmp_path):
    """
    Verify Level 3 sensitive actions requiring approval transition to WAITING_FOR_USER.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ACT, confidence=0.9, reason="Action required")]
    )

    gate_approval = GateResult(allowed=False, gate_name="policy_gate", reason="Level 3 action requires UI approval", requires_approval=True)

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.cognition.action_proposal.ActionGate.evaluate_proposal", return_value=gate_approval):

        res = runtime.process_cognitive_cycle(user_text="delete workspace files")

        assert res["success"] is False
        assert res["requires_approval"] is True
        assert res["goal_lifecycle_state"] == GoalLifecycleState.WAITING_FOR_USER.value
