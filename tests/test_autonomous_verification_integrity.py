"""Regression guards for the P0 autonomous-execution integrity fixes.

The autonomous executor must consume the cognitive cycle's GoalVerifier verdict
and the ActionGate result — it must NEVER mark a step COMPLETED just because the
cycle returned a reply.
"""

from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionStep,
    ExecutionStatus,
    TaskType,
)


def _make_step():
    return ExecutionStep(goal_id="g1", description="Optimize system", task_type=TaskType.OPTIMIZATION)


class _Runtime:
    """A mock cognitive runtime returning a configurable cycle result."""
    def __init__(self, result):
        self._result = result

    def process_cognitive_cycle(self, user_text, complexity):
        return self._result


def test_step_completed_only_when_goal_verified(tmp_path):
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({"goal_verified": True, "assistant_reply": "optimized", "goal_lifecycle_state": "achieved"})
    step = ex.execute_step(_make_step(), cognitive_runtime=rt)
    assert step.status == ExecutionStatus.COMPLETED
    # Confidence is evidence-derived, NOT a hard-coded 1.0: this mock has no
    # environmental observation (no executed_actions/reasoning_action), so it's a
    # conversational verification → 0.7.
    assert step.confidence == 0.7


def test_step_failed_when_verification_fails(tmp_path):
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({"goal_verified": False, "assistant_reply": "it failed", "goal_lifecycle_state": "failed"})
    step = ex.execute_step(_make_step(), cognitive_runtime=rt)
    assert step.status == ExecutionStatus.FAILED


def test_step_unverified_when_no_evidence(tmp_path):
    """The core P0 #1 bug: 'the cycle returned a reply' must NOT mean COMPLETED."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({
        "goal_verified": False,
        "assistant_reply": "I've implemented the optimization.",
        "goal_lifecycle_state": "executing",  # never reached a verified terminal state
    })
    step = ex.execute_step(_make_step(), cognitive_runtime=rt)
    assert step.status == ExecutionStatus.UNVERIFIED
    assert step.status != ExecutionStatus.COMPLETED


def test_step_waiting_approval_on_level3(tmp_path):
    """P0 #2: a gated Level-3 action must not be treated as completed."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({
        "goal_verified": False,
        "requires_approval": True,
        "gate_blocked": "policy",
        "assistant_reply": "Action requires owner approval",
    })
    step = ex.execute_step(_make_step(), cognitive_runtime=rt)
    assert step.status == ExecutionStatus.WAITING_APPROVAL


def test_plan_not_completed_with_unverified_steps(tmp_path):
    """A plan is COMPLETED only when every step is verified."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({
        "goal_verified": False,
        "assistant_reply": "done-ish",
        "goal_lifecycle_state": "executing",
    })
    from app.cognition.autonomous_goal_executor import ExecutionPlan
    plan = ExecutionPlan(goal_id="g1", goal_title="Optimize", steps=[_make_step(), _make_step()])
    plan = ex.execute_plan(plan, cognitive_runtime=rt)
    assert plan.status != ExecutionStatus.COMPLETED
    assert plan.status == ExecutionStatus.PARTIAL  # all unverified → partial


def test_plan_completed_when_all_verified(tmp_path):
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({"goal_verified": True, "assistant_reply": "ok", "goal_lifecycle_state": "achieved"})
    from app.cognition.autonomous_goal_executor import ExecutionPlan
    plan = ExecutionPlan(goal_id="g1", goal_title="Optimize", steps=[_make_step()])
    plan = ex.execute_plan(plan, cognitive_runtime=rt)
    assert plan.status == ExecutionStatus.COMPLETED
