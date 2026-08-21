"""Regression guards for StepVerifier — the layer that separates step-level
verification from goal-level verification.

The core P0: a step with a declared evidence/criteria contract must NOT be marked
COMPLETED just because the cognitive cycle returned goal_verified=True via a
conversational ANSWER (which only means "a reply was delivered").
"""

from app.cognition.step_verifier import StepVerifier, StepVerificationResult
from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionStep,
    ExecutionStatus,
    TaskType,
)


class _Step:
    def __init__(self, produces=None, requires=None, success=None, failure=None):
        self.produces_evidence = produces or []
        self.requires_evidence = requires or []
        self.success_criteria = success or []
        self.failure_conditions = failure or []


def test_evidence_declaring_step_with_answer_is_unverified():
    """THE leak: goal_verified=True via ANSWER must NOT complete an evidence step."""
    step = _Step(produces=["current_state"])
    result = {
        "goal_verified": True,
        "goal_lifecycle_state": "achieved",
        "reasoning_action": "answer",
        "executed_actions": [],
        "assistant_reply": "I've analyzed the current state.",
    }
    v = StepVerifier.verify_step(step, result, available_evidence=None)
    assert v.status == "unverified"
    assert v.confidence == 0.5


def test_evidence_declaring_step_with_observation_is_verified():
    step = _Step(produces=["current_state"])
    result = {
        "goal_verified": True,
        "goal_lifecycle_state": "achieved",
        "reasoning_action": "act",
        "executed_actions": [{"action_type": "system_probe"}],
        "assistant_reply": "observed",
    }
    v = StepVerifier.verify_step(step, result, available_evidence=None)
    assert v.status == "verified"
    assert v.confidence == 0.9


def test_plain_step_without_declared_evidence_can_be_conversational():
    """A step declaring NO evidence contract may be verified conversationally."""
    step = _Step()
    result = {"goal_verified": True, "goal_lifecycle_state": "achieved", "reasoning_action": "answer", "executed_actions": []}
    v = StepVerifier.verify_step(step, result, available_evidence=None)
    assert v.status == "verified"
    assert v.confidence == 0.7  # conversational, not 1.0


def test_failed_lifecycle_maps_to_failed():
    step = _Step(failure=["app_running"])
    result = {"goal_verified": False, "goal_lifecycle_state": "failed", "assistant_reply": "it crashed"}
    v = StepVerifier.verify_step(step, result, available_evidence=None)
    assert v.status == "failed"
    assert v.confidence == 0.0


def test_requires_evidence_enforced_when_set_provided():
    step = _Step(requires=["root_cause"])
    result = {"goal_verified": True, "goal_lifecycle_state": "achieved", "reasoning_action": "act", "executed_actions": [{}]}
    # Evidence "root_cause" not in the available set → unverified.
    v = StepVerifier.verify_step(step, result, available_evidence={"current_state"})
    assert v.status == "unverified"
    # And verified when the evidence IS available.
    v2 = StepVerifier.verify_step(step, result, available_evidence={"current_state", "root_cause"})
    assert v2.status == "verified"


def test_plan_enforces_requires_evidence_dataflow(tmp_path):
    """A step requiring evidence never produced by a COMPLETED step is blocked."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    a = ExecutionStep(step_id="a", goal_id="g1", description="A", task_type=TaskType.ANALYSIS,
                      produces_evidence=["current_state"])
    b = ExecutionStep(step_id="b", goal_id="g1", description="B", task_type=TaskType.ANALYSIS,
                      requires_evidence=["root_cause"])  # nobody produces this

    # Step A completes (observed); step B requires evidence A didn't produce.
    class Runtime:
        def process_cognitive_cycle(self, user_text, complexity):
            return {
                "goal_verified": True, "assistant_reply": "ok",
                "goal_lifecycle_state": "achieved", "reasoning_action": "act",
                "executed_actions": [{"action_type": "probe"}],
            }

    from app.cognition.autonomous_goal_executor import ExecutionPlan
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[a, b])
    plan = ex.execute_plan(plan, cognitive_runtime=Runtime())

    assert plan.steps[0].status == ExecutionStatus.COMPLETED
    # B is blocked: it requires "root_cause" which A never produced.
    assert plan.steps[1].status == ExecutionStatus.UNVERIFIED
    assert "evidence" in (plan.steps[1].error or "").lower() or "required evidence" in (plan.steps[1].error or "").lower()


def test_executor_uses_step_verifier_not_goal_verifier(tmp_path):
    """End-to-end: a generated evidence step + conversational answer → UNVERIFIED."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    step = ExecutionStep(
        goal_id="g1", description="Analyze current state", task_type=TaskType.ANALYSIS,
        produces_evidence=["current_state"],
    )
    class AnswerRuntime:
        def process_cognitive_cycle(self, user_text, complexity):
            return {
                "goal_verified": True,
                "assistant_reply": "I've analyzed the current state.",
                "goal_lifecycle_state": "achieved",
                "reasoning_action": "answer",
                "executed_actions": [],
            }
    step = ex.execute_step(step, cognitive_runtime=AnswerRuntime())
    assert step.status == ExecutionStatus.UNVERIFIED
    assert step.confidence == 0.5
