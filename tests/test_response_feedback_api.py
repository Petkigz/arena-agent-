"""Owner feedback is trace-linked, retry-safe, and separate from execution truth."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cognition.phase1_task_evaluations import Phase1TaskEvaluationStore
from app.cognition.trace import CognitiveTrace


@pytest.fixture
def feedback_environment(tmp_path, monkeypatch):
    from app.config import settings
    from app.cognition.runtime import CognitiveRuntime
    from app.main import router

    trace_db = tmp_path / "traces.db"
    monkeypatch.setattr(settings, "DB_PATH", trace_db)
    traces = []
    for name in ("first", "second"):
        trace = CognitiveTrace(
            user_input=f"Find {name}", session_id=f"chat-{name}",
            strategy_goal_type="search_intent", strategy_action_type="search_files",
            route_comparison={"selected_route": "act"},
        )
        trace.finalize(
            reply="No independent evidence", actions=[], latency=1,
            goal_verified=False, grounding_result={"status": "unknown", "supported": False},
        )
        traces.append(trace)
    store = Phase1TaskEvaluationStore(tmp_path / "evaluations.db", trace_db_path=trace_db)
    monkeypatch.setattr(
        CognitiveRuntime, "get_instance",
        classmethod(lambda cls: SimpleNamespace(phase1_task_evaluations=store)),
    )
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client, store, traces, trace_db


def test_usefulness_retry_returns_original_receipt_and_rejects_changed_content(feedback_environment):
    client, _, traces, trace_db = feedback_environment
    trace = traces[0]
    path = f"/cognition/traces/{trace.trace_id}/usefulness"
    payload = {"usefulness": "helpful", "submission_id": "web-rating-123", "note": "Useful despite uncertainty"}
    first = client.post(path, json=payload)
    retry = client.post(path, json=payload)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    conflict = client.post(path, json={**payload, "usefulness": "not_helpful"})
    assert conflict.status_code == 400
    assert "different content" in conflict.json()["detail"]
    other_trace = client.post(f"/cognition/traces/{traces[1].trace_id}/usefulness", json=payload)
    assert other_trace.status_code == 400
    assert len(client.get(path).json()["feedback"]) == 1
    # A helpful rating never rewrites UNKNOWN or goal verification.
    with sqlite3.connect(trace_db) as conn:
        row = conn.execute(
            "SELECT goal_verified, grounding_result_json FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()
    assert row[0] == 0
    assert '"status": "unknown"' in row[1]


def test_concurrent_usefulness_retries_do_not_inflate_evidence(feedback_environment):
    _, _, traces, _ = feedback_environment
    trace_id = traces[0].trace_id
    def record(_):
        return CognitiveTrace.record_usefulness_feedback(
            trace_id, usefulness="partially_helpful", retrieval_useful=False,
            submission_id="concurrent-rating-123",
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(record, range(8)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert len(CognitiveTrace.list_usefulness_feedback(trace_id)) == 1


def test_task_evaluation_retry_is_measurement_only_and_fills_trace_context(feedback_environment):
    client, store, traces, trace_db = feedback_environment
    payload = {
        "task_key": "find-previously-unseen-report",
        "trace_id": traces[0].trace_id,
        "observed_outcome": "success", "usefulness": "helpful",
        "condition": "baseline", "split": "held_out",
        "evidence_ids": ["owner:checked-report"],
        "submission_id": "web-evaluation-123",
    }
    path = "/benchmarks/phase1/tasks/evaluations"
    first = client.post(path, json=payload)
    retry = client.post(path, json=payload)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    receipt = first.json()["evaluation"]
    assert receipt["strategy_goal_type"] == "search_intent"
    assert receipt["strategy_action_type"] == "search_files"
    assert receipt["route"] == "act"
    assert client.post(path, json={**payload, "observed_outcome": "failure"}).status_code == 400
    # Reopening the store must still return the same idempotency receipt.
    reopened = Phase1TaskEvaluationStore(store.db_path, trace_db_path=trace_db)
    assert reopened.record(**payload).to_dict() == receipt
    assert store.report()["evaluation_count"] == 1
    assert CognitiveTrace.list_usefulness_feedback(traces[0].trace_id) == []
    with sqlite3.connect(trace_db) as conn:
        assert conn.execute("SELECT SUM(goal_verified) FROM cognitive_traces").fetchone()[0] == 0


def test_concurrent_task_evaluation_retries_return_one_receipt(feedback_environment):
    _, store, traces, _ = feedback_environment
    def record(_):
        return store.record(
            task_key="owner-task", trace_id=traces[0].trace_id,
            observed_outcome="unknown", submission_id="concurrent-evaluation-123",
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(record, range(8)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert len(store.history()) == 1


def test_response_evaluation_history_filters_by_exact_trace_and_split(feedback_environment):
    client, store, traces, _ = feedback_environment
    for trace, split in ((traces[0], "held_out"), (traces[0], "contract"), (traces[1], "held_out")):
        store.record(task_key="owner-task", trace_id=trace.trace_id, observed_outcome="unknown", split=split)
    path = "/benchmarks/phase1/tasks/evaluations"
    result = client.get(path, params={"trace_id": traces[0].trace_id, "split": "held_out"})
    assert result.status_code == 200
    assert result.json()["report"]["evaluation_count"] == 1
    assert result.json()["evaluations"][0]["trace_id"] == traces[0].trace_id
    assert client.get(path, params={"split": "other"}).status_code == 400
    assert client.get(path, params={"trace_id": "absent"}).json()["evaluations"] == []


def test_feedback_endpoints_reject_absent_trace_and_invalid_submission_id(feedback_environment):
    client, _, traces, _ = feedback_environment
    path = "/cognition/traces/absent/usefulness"
    assert client.post(path, json={"usefulness": "helpful"}).status_code == 404
    assert client.post("/benchmarks/phase1/tasks/evaluations", json={
        "task_key": "owner-task", "trace_id": "absent", "observed_outcome": "success",
    }).status_code == 404
    assert client.post(f"/cognition/traces/{traces[0].trace_id}/usefulness", json={
        "usefulness": "helpful", "submission_id": "invalid/identifier",
    }).status_code == 422
    with pytest.raises(ValueError, match="submission_id"):
        CognitiveTrace.record_usefulness_feedback(traces[0].trace_id, usefulness="helpful", submission_id="short")
