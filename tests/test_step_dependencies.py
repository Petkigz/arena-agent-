"""Regression guards for explicit step dependencies and split UNVERIFIED vs
WAITING_APPROVAL recovery."""

from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStatus,
    TaskType,
)


def _step(step_id, desc, status=ExecutionStatus.PENDING, depends_on=None, produces=None):
    return ExecutionStep(
        step_id=step_id, goal_id="g1", description=desc, task_type=TaskType.ANALYSIS,
        status=status, depends_on=depends_on or [], produces_evidence=produces or [],
    )


class _Runtime:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def process_cognitive_cycle(self, user_text, complexity):
        self.calls.append(user_text)
        r = self._results.pop(0) if self._results else {"goal_verified": True, "goal_lifecycle_state": "achieved"}
        return {**r, "assistant_reply": r.get("assistant_reply", "done")}


def test_steps_have_explicit_dependency_chain(tmp_path):
    """Generated plans must declare depends_on edges (not just list order)."""
    from app.cognition.autonomous_goal_generator import (
        AutonomousGoal, GoalSource,
    )
    goal = AutonomousGoal(title="T", description="D", source=GoalSource.SYSTEM_OPTIMIZATION, goal_id="g1")
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    plan = ex.create_execution_plan(goal)
    assert len(plan.steps) >= 3
    for i in range(1, len(plan.steps)):
        assert plan.steps[i - 1].step_id in plan.steps[i].depends_on


def test_step_blocked_by_unverified_dependency(tmp_path):
    """A step whose dependency is UNVERIFIED must NOT be executed."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    a = _step("a", "A")
    b = _step("b", "B", depends_on=["a"])
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[a, b])

    # Step A goes UNVERIFIED; the plan halts, so B is never executed.
    rt = _Runtime([{"goal_verified": False, "goal_lifecycle_state": "executing"}])
    plan = ex.execute_plan(plan, cognitive_runtime=rt)

    assert a.status == ExecutionStatus.UNVERIFIED
    assert b.status == ExecutionStatus.PENDING  # never reached
    assert len(rt.calls) == 1  # only A was actually run through the runtime


def test_blocked_dependency_helper(tmp_path):
    """_blocked_dependency reports prerequisites that are not COMPLETED."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    a = _step("a", "A", status=ExecutionStatus.UNVERIFIED)
    b = _step("b", "B", depends_on=["a"])
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[a, b])
    assert ex._blocked_dependency(b, plan) == ["a"]

    a.status = ExecutionStatus.COMPLETED
    assert ex._blocked_dependency(b, plan) == []


def test_resume_only_reattempts_waiting_approval(tmp_path):
    """resume_plan must re-attempt WAITING_APPROVAL but NOT UNVERIFIED steps."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    a = _step("a", "A")
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[a])

    rt1 = _Runtime([{"goal_verified": False, "requires_approval": True, "gate_blocked": "policy"}])
    plan = ex.execute_plan(plan, cognitive_runtime=rt1)
    assert a.status == ExecutionStatus.WAITING_APPROVAL

    # Owner approves; resume re-attempts A and it verifies.
    rt2 = _Runtime([{"goal_verified": True, "goal_lifecycle_state": "achieved"}])
    plan = ex.resume_plan(plan, cognitive_runtime=rt2)
    assert a.status == ExecutionStatus.COMPLETED


def test_reconcile_uses_verify_only_framing(tmp_path):
    """reconcile_plan must re-run UNVERIFIED steps in verify-only (observe) mode."""
    ex = AutonomousGoalExecutor(db_path=str(tmp_path / "e.db"))
    a = _step("a", "A")
    plan = ExecutionPlan(goal_id="g1", goal_title="T", steps=[a])

    rt1 = _Runtime([{"goal_verified": False, "goal_lifecycle_state": "executing"}])
    plan = ex.execute_plan(plan, cognitive_runtime=rt1)
    assert a.status == ExecutionStatus.UNVERIFIED

    rt2 = _Runtime([{"goal_verified": True, "goal_lifecycle_state": "achieved"}])
    plan = ex.reconcile_plan(plan, cognitive_runtime=rt2)
    assert a.status == ExecutionStatus.COMPLETED
    # The reconciliation re-ran the step with verify-only framing.
    assert any("Verify whether" in c for c in rt2.calls)
