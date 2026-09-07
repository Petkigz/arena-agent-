"""Owner-recorded held-out task evaluation contracts."""

import pytest

from app.cognition.phase1_task_evaluations import Phase1TaskEvaluationStore
from app.cognition.trace import CognitiveTrace


def _make_trace(db_path, name):
    from app.config import settings

    settings.DB_PATH = db_path
    trace = CognitiveTrace(user_input=name, session_id=name)
    trace.finalize(reply="Recorded response", actions=[], latency=1.0, goal_verified=False)
    return trace


def test_task_evaluations_require_trace_and_compare_paired_conditions(tmp_path, monkeypatch):
    from app.config import settings

    trace_db = tmp_path / "traces.db"
    monkeypatch.setattr(settings, "DB_PATH", trace_db)
    baseline_trace = _make_trace(trace_db, "baseline")
    adapted_trace = _make_trace(trace_db, "adapted")
    store = Phase1TaskEvaluationStore(
        tmp_path / "evaluations.db",
        trace_db_path=trace_db,
    )

    baseline = store.record(
        task_key="find-report",
        trace_id=baseline_trace.trace_id,
        observed_outcome="failure",
        usefulness="not_helpful",
        condition="baseline",
        strategy_goal_type="search_intent",
        strategy_action_type="search_files",
        evidence_ids=["owner:held-out-1"],
    )
    adapted = store.record(
        task_key="find-report",
        trace_id=adapted_trace.trace_id,
        observed_outcome="success",
        usefulness="helpful",
        condition="adapted",
        correction_received=True,
        strategy_goal_type="search_intent",
        strategy_action_type="web_search",
        evidence_ids=["owner:held-out-1"],
    )
    single = store.record(
        task_key="unknown-task",
        trace_id=adapted_trace.trace_id,
        observed_outcome="unknown",
        condition="single",
    )

    report = store.report()

    assert baseline.trace_id == baseline_trace.trace_id
    assert adapted.correction_received is True
    assert single.observed_outcome == "unknown"
    assert report["status"] == "measured"
    assert report["evaluation_count"] == 3
    assert report["outcome_counts"] == {"failure": 1, "success": 1, "unknown": 1}
    assert report["outcome_success_rate"] == 0.5
    assert report["usefulness_counts"] == {"helpful": 1, "not_helpful": 1}
    assert report["usefulness_rate"] == 0.5
    assert report["correction_received_count"] == 1
    assert report["paired_comparison_count"] == 1
    assert report["paired_improved_count"] == 1
    assert report["paired_regressed_count"] == 0
    assert report["strategies"]["search_intent|search_files"]["success_rate"] == 0.0
    assert report["strategies"]["search_intent|web_search"]["success_rate"] == 1.0
    assert "causality" in report["note"]

    with pytest.raises(KeyError):
        store.record(
            task_key="missing-trace-task",
            trace_id="missing-trace",
            observed_outcome="success",
        )


def test_task_evaluations_reject_invalid_labels(tmp_path):
    store = Phase1TaskEvaluationStore(tmp_path / "evaluations.db", trace_db_path=tmp_path / "traces.db")

    with pytest.raises(ValueError, match="observed_outcome"):
        store.record(
            task_key="invalid-outcome",
            trace_id="trace",
            observed_outcome="maybe",
        )


def test_task_evaluation_endpoints_round_trip_owner_observation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.config import settings
    from app.cognition.runtime import CognitiveRuntime
    from app.main import (
        Phase1TaskEvaluationRequest,
        phase1_task_evaluations_endpoint,
        record_phase1_task_evaluation_endpoint,
    )

    trace_db = tmp_path / "traces.db"
    monkeypatch.setattr(settings, "DB_PATH", trace_db)
    trace = _make_trace(trace_db, "endpoint-task")
    store = Phase1TaskEvaluationStore(
        tmp_path / "evaluations.db",
        trace_db_path=trace_db,
    )
    runtime = SimpleNamespace(phase1_task_evaluations=store)
    monkeypatch.setattr(
        CognitiveRuntime,
        "get_instance",
        classmethod(lambda cls: runtime),
    )

    created = record_phase1_task_evaluation_endpoint(Phase1TaskEvaluationRequest(
        task_key="endpoint-task",
        trace_id=trace.trace_id,
        observed_outcome="success",
        usefulness="helpful",
        evidence_ids=["owner:test"],
    ))
    listed = phase1_task_evaluations_endpoint(limit=10, split="held_out")

    assert created["success"] is True
    assert created["evaluation"]["trace_id"] == trace.trace_id
    assert listed["success"] is True
    assert listed["report"]["known_outcome_count"] == 1
    assert listed["evaluations"][0]["usefulness"] == "helpful"


def test_one_trace_cannot_be_both_halves_of_an_improved_pair(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.DB_PATH", tmp_path / "traces.db")
    trace = _make_trace(tmp_path / "traces.db", "one response")
    store = Phase1TaskEvaluationStore(tmp_path / "eval.db", trace_db_path=tmp_path / "traces.db")
    for condition, outcome in [("baseline", "failure"), ("adapted", "success")]:
        store.record(task_key="same-response", trace_id=trace.trace_id, observed_outcome=outcome, condition=condition)
    report = store.report()
    assert report["paired_comparison_count"] == 0
    assert report["paired_improved_count"] == 0
    assert report["known_outcome_trace_count"] == 1
    assert report["evidence_sufficient"] is False


def test_unknown_outcomes_and_repeat_assessments_do_not_inflate_success_evidence(tmp_path, monkeypatch):
    path = tmp_path / "traces.db"
    monkeypatch.setattr("app.config.settings.DB_PATH", path)
    trace = _make_trace(path, "unobserved response")
    store = Phase1TaskEvaluationStore(tmp_path / "eval.db", trace_db_path=path)
    for _ in range(3):
        store.record(task_key="unobserved-task", trace_id=trace.trace_id, observed_outcome="unknown",
                     strategy_goal_type="search", strategy_action_type="search_files")
    report = store.report()
    assert len(store.history()) == 3
    assert report["recorded_evaluation_count"] == 3
    assert report["evaluation_count"] == 1
    assert report["evidence_sufficient"] is False
    assert report["strategies"]["search|search_files"]["success_rate"] is None
    latest = store.record(task_key="unobserved-task", trace_id=trace.trace_id, observed_outcome="success")
    assert store.history(limit=1)[0].evaluation_id == latest.evaluation_id
