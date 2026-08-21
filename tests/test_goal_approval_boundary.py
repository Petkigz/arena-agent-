"""Regression guards for the P0 goal-approval ≠ action-authorization boundary."""

from app.cognition.autonomous_goal_generator import (
    AutonomousGoalGenerator,
    AutonomousGoal,
    GoalApproval,
    GoalSource,
    GoalPriority,
    GoalStatus,
)


def _make_goal(generator):
    goal = AutonomousGoal(
        title="Improve system configuration",
        description="Tune system config for performance",
        source=GoalSource.SYSTEM_OPTIMIZATION,
        priority=GoalPriority.HIGH,
        overall_score=0.82,
    )
    generator.add_goal(goal)
    return goal


def test_approve_goal_sets_planning_boundary(tmp_path):
    gen = AutonomousGoalGenerator(db_path=str(tmp_path / "g.db"))
    goal = _make_goal(gen)
    gen.evaluate_goal(goal)

    assert gen.approve_goal(goal.goal_id, auto_approve_threshold=0.7) is True

    stored = gen.get_goal(goal.goal_id)
    # Approved for PLANNING, with an explicit action-level boundary.
    assert stored.status == GoalStatus.APPROVED
    assert stored.max_action_level == 2  # Level 3 still needs owner approval
    assert stored.requires_owner_approval is True


def test_goal_approval_is_planning_not_execution(tmp_path):
    """Approving a goal must NOT grant execution_allowed."""
    gen = AutonomousGoalGenerator(db_path=str(tmp_path / "g.db"))
    goal = _make_goal(gen)
    approval = gen.build_goal_approval(goal)

    assert approval.planning_allowed is True
    assert approval.execution_allowed is False
    assert approval.max_action_level == 2


def test_approval_boundary_survives_roundtrip(tmp_path):
    """max_action_level + requires_owner_approval persist through the DB."""
    gen = AutonomousGoalGenerator(db_path=str(tmp_path / "g.db"))
    goal = _make_goal(gen)
    goal.max_action_level = 1
    goal.requires_owner_approval = True
    gen.add_goal(goal)

    reloaded = AutonomousGoalGenerator(db_path=str(tmp_path / "g.db"))
    stored = reloaded.get_goal(goal.goal_id)
    assert stored.max_action_level == 1
    assert stored.requires_owner_approval is True


def test_goal_approval_dataclass_shape():
    a = GoalApproval(goal_id="g1")
    assert a.planning_allowed is True
    assert a.execution_allowed is False
    assert a.max_action_level == 2
    assert a.requires_owner_approval is False  # default before planning runs
    assert "Level 3" in a.policy_snapshot
