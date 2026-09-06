import sqlite3

import pytest

from app.cognition.phase7_preferences import (
    Phase7AssessmentStore,
    Phase7PreferenceEngine,
    Phase7PreferenceError,
)


def test_curiosity_separates_signals_and_never_grants_authority(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    result = engine.assess_curiosity(
        information_needs=[{"question": "Which source is current?", "target": "source", "priority": 0.9}],
        learning_targets=[{"action_type": "search", "learning_value": 0.8, "status": "improving"}],
        anomalies=[{"target": "result", "score": 0.7, "evidence_ids": ["e:anomaly"]}],
        owner_approved_exploration=False,
        trace_id="trace-curiosity",
        evidence_ids=["e:unknown", "e:progress"],
    )
    assert result.information_gain == pytest.approx(0.9)
    assert result.learning_progress == pytest.approx(0.8)
    assert result.owner_approved_exploration == 0.0
    assert result.activity_cap == 1
    assert result.advisory_only is True
    assert result.authority == "none"
    assert result.recommended_targets[0]["category"] == "information_gain"


def test_curiosity_does_not_promote_anomaly_without_evidence(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    result = engine.assess_curiosity(
        anomalies=[{"target": "unsupported", "score": 1.0}],
        trace_id="trace-anomaly",
        evidence_ids=["e:input"],
    )
    assert result.anomaly_investigation == 0.0
    assert result.recommended_targets == []
    assert result.activity_cap == 0


def test_owner_approved_exploration_requires_explicit_authorization(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    with pytest.raises(Phase7PreferenceError, match="owner_authorization_id"):
        engine.assess_curiosity(
            information_needs=[{"question": "q", "priority": 0.5}],
            owner_approved_exploration=True,
            trace_id="trace-owner-missing",
            evidence_ids=["e:input"],
        )
    result = engine.assess_curiosity(
        information_needs=[{"question": "q", "priority": 0.5}],
        owner_approved_exploration=True,
        owner_authorization_id="owner-decision-1",
        trace_id="trace-owner-present",
        evidence_ids=["e:input"],
    )
    assert result.owner_approved_exploration == 1.0
    assert result.owner_authorization_id == "owner-decision-1"


def test_simplicity_breaks_only_comparable_utility_ties(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    result = engine.choose_solution(
        [
            {"solution_id": "complex", "utility": 0.90, "step_count": 18, "reversibility": 0.2},
            {"solution_id": "simple", "utility": 0.86, "step_count": 2, "reversibility": 0.9},
        ],
        trace_id="trace-taste",
        evidence_ids=["e:requirements", "e:constraints"],
    )
    assert result["selected_solution_id"] == "simple"
    assert result["simplicity_preference_applied"] is True
    assert result["selection_is_advisory"] is True
    assert result["authority"] == "none"

    utility_winner = engine.choose_solution(
        [
            {"solution_id": "high-utility", "utility": 0.95, "step_count": 20},
            {"solution_id": "simple-low-utility", "utility": 0.50, "step_count": 1},
        ],
        trace_id="trace-taste-2",
        evidence_ids=["e:requirements"],
    )
    assert utility_winner["selected_solution_id"] == "high-utility"
    assert utility_winner["simplicity_preference_applied"] is False


def test_novelty_compares_sources_and_flags_uncertainty_without_quality_claim(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    result = engine.detect_novelty(
        "combine a calendar constraint with a reversible local cache",
        retrieved_material=[{"content": "use a calendar constraint", "source_type": "retrieved", "evidence_id": "e:r1"}],
        baseline_strategies=[{"content": "use a remote database", "source_type": "baseline", "evidence_id": "e:b1"}],
        prior_outputs=[{"content": "write a local cache", "source_type": "prior", "evidence_id": "e:p1"}],
        trace_id="trace-novelty",
        evidence_ids=["e:r1", "e:b1", "e:p1"],
    )
    assert 0.0 <= result.novelty_score <= 1.0
    assert 0.0 <= result.uncertainty <= 1.0
    assert result.comparison_count == 3
    assert result.quality_not_inferred is True
    assert result.calibration_status == "calibrated_proxy"


def test_novelty_without_references_is_unknown_not_novel(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    result = engine.detect_novelty(
        "an output with no comparison set",
        trace_id="trace-novelty-unknown",
        evidence_ids=["e:output"],
    )
    assert result.novelty_score == 0.0
    assert result.novelty_flagged is False
    assert result.uncertainty == 1.0
    assert result.calibration_status == "insufficient_reference_evidence"


def test_phase7_assessments_persist_with_trace_and_evidence(tmp_path):
    path = tmp_path / "phase7.db"
    engine = Phase7PreferenceEngine(path)
    engine.assess_curiosity(
        information_needs=[{"question": "q", "priority": 0.5}],
        trace_id="trace-persist",
        evidence_ids=["e:persist"],
    )
    reopened = Phase7AssessmentStore(path)
    history = reopened.history()
    assert history[0]["trace_id"] == "trace-persist"
    assert history[0]["result_type"] == "generated_hypothesis"
    assert history[0]["evidence_ids"] == ["e:persist"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM phase7_assessments").fetchone()[0] == 1


def test_phase7_rejects_missing_trace_evidence_and_schema(tmp_path):
    engine = Phase7PreferenceEngine(tmp_path / "phase7.db")
    with pytest.raises(Phase7PreferenceError, match="trace_id"):
        engine.detect_novelty("text", trace_id="", evidence_ids=["e"])
    with pytest.raises(Phase7PreferenceError, match="evidence_ids"):
        engine.detect_novelty("text", trace_id="trace", evidence_ids=[])

    unsupported = tmp_path / "unsupported.db"
    with sqlite3.connect(unsupported) as conn:
        conn.execute(
            "CREATE TABLE phase7_meta (singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO phase7_meta VALUES (1, 99)")
    with pytest.raises(Phase7PreferenceError, match="unsupported phase 7"):
        Phase7AssessmentStore(unsupported)
