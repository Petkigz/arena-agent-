"""Regression guards for plan dependencies (pause on UNVERIFIED) and resumable
approval (WAITING_APPROVAL is a resume point, not a deferral)."""

from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStatus,
    TaskType,
)
from app.cognition.autonomous_goal_generator import GoalStatus


def _step(desc, status=ExecutionStatus.PENDING):
    return ExecutionStep(goal_id="g1", description=desc, task_type=TaskType.ANALYSIS, status=status)


class _Runtime:
    """Returns a fixed cycle result for every step."""
    def __init__(self, result):
        self._result = result

    def process_cognitive_cycle(self, user_text, complexity):
        return self._result


def test_plan_halts_after_unverified_step(tmp_path):
    """🟠 fix: an UNVERIFIED step pauses the plan; later steps are not executed."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))
    rt = _Runtime({"goal_verified": False, "assistant_reply": "maybe", "goal_lifecycle_state": "executing"})
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[_step("A"), _step("B"), _step("C")])
    plan = ex.execute_plan(plan, cognitive_runtime=rt)

    assert plan.steps[0].status == ExecutionStatus.UNVERIFIED
    # Steps B and C were NOT executed — they stay PENDING.
    assert plan.steps[1].status == ExecutionStatus.PENDING
    assert plan.steps[2].status == ExecutionStatus.PENDING
    assert plan.status == ExecutionStatus.PARTIAL


def test_plan_waits_on_approval_and_resumes(tmp_path):
    """WAITING_APPROVAL is a resume point: resume_plan re-attempts the gated step."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "a.db"))

    # First, a gated Level-3 action → WAITING_APPROVAL.
    rt_gated = _Runtime({"goal_verified": False, "requires_approval": True, "gate_blocked": "policy", "assistant_reply": "needs approval"})
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[_step("A")])
    plan = ex.execute_plan(plan, cognitive_runtime=rt_gated)
    assert plan.steps[0].status == ExecutionStatus.WAITING_APPROVAL
    assert plan.status == ExecutionStatus.WAITING_APPROVAL

    # Owner approves; the same step now verifies on re-execution.
    rt_approved = _Runtime({"goal_verified": True, "assistant_reply": "done", "goal_lifecycle_state": "achieved"})
    plan = ex.resume_plan(plan, cognitive_runtime=rt_approved)
    assert plan.steps[0].status == ExecutionStatus.COMPLETED
    assert plan.status == ExecutionStatus.COMPLETED


def test_execute_next_goal_maps_waiting_approval(tmp_path):
    """A WAITING_APPROVAL plan must map the goal to WAITING_APPROVAL, not DEFERRED."""
    from app.cognition.autonomous_goal_generator import (
        AutonomousGoalGenerator, AutonomousGoal, GoalSource,
    )
    gen = AutonomousGoalGenerator(db_path=str(tmp_path / "g.db"))
    goal = AutonomousGoal(title="T", description="D", source=GoalSource.MAINTENANCE, status=GoalStatus.APPROVED)
    gen.add_goal(goal)

    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    rt = _Runtime({"goal_verified": False, "requires_approval": True, "gate_blocked": "policy", "assistant_reply": "needs approval"})

    plan = ex.execute_next_goal(gen, cognitive_runtime=rt)
    assert plan is not None
    assert plan.status == ExecutionStatus.WAITING_APPROVAL
    updated = gen.get_goal(goal.goal_id)
    assert updated.status == GoalStatus.WAITING_APPROVAL
