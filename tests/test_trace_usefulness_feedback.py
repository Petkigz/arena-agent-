"""Usefulness feedback remains separate from correctness and execution truth."""

import sqlite3

import pytest

from app.cognition.trace import CognitiveTrace


def test_usefulness_feedback_is_append_only_and_separate(tmp_path, monkeypatch):
    from app.config import settings

    db_path = tmp_path / "trace.db"
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    trace = CognitiveTrace(user_input="Find the project", session_id="session-1")
    trace.finalize(
        reply="I found a historical match.",
        actions=[],
        latency=1.0,
        goal_verified=False,
    )

    first = CognitiveTrace.record_usefulness_feedback(
        trace.trace_id,
        usefulness="partially_helpful",
        outcome_signal="clarification_requested",
        retrieval_useful=False,
        note="The historical result was relevant but stale.",
    )
    second = CognitiveTrace.record_usefulness_feedback(
        trace.trace_id,
        usefulness="helpful",
        outcome_signal="task_completed",
        retrieval_useful=True,
    )

    feedback = CognitiveTrace.list_usefulness_feedback(trace.trace_id)
    assert [item["feedback_id"] for item in feedback] == [
        first["feedback_id"],
        second["feedback_id"],
    ]
    assert feedback[0]["retrieval_useful"] is False
    assert feedback[1]["retrieval_useful"] is True
    assert feedback[0]["usefulness"] == "partially_helpful"

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(cognitive_traces)").fetchall()
        }
        assert "goal_verified" in columns
        assert "usefulness" not in columns
        raw_note = conn.execute(
            "SELECT note FROM cognitive_trace_usefulness WHERE feedback_id = ?",
            (first["feedback_id"],),
        ).fetchone()[0]
    assert raw_note == "The historical result was relevant but stale."


def test_usefulness_feedback_endpoint_round_trips_trace_link(tmp_path, monkeypatch):
    from app.config import settings
    from app.main import (
        TraceUsefulnessRequest,
        list_trace_usefulness_endpoint,
        record_trace_usefulness_endpoint,
    )

    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "trace.db")
    trace = CognitiveTrace(user_input="Endpoint query")
    trace.finalize(reply="Endpoint reply", actions=[], latency=1.0)
    result = record_trace_usefulness_endpoint(
        trace.trace_id,
        TraceUsefulnessRequest(
            usefulness="helpful",
            outcome_signal="task_completed",
            retrieval_useful=True,
        ),
    )
    assert result["success"] is True
    listed = list_trace_usefulness_endpoint(trace.trace_id)
    assert listed["feedback"][0]["trace_id"] == trace.trace_id
    assert listed["feedback"][0]["retrieval_useful"] is True


def test_usefulness_feedback_rejects_unknown_trace_and_invalid_labels(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "trace.db")
    with pytest.raises(KeyError):
        CognitiveTrace.record_usefulness_feedback(
            "missing-trace",
            usefulness="helpful",
        )

    trace = CognitiveTrace(user_input="A query")
    trace.finalize(reply="A reply", actions=[], latency=1.0)
    with pytest.raises(ValueError):
        CognitiveTrace.record_usefulness_feedback(
            trace.trace_id,
            usefulness="correct",
        )
