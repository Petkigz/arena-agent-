"""Regression guards for evidence-driven goal generation + outcome-calibrated
goal scoring (the two remaining 'learning layer' items)."""

from app.cognition.autonomous_goal_generator import (
    AutonomousGoalGenerator,
    AutonomousGoal,
    GoalSource,
    GoalStatus,
)


def _gen(tmp_path):
    return AutonomousGoalGenerator(db_path=str(tmp_path / "g.db"))


def test_signals_produce_optimization_goal_for_resource_pressure(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"resource_pressure": {"ram_percent": 92, "cpu_percent": 30, "disk_percent": 40}})
    assert any(g.source == GoalSource.SYSTEM_OPTIMIZATION for g in goals)


def test_signals_ignore_normal_resource_pressure(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"resource_pressure": {"ram_percent": 40, "cpu_percent": 30, "disk_percent": 40}})
    assert goals == []


def test_signals_produce_information_gap_for_stale_beliefs(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"stale_beliefs": ["chrome.status", "disk.full"]})
    assert any(g.source == GoalSource.INFORMATION_GAP for g in goals)
    assert len([g for g in goals if g.source == GoalSource.INFORMATION_GAP]) == 2


def test_signals_produce_optimization_for_failed_actions(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"failed_actions": ["open_application", "web_search"]})
    assert any(g.source == GoalSource.SYSTEM_OPTIMIZATION for g in goals)


def test_signals_produce_investigation_for_high_surprisal(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"prediction_error": 0.8})
    assert any(g.source == GoalSource.CURIOSITY for g in goals)


def test_signals_ignore_low_surprisal(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"prediction_error": 0.1})
    assert goals == []


def test_signals_produce_optimization_for_low_success_rate(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({"low_success_rate": 0.4})
    assert any(g.source == GoalSource.SYSTEM_OPTIMIZATION for g in goals)


def test_signals_no_goals_when_everything_healthy(tmp_path):
    gen = _gen(tmp_path)
    goals = gen.generate_goals_from_signals({
        "resource_pressure": {"ram_percent": 30, "cpu_percent": 20, "disk_percent": 30},
        "low_success_rate": 0.9,
        "prediction_error": 0.0,
    })
    assert goals == []


def _make_goal(source, status):
    return AutonomousGoal(
        title=f"g-{source.value}", description="d", source=source,
        status=status, estimated_effort="medium",
    )


def test_evaluate_goal_calibrates_feasibility_down_after_failures(tmp_path):
    gen = _gen(tmp_path)
    # Record 3 past FAILED goals of the same source.
    for _ in range(3):
        gen.add_goal(_make_goal(GoalSource.SYSTEM_OPTIMIZATION, GoalStatus.FAILED))

    goal = _make_goal(GoalSource.SYSTEM_OPTIMIZATION, GoalStatus.PROPOSED)
    goal.estimated_effort = "medium"
    gen.evaluate_goal(goal)

    # Heuristic feasibility for "medium" effort is 0.7; observed success rate is
    # 0.0, so calibration must pull feasibility DOWN.
    assert goal.feasibility_score < 0.7


def test_evaluate_goal_calibrates_feasibility_up_after_successes(tmp_path):
    gen = _gen(tmp_path)
    for _ in range(3):
        gen.add_goal(_make_goal(GoalSource.SYSTEM_OPTIMIZATION, GoalStatus.COMPLETED))

    goal = _make_goal(GoalSource.SYSTEM_OPTIMIZATION, GoalStatus.PROPOSED)
    goal.estimated_effort = "high"
    gen.evaluate_goal(goal)

    # Heuristic feasibility for "high" effort is 0.5; observed success rate is
    # 1.0, so calibration must pull feasibility UP.
    assert goal.feasibility_score > 0.5


def test_evaluate_goal_ignores_small_samples(tmp_path):
    gen = _gen(tmp_path)
    # Only 1 past outcome — below MIN_OUTCOME_SAMPLES → no calibration.
    gen.add_goal(_make_goal(GoalSource.SYSTEM_OPTIMIZATION, GoalStatus.FAILED))

    goal = _make_goal(GoalSource.SYSTEM_OPTIMIZATION, GoalStatus.PROPOSED)
    goal.estimated_effort = "medium"
    gen.evaluate_goal(goal)

    # Heuristic feasibility unchanged (0.7 for medium effort).
    assert goal.feasibility_score == 0.7


def test_goal_outcome_stats(tmp_path):
    gen = _gen(tmp_path)
    for _ in range(2):
        gen.add_goal(_make_goal(GoalSource.MAINTENANCE, GoalStatus.COMPLETED))
    gen.add_goal(_make_goal(GoalSource.MAINTENANCE, GoalStatus.FAILED))

    rate, attempts = gen._goal_outcome_stats(GoalSource.MAINTENANCE)
    assert attempts == 3
    assert abs(rate - 2 / 3) < 1e-6

    # A source with no outcomes → None.
    assert gen._goal_outcome_stats(GoalSource.CURIOSITY) is None
