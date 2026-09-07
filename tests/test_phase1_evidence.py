"""Phase 1 evidence aggregation reports observations without maturity claims."""

from types import SimpleNamespace

from app.cognition.phase1_evidence import Phase1EvidenceStore
from app.cognition.trace import CognitiveTrace


def _trace(db_path, *, index, verified, grounding, route=None, strategy="answer"):
    from app.config import settings

    settings.DB_PATH = db_path
    trace = CognitiveTrace(
        user_input=f"Phase 1 task {index}",
        session_id=f"phase1-{index}",
        strategy_goal_type="knowledge_query",
        strategy_action_type=strategy,
    )
    trace.route_comparison = dict(route or {})
    trace.finalize(
        reply=f"Reply {index}",
        actions=[],
        latency=1.0,
        goal_verified=verified,
        grounding_result=grounding,
    )
    return trace


def test_phase1_report_aggregates_grounding_outcomes_and_usefulness(tmp_path, monkeypatch):
    from app.config import settings

    db_path = tmp_path / "phase1.db"
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    first = _trace(
        db_path,
        index=1,
        verified=True,
        grounding={"status": "verified", "unsupported_claims": []},
        route={"correction_applied": False},
    )
    second = _trace(
        db_path,
        index=2,
        verified=False,
        grounding={"status": "unknown", "unsupported_claims": ["unsupported claim"]},
        route={"correction_applied": True, "correction_outcome": "verified_failure"},
    )
    third = _trace(
        db_path,
        index=3,
        verified=True,
        grounding={"status": "supported", "unsupported_claims": []},
        route={"correction_applied": True, "correction_outcome": "verified_success"},
    )

    CognitiveTrace.record_usefulness_feedback(
        first.trace_id,
        usefulness="helpful",
        outcome_signal="task_completed",
    )
    CognitiveTrace.record_usefulness_feedback(
        second.trace_id,
        usefulness="not_helpful",
        outcome_signal="correction_followup",
    )
    CognitiveTrace.record_usefulness_feedback(
        third.trace_id,
        usefulness="partially_helpful",
        outcome_signal="clarification_requested",
        retrieval_useful=True,
    )

    report = Phase1EvidenceStore(db_path).report()

    assert report["status"] == "measured"
    assert report["evidence_sufficient"] is True
    assert report["trace_count"] == 3
    assert report["verified_outcome_count"] == 2
    assert report["verified_outcome_rate"] == round(2 / 3, 4)
    assert report["grounding_status_counts"] == {
        "supported": 1,
        "unknown": 1,
        "verified": 1,
    }
    assert report["unsupported_claim_count"] == 1
    assert report["unsupported_claim_trace_rate"] == round(1 / 3, 4)
    assert report["correction_applied_count"] == 2
    assert report["correction_outcome_counts"] == {
        "verified_failure": 1,
        "verified_success": 1,
    }
    assert report["usefulness_feedback_count"] == 3
    assert report["usefulness_counts"] == {
        "helpful": 1,
        "partially_helpful": 1,
        "not_helpful": 1,
    }
    assert report["usefulness_rate"] == round(1.5 / 3, 4)
    assert report["retrieval_feedback_count"] == 1
    assert report["retrieval_useful_count"] == 1
    assert report["strategies"]["knowledge_query|answer"]["attempts"] == 3
    assert "causality" in report["note"]


def test_phase1_report_admits_missing_trace_evidence(tmp_path):
    report = Phase1EvidenceStore(tmp_path / "missing.db").report()

    assert report["status"] == "insufficient_evidence"
    assert report["evidence_sufficient"] is False
    assert report["usefulness_rate"] is None
    assert "unmeasured" in report["note"]


def test_phase1_evidence_endpoint_exposes_report(tmp_path, monkeypatch):
    from app.cognition.runtime import CognitiveRuntime
    from app.main import phase1_evidence_endpoint

    store = Phase1EvidenceStore(tmp_path / "phase1.db")
    runtime = SimpleNamespace(phase1_evidence=store)
    monkeypatch.setattr(
        CognitiveRuntime,
        "get_instance",
        classmethod(lambda cls: runtime),
    )

    result = phase1_evidence_endpoint(limit=10)

    assert result["success"] is True
    assert result["report"]["status"] == "insufficient_evidence"
