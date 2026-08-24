"""Preemption reconciliation applied to exact plan steps.

A reconciled-verified step is skipped (never re-executed) on resume; unknown
outcomes halt for evidence; verified failures require a fresh revision. A
verified completion is never downgraded — later contradictions are recorded.
"""
from unittest.mock import patch

from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionStep,
    TaskType,
)
from app.cognition.plan_step_reconciliation import (
    PlanStepReconciliationStore,
    STATUS_COMPLETED,
    STATUS_NEEDS_FRESH_REPLAN,
    STATUS_UNKNOWN_PENDING_EVIDENCE,
)


def make_store(tmp_path):
    return PlanStepReconciliationStore(tmp_path / "steps.db")


def make_plan():
    first = ExecutionStep(
        step_id="step_first", description="Copy report", task_type=TaskType.ANALYSIS,
        action_type="copy_file_verified", payload={"source": "a", "destination": "b"},
    )
    second = ExecutionStep(
        step_id="step_second", description="Archive report", task_type=TaskType.ANALYSIS,
        action_type="compress_files", payload={"files": ["b"]},
        depends_on=["step_first"],
    )
    return ExecutionPlan(plan_id="plan_resume", goal_id="g1", goal_title="Safely move report",
                         steps=[first, second])


def test_recommendations_map_to_step_statuses(tmp_path):
    store = make_store(tmp_path)
    step = {"step_id": "s1", "action_type": "copy_file_verified", "payload": {}}
    done = store.apply("plan1", step, "skip_verified_step_and_review_next",
                       verification={"goal_verified": True}, preemption_id="p1", execution_id="e1")
    unknown = store.apply("plan1", {**step, "step_id": "s2"}, "wait_for_evidence",
                          verification={"verification_unknown": True}, preemption_id="p1", execution_id="e1")
    failed = store.apply("plan1", {**step, "step_id": "s3"}, "create_fresh_replan",
                         verification={"goal_verified": False, "verification_unknown": False},
                         preemption_id="p1", execution_id="e1")
    assert done.status == STATUS_COMPLETED and done.goal_verified is True
    assert unknown.status == STATUS_UNKNOWN_PENDING_EVIDENCE and unknown.verification_unknown is True
    assert failed.status == STATUS_NEEDS_FRESH_REPLAN
    assert [r.status for r in store.for_plan("plan1")] == [STATUS_COMPLETED, STATUS_UNKNOWN_PENDING_EVIDENCE, STATUS_NEEDS_FRESH_REPLAN]


def test_verified_completion_is_never_downgraded(tmp_path):
    store = make_store(tmp_path)
    step = {"step_id": "s1", "action_type": "copy_file_verified", "payload": {}}
    store.apply("plan1", step, "skip_verified_step_and_review_next",
                verification={"goal_verified": True, "evidence": "file observed"}, preemption_id="p1", execution_id="e1")
    conflict = store.apply("plan1", step, "create_fresh_replan",
                           verification={"goal_verified": False, "verification_unknown": False},
                           preemption_id="p2", execution_id="e2")
    assert conflict.status == STATUS_COMPLETED  # never downgraded
    assert conflict.conflict and "keeping verified completion" in conflict.conflict
    assert len(conflict.history) == 1 and conflict.history[0]["recommendation"] == "skip_verified_step_and_review_next"


def test_apply_requires_exact_step_and_known_recommendation(tmp_path):
    store = make_store(tmp_path)
    for bad_args in (
        ("plan1", {"action_type": "x"}, "wait_for_evidence"),
        ("plan1", {"step_id": "s1"}, "not_a_recommendation"),
    ):
        try:
            store.apply(bad_args[0], bad_args[1], bad_args[2],
                        verification={}, preemption_id="p", execution_id="e")
            raised = False
        except ValueError:
            raised = True
        assert raised


def run_executor(plan, store, executed):
    executor = AutonomousGoalExecutor.__new__(AutonomousGoalExecutor)
    with patch.object(AutonomousGoalExecutor, "save_plan", lambda self, p: None), \
         patch.object(AutonomousGoalExecutor, "execute_step", lambda self, s, crt=None: executed.append(s.step_id) or setattr(s, "status", ExecutionStatus.COMPLETED) or setattr(s, "completed_at", "now")):
        with patch("app.cognition.plan_step_reconciliation.plan_step_reconciliation_store", store):
            return executor._execute_plan_steps(plan)


def test_resume_skips_verified_step_and_runs_dependents(tmp_path):
    store = make_store(tmp_path)
    plan = make_plan()
    store.apply("plan_resume", {"step_id": "step_first", "action_type": "copy_file_verified", "payload": {}},
                "skip_verified_step_and_review_next",
                verification={"goal_verified": True}, preemption_id="p1", execution_id="e1")
    executed: list = []
    finished = run_executor(plan, store, executed)
    # Verified work was NOT re-executed; the dependent step ran.
    assert executed == ["step_second"]
    assert plan.steps[0].status == ExecutionStatus.COMPLETED
    assert "skipped on resume" in plan.steps[0].result
    assert plan.steps[1].status == ExecutionStatus.COMPLETED


def test_resume_halted_by_unknown_evidence_never_reexecutes(tmp_path):
    store = make_store(tmp_path)
    plan = make_plan()
    store.apply("plan_resume", {"step_id": "step_first", "action_type": "copy_file_verified", "payload": {}},
                "wait_for_evidence",
                verification={"verification_unknown": True}, preemption_id="p1", execution_id="e1")
    executed: list = []
    finished = run_executor(plan, store, executed)
    assert executed == []  # nothing ran
    assert plan.steps[0].status == ExecutionStatus.UNVERIFIED
    assert "unknown" in plan.steps[0].error.lower()
    assert plan.steps[1].status == ExecutionStatus.PENDING  # halted; dependent untouched
    assert finished.status != ExecutionStatus.COMPLETED  # halted plans never report completed


def test_resume_halted_by_verified_failure_requires_fresh_replan(tmp_path):
    store = make_store(tmp_path)
    plan = make_plan()
    store.apply("plan_resume", {"step_id": "step_first", "action_type": "copy_file_verified", "payload": {}},
                "create_fresh_replan",
                verification={"goal_verified": False, "verification_unknown": False},
                preemption_id="p1", execution_id="e1")
    executed: list = []
    run_executor(plan, store, executed)
    assert executed == []
    assert plan.steps[0].status == ExecutionStatus.UNVERIFIED
    assert "fresh plan revision" in plan.steps[0].error
    assert plan.steps[1].status == ExecutionStatus.PENDING


def test_steps_without_reconciliation_records_run_normally(tmp_path):
    store = make_store(tmp_path)
    plan = make_plan()
    executed: list = []
    run_executor(plan, store, executed)
    assert executed == ["step_first", "step_second"]
    assert all(s.status == ExecutionStatus.COMPLETED for s in plan.steps)
