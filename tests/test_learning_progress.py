"""Learning-progress motivation: explore where competence is growing.

Windowed success rates from the action-outcome store rank exploration targets
(weak-but-improving wins; mastered flat domains don't). Insufficient data
scores nothing. The owner's exploration cap and all gates stay authoritative.
"""
from app.cognition.action_outcomes import ActionOutcomeStore
from app.cognition.learning_progress import LearningProgressTracker


def seeded_store(tmp_path, histories):
    """histories: {action_type: [(outcome, n_repeats), ...]} appended in order."""
    store = ActionOutcomeStore(tmp_path / "ao.db")
    counter = 0
    for action_type, phases in histories.items():
        for outcome, repeats in phases:
            for _ in range(repeats):
                counter += 1
                store.record(action_type, {"i": counter}, outcome, execution_id=f"e{counter}")
    return store


def test_improving_domain_outranks_mastered_and_flat(tmp_path):
    store = seeded_store(tmp_path, {
        # Improving: earlier 2/6 ≈ 0.33 → recent 5/6 ≈ 0.83.
        "browser_upload": [("verified_failure", 4), ("verified_success", 1), ("verified_success", 5)],
        # Mastered: 10/10 throughout.
        "search_files": [("verified_success", 10)],
        # Flat-weak: 1/10 then 1/10.
        "system_update": [("verified_failure", 4), ("verified_success", 1), ("verified_failure", 4), ("verified_success", 0)],
    })
    tracker = LearningProgressTracker(store.db_path)
    upload = tracker.progress_for("browser_upload")
    assert upload.status == "improving" and upload.progress > 0.3
    assert upload.learning_value > 0.2

    mastered = tracker.progress_for("search_files")
    assert mastered.status == "mastered" and mastered.learning_value < upload.learning_value

    report = tracker.report()
    assert report["targets"][0]["action_type"] in ("browser_upload", "system_update")
    assert "exploration cap" in report["note"]


def test_insufficient_data_scores_nothing_and_is_labeled(tmp_path):
    store = seeded_store(tmp_path, {
        "once_only": [("verified_success", 1)],
        "all_unknown": [("verification_unknown", 8)],
    })
    tracker = LearningProgressTracker(store.db_path)
    once = tracker.progress_for("once_only")
    assert once.status == "insufficient_data" and once.learning_value == 0.0
    unknown = tracker.progress_for("all_unknown")
    assert unknown.status == "insufficient_data"  # unknowns never count as wins
    assert tracker.top_targets(k=3) == []  # nothing qualifies


def test_mastered_domain_is_not_a_target(tmp_path):
    store = seeded_store(tmp_path, {"search_files": [("verified_success", 12)]})
    tracker = LearningProgressTracker(store.db_path)
    assert tracker.top_targets(k=3) == []  # mastered: nothing to learn


def test_declining_domain_is_reported_not_targeted(tmp_path):
    store = seeded_store(tmp_path, {
        "restore_backup": [("verified_success", 5), ("verified_failure", 5)],
    })
    tracker = LearningProgressTracker(store.db_path)
    progress = tracker.progress_for("restore_backup")
    assert progress.status in ("declining", "weak")
    assert progress.progress < 0  # honest: getting worse, not learning


def test_missing_store_is_honest(tmp_path):
    tracker = LearningProgressTracker(str(tmp_path / "nope.db"))
    nothing = tracker.progress_for("anything")
    assert nothing.status == "no_data" and nothing.learning_value == 0.0
    assert tracker.report()["targets"] == []


def test_goal_generator_targets_learning_domains(tmp_path, monkeypatch):
    """Curiosity slots fill with practice goals for measured learning domains."""
    from app.cognition import learning_progress as lp
    store = seeded_store(tmp_path, {
        "browser_upload": [("verified_failure", 4), ("verified_success", 6)],
    })
    monkeypatch.setattr(lp.learning_progress_tracker, "outcomes_db", store.db_path)
    tracker = lp.LearningProgressTracker(store.db_path)
    targets = tracker.top_targets(k=2)
    assert targets and targets[0].action_type == "browser_upload"

    from app.cognition.autonomous_goal_generator import (
        AutonomousGoalGenerator, GoalSource,
    )
    generator = AutonomousGoalGenerator(str(tmp_path / "goals.db"))
    generated = generator.generate_goals_from_information_gain(thresholds={"exploration_budget": 2})
    competence_goals = [g for g in generated if g.source == GoalSource.COMPETENCE_IMPROVEMENT]
    assert competence_goals and any("browser_upload" in g.title for g in competence_goals)
    assert len(generated) <= 2  # owner exploration cap respected
