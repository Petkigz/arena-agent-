"""Learned action→outcome statistics: predictions improve with verified history.

Empirical success rates (Wilson intervals + Laplace smoothing) from recorded
execution evidence replace the hardcoded 0.85 prediction confidence once
evidence suffices. Thin evidence keeps the labeled prior. The uncertainty gate
(F1.2) compounds: a history of failures drops learned confidence below the
asking threshold and the agent asks instead of acting.
"""
from app.cognition.action_outcomes import (
    ActionOutcomeStore,
    classify_outcome,
    learned_confidence,
)
from app.cognition.prediction_engine import PredictionEngine


def make_store(tmp_path):
    return ActionOutcomeStore(tmp_path / "ao.db")


def test_outcome_classification_is_honest():
    assert classify_outcome({"goal_verified": True}) == "verified_success"
    assert classify_outcome({"verification_unknown": True}) == "verification_unknown"
    assert classify_outcome({"goal_verified": False}) == "verified_failure"
    assert classify_outcome({"success": True}) == "unverified_success"
    assert classify_outcome({"success": False}) == "verified_failure"
    assert classify_outcome({"irrelevant": 1}) is None
    assert classify_outcome(None) is None


def test_thin_evidence_keeps_the_labeled_prior(tmp_path):
    store = make_store(tmp_path)
    estimate = store.estimate("browser_upload")
    assert estimate.n == 0 and estimate.evidence_sufficient is False
    assert "insufficient" in estimate.confidence_source
    assert learned_confidence("browser_upload") is None  # no pretense of knowledge
    assert PredictionEngine().predict_action("browser_upload", {}).confidence_source == "default"


def test_estimate_tracks_observed_rate_with_smoothing(tmp_path):
    store = make_store(tmp_path)
    for i in range(8):
        store.record("move_file", {"src": i}, "verified_success", execution_id=f"e_ok_{i}")
    for i in range(2):
        store.record("move_file", {"src": i}, "verified_failure", execution_id=f"e_bad_{i}")
    estimate = store.estimate("move_file", refresh=True)
    assert estimate.n == 10 and estimate.evidence_sufficient is True
    assert estimate.raw_success_rate == 0.8
    # Smoothed toward the global rate (0.8 here) with prior strength 5:
    assert abs(estimate.smoothed_success_rate - 0.8) < 1e-6
    assert 0.0 < estimate.wilson_low < 0.8 < estimate.wilson_high < 1.0


def test_verification_unknown_shrinks_evidence_without_counting_as_success(tmp_path):
    store = make_store(tmp_path)
    for i in range(5):
        store.record("browser_upload", {}, "verification_unknown", execution_id=f"u_{i}")
    estimate = store.estimate("browser_upload", refresh=True)
    assert estimate.n == 5 and estimate.verification_unknown == 5
    assert estimate.evidence_sufficient is False  # unknowns are not informative successes
    assert learned_confidence("browser_upload") is None


def test_duplicate_execution_evidence_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    assert store.record("move_file", {}, "verified_success", execution_id="e1")["recorded"] is True
    assert store.record("move_file", {}, "verified_failure", execution_id="e1")["recorded"] is False
    estimate = store.estimate("move_file", refresh=True)
    assert estimate.n == 1 and estimate.verified_successes == 1


def test_ingest_from_execution_registry(tmp_path):
    import json
    from app.cognition.execution_control import ExecutionControlRegistry

    registry = ExecutionControlRegistry(str(tmp_path / "exec.db"))
    ok = registry.begin("p1", "move_file")
    registry.complete(ok.execution_id, status="completed")
    registry.record_result(ok.execution_id, {"success": True, "goal_verified": True})
    bad = registry.begin("p2", "browser_upload")
    registry.complete(bad.execution_id, status="completed")
    registry.record_result(bad.execution_id, {"success": True, "verification_unknown": True})
    noise = registry.begin("p3", "weird_action")
    registry.complete(noise.execution_id, status="completed")
    registry.record_result(noise.execution_id, {"unclassifiable": "yes"})

    store = make_store(tmp_path)
    result = store.ingest_execution_registry(registry)
    assert result["imported"] == 2 and result["skipped"] == 1
    # Re-ingest is idempotent.
    again = store.ingest_execution_registry(registry)
    assert again["imported"] == 0

    move = store.estimate("move_file", refresh=True)
    assert move.n == 1 and move.verified_successes == 1
    upload = store.estimate("browser_upload", refresh=True)
    assert upload.n == 1 and upload.verification_unknown == 1


def test_prediction_confidence_learns_from_history(tmp_path, monkeypatch):
    import app.cognition.action_outcomes as ao_module
    store = make_store(tmp_path)
    monkeypatch.setattr(ao_module, "action_outcome_store", store)

    # Before evidence: default prior.
    engine = PredictionEngine()
    assert engine.predict_action("restore_backup_overwrite", {}).confidence == 0.85

    # A verified failure history: learned confidence drops well below default.
    for i in range(6):
        store.record("restore_backup_overwrite", {"backup_id": i}, "verified_failure",
                     execution_id=f"fail_{i}")
    prediction = engine.predict_action("restore_backup_overwrite", {})
    assert prediction.confidence_source == "learned"
    assert prediction.confidence < 0.3
    assert learned_confidence("restore_backup_overwrite") < 0.3


def test_uncertainty_gate_compounds_with_learned_history(tmp_path, monkeypatch):
    """F1.2 × F1.4: failure history converts an autonomous action into a question."""
    import app.cognition.action_outcomes as ao_module
    from app.cognition.action_proposal import ActionProposal, ActionGate
    from app.cognition.owner_control import OwnerControlPolicy, owner_control_store
    from app.cognition.uncertainty_questions import OwnerQuestionStore

    store = make_store(tmp_path)
    monkeypatch.setattr(ao_module, "action_outcome_store", store)
    questions = OwnerQuestionStore(tmp_path / "q.db")
    monkeypatch.setattr("app.cognition.uncertainty_questions.owner_question_store", questions)
    monkeypatch.setattr("app.config.settings.ARENA_ASK_QUESTIONS_ENABLED", "1", raising=False)
    monkeypatch.setattr(owner_control_store, "_policy", OwnerControlPolicy())

    # No history yet: the default 0.85 confidence passes the uncertainty gate.
    from app.cognition.action_proposal import ActionProposal as P
    gate = ActionGate.evaluate_proposal(P(action_type="search_files", payload={"query": "x"}))
    assert gate.gate_name != "uncertainty_gate"

    # Six verified failures later, the same action asks instead of acting.
    for i in range(6):
        store.record("search_files", {"query": i}, "verified_failure", execution_id=f"f_{i}")
    gate2 = ActionGate.evaluate_proposal(P(action_type="search_files", payload={"query": "x"}))
    assert gate2.gate_name == "uncertainty_gate"
    assert questions.list("pending")
