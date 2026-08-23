"""Outcome-calibrated thresholds and owner-bounded curiosity."""

from types import SimpleNamespace

from app.cognition.adaptive_autonomy import AdaptiveAutonomyCalibrator
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator, GoalSource
from app.cognition.strategy_outcomes import StrategyOutcomeStore


def _outcomes(tmp_path, successes, surprisals):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = StrategyOutcomeStore(str(tmp_path / "outcomes.db"))
    for index, success in enumerate(successes):
        store.record_outcome(
            goal_type="test",
            action_type="search_files",
            success=success,
            surprisal=surprisals[index],
            goal_text=f"goal {index}",
        )
    return store


def test_calibration_waits_for_minimum_verified_samples(tmp_path):
    outcomes = _outcomes(tmp_path, [True, False], [0.1, 0.9])
    calibrator = AdaptiveAutonomyCalibrator(tmp_path / "profile.json")

    profile = calibrator.calibrate(outcomes)

    assert profile.sample_count == 2
    assert profile.source == "defaults_insufficient_samples"
    assert profile.prediction_error_threshold == 0.5


def test_thresholds_adapt_to_observed_success_and_surprisal(tmp_path):
    high_outcomes = _outcomes(
        tmp_path / "high", [True] * 8, [0.7, 0.8, 0.9, 0.6, 0.85, 0.75, 0.8, 0.9]
    )
    low_outcomes = _outcomes(
        tmp_path / "low", [False] * 8, [0.05, 0.1, 0.2, 0.15, 0.1, 0.2, 0.05, 0.1]
    )
    high = AdaptiveAutonomyCalibrator(tmp_path / "high.json").calibrate(high_outcomes)
    low = AdaptiveAutonomyCalibrator(tmp_path / "low.json").calibrate(low_outcomes)

    assert high.prediction_error_threshold > low.prediction_error_threshold
    assert high.goal_auto_approve_threshold < low.goal_auto_approve_threshold
    assert high.exploration_budget == 3
    assert low.exploration_budget == 1
    assert high.source == "verified_strategy_outcomes"


def test_owner_exploration_cap_is_persistent_and_absolute(tmp_path):
    path = tmp_path / "profile.json"
    calibrator = AdaptiveAutonomyCalibrator(path)
    calibrator.set_owner_max_exploration_goals(1)
    outcomes = _outcomes(tmp_path, [True] * 6, [0.5] * 6)

    profile = calibrator.calibrate(outcomes)
    restored = AdaptiveAutonomyCalibrator(path).get_profile()

    assert profile.exploration_budget == 1
    assert restored.owner_max_exploration_goals == 1
    assert restored.exploration_budget == 1


def test_signal_generation_uses_supplied_thresholds(tmp_path):
    generator = AutonomousGoalGenerator(db_path=str(tmp_path / "goals.db"))

    strict = generator.generate_goals_from_signals(
        {"prediction_error": 0.6, "low_success_rate": 0.55},
        thresholds={
            "prediction_error_threshold": 0.7,
            "low_success_rate_threshold": 0.5,
            "exploration_budget": 3,
        },
    )
    adaptive = generator.generate_goals_from_signals(
        {"prediction_error": 0.6, "low_success_rate": 0.55},
        thresholds={
            "prediction_error_threshold": 0.5,
            "low_success_rate_threshold": 0.6,
            "exploration_budget": 3,
        },
    )

    assert strict == []
    assert any(goal.source == GoalSource.CURIOSITY for goal in adaptive)
    assert any(goal.source == GoalSource.SYSTEM_OPTIMIZATION for goal in adaptive)


def test_exploration_budget_caps_structured_and_information_gain_goals(tmp_path):
    generator = AutonomousGoalGenerator(db_path=str(tmp_path / "goals.db"))
    structured = generator.generate_goals_from_signals(
        {
            "unknown_entities": ["a", "b", "c"],
            "low_confidence_groundings": ["d", "e"],
            "weak_causal_edges": ["f", "g"],
        },
        thresholds={"exploration_budget": 2},
    )
    assert len([
        goal for goal in structured
        if goal.source in (GoalSource.CURIOSITY, GoalSource.INFORMATION_GAP)
    ]) == 2

    world = SimpleNamespace(find_entities=lambda: [
        SimpleNamespace(name="x", confidence=0.1),
        SimpleNamespace(name="y", confidence=0.2),
        SimpleNamespace(name="z", confidence=0.3),
    ])
    info = generator.generate_goals_from_information_gain(
        world_model=world,
        thresholds={
            "unknown_entity_confidence": 0.5,
            "exploration_budget": 1,
        },
    )
    assert len(info) == 1


def test_zero_owner_budget_disables_curiosity_but_not_optimization(tmp_path):
    generator = AutonomousGoalGenerator(db_path=str(tmp_path / "goals.db"))
    goals = generator.generate_goals_from_signals(
        {
            "unknown_entities": ["unknown"],
            "failed_actions": ["search_files"],
        },
        thresholds={"exploration_budget": 0},
    )

    assert not any(goal.source in (GoalSource.CURIOSITY, GoalSource.INFORMATION_GAP) for goal in goals)
    assert any(goal.source == GoalSource.SYSTEM_OPTIMIZATION for goal in goals)
