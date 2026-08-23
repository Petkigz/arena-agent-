"""Editable plan review: revision-bound approval before non-sensitive execution."""

from unittest.mock import patch

import pytest

from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionStep,
    TaskType,
)
from app.cognition.owner_control import OwnerControlStore, authorized_plan_scope
from app.cognition.plan_control import PlanReviewStatus, PlanReviewStore


def _plan() -> ExecutionPlan:
    first = ExecutionStep(
        step_id="step_a",
        goal_id="goal_1",
        description="Inspect current state",
        task_type=TaskType.ANALYSIS,
        produces_evidence=["state"],
    )
    second = ExecutionStep(
        step_id="step_b",
        goal_id="goal_1",
        description="Draft the result",
        task_type=TaskType.USER_ASSISTANCE,
        depends_on=["step_a"],
        requires_evidence=["state"],
    )
    return ExecutionPlan(plan_id="plan_review_1", goal_id="goal_1", goal_title="Review me", steps=[first, second])


def test_edit_creates_new_revision_and_requires_fresh_approval(tmp_path):
    store = PlanReviewStore(tmp_path / "reviews.db")
    review = store.submit(_plan())
    approved = store.decide(review.plan_id, review.revision, True, "looks good")
    assert approved.status == PlanReviewStatus.APPROVED

    edited_steps = approved.snapshot["steps"]
    edited_steps[1] = {**edited_steps[1], "description": "Draft a concise result"}
    edited = store.edit(approved.plan_id, approved.revision, edited_steps)

    assert edited.revision == 2
    assert edited.status == PlanReviewStatus.PENDING
    with pytest.raises(ValueError, match="revision conflict"):
        store.decide(edited.plan_id, 1, True)


def test_plan_editor_rejects_unknown_dependencies_and_cycles(tmp_path):
    store = PlanReviewStore(tmp_path / "reviews.db")
    review = store.submit(_plan())
    steps = review.snapshot["steps"]

    broken = [{**steps[0], "depends_on": ["missing"]}, steps[1]]
    with pytest.raises(ValueError, match="Unknown dependency"):
        store.edit(review.plan_id, review.revision, broken)

    cyclic = [
        {**steps[0], "depends_on": ["step_b"]},
        {**steps[1], "depends_on": ["step_a"]},
    ]
    with pytest.raises(ValueError, match="cycle"):
        store.edit(review.plan_id, review.revision, cyclic)


def test_approve_each_plan_halts_before_any_step(tmp_path):
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.update({"mode": "approve_each_plan"})
    reviews = PlanReviewStore(tmp_path / "reviews.db")
    executor = AutonomousGoalExecutor(db_path=str(tmp_path / "execution.db"))
    plan = _plan()

    with (
        patch("app.cognition.owner_control.owner_control_store", policy),
        patch("app.cognition.plan_control.plan_review_store", reviews),
    ):
        result = executor.execute_plan(plan, cognitive_runtime=None)

    assert result.status == ExecutionStatus.WAITING_APPROVAL
    assert all(step.status == ExecutionStatus.PENDING for step in result.steps)
    review = reviews.get(plan.plan_id)
    assert review is not None and review.status == PlanReviewStatus.PENDING


def test_approved_edited_snapshot_is_the_executed_plan(tmp_path):
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.update({"mode": "approve_each_plan"})
    reviews = PlanReviewStore(tmp_path / "reviews.db")
    executor = AutonomousGoalExecutor(db_path=str(tmp_path / "execution.db"))
    plan = _plan()
    review = reviews.submit(plan)
    steps = review.snapshot["steps"]
    steps[0] = {**steps[0], "description": "Inspect only the approved workspace"}
    edited = reviews.edit(plan.plan_id, review.revision, steps)
    reviews.decide(plan.plan_id, edited.revision, True)

    with (
        patch("app.cognition.owner_control.owner_control_store", policy),
        patch("app.cognition.plan_control.plan_review_store", reviews),
    ):
        result = executor.execute_plan(plan, cognitive_runtime=None)

    assert result.steps[0].description == "Inspect only the approved workspace"
    assert result.steps[0].status == ExecutionStatus.UNVERIFIED


def test_rejected_or_revoked_plan_is_cancelled(tmp_path):
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.update({"mode": "approve_each_plan"})
    reviews = PlanReviewStore(tmp_path / "reviews.db")
    executor = AutonomousGoalExecutor(db_path=str(tmp_path / "execution.db"))
    plan = _plan()
    review = reviews.submit(plan)
    reviews.decide(plan.plan_id, review.revision, False, "not acceptable")

    with (
        patch("app.cognition.owner_control.owner_control_store", policy),
        patch("app.cognition.plan_control.plan_review_store", reviews),
    ):
        result = executor.execute_plan(plan, cognitive_runtime=None)

    assert result.status == ExecutionStatus.CANCELLED
    assert all(step.status == ExecutionStatus.PENDING for step in result.steps)


def test_approved_plan_scope_never_covers_level3_or_explicit_action_rule(tmp_path):
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.update({
        "mode": "approve_each_plan",
        "max_autonomous_level": 2,
        "require_approval_actions": ["open_application"],
    })

    assert policy.evaluate("read_file", 0).requires_approval is True
    with authorized_plan_scope("plan_1", 2):
        assert policy.evaluate("read_file", 0).allowed is True
        assert policy.evaluate("create_note", 1).allowed is True
        assert policy.evaluate("send_email", 3).requires_approval is True
        assert policy.evaluate("open_application", 2).requires_approval is True
