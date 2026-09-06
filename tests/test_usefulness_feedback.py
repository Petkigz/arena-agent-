"""Usefulness feedback is trace-linked and separate from correctness."""

import sqlite3

import pytest

from app.cognition.usefulness_feedback import UsefulnessFeedbackStore


def _trace_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE cognitive_traces (
            trace_id TEXT PRIMARY KEY,
            latency_ms REAL NOT NULL,
            epistemic_presentation_json TEXT NOT NULL DEFAULT '{}'
        )""")
        conn.execute(
            "INSERT INTO cognitive_traces VALUES (?, ?, ?)",
            (
                "trace-1", 42.5,
                '{"confidence_label":"Moderately confident",'
                '"evidence_state":"inferred","confidence_score":0.6}',
            ),
        )
        conn.commit()


def test_feedback_captures_trace_context_and_explicit_rating(tmp_path):
    db_path = tmp_path / "feedback.db"
    _trace_db(db_path)
    store = UsefulnessFeedbackStore(db_path)

    feedback = store.record_rating(
        trace_id="trace-1",
        rating=4,
        note="Useful, but I needed one clarification.",
    )

    assert feedback.value == 0.75
    assert feedback.confidence_label == "Moderately confident"
    assert feedback.evidence_state == "inferred"
    assert feedback.latency_ms == 42.5
    assert store.summary()["overall"]["samples"] == 1


def test_summary_keeps_usefulness_separate_from_correctness(tmp_path):
    db_path = tmp_path / "feedback.db"
    _trace_db(db_path)
    store = UsefulnessFeedbackStore(db_path)
    store.record(
        trace_id="trace-1",
        signal_type="clarification_requested",
        value=0.25,
        source="owner_interaction",
    )
    store.record(
        trace_id="trace-1",
        signal_type="task_completed",
        value=1.0,
        source="owner_interaction",
    )

    summary = store.summary()
    assert summary["samples"] == 2
    assert summary["by_confidence_label"]["Moderately confident"]["samples"] == 2
    assert "correctness" in summary["note"]


def test_feedback_requires_existing_trace_and_valid_signal(tmp_path):
    db_path = tmp_path / "feedback.db"
    _trace_db(db_path)
    store = UsefulnessFeedbackStore(db_path)

    with pytest.raises(KeyError, match="Trace not found"):
        store.record(trace_id="missing", signal_type="task_completed", value=1.0)
    with pytest.raises(ValueError, match="Unknown usefulness signal_type"):
        store.record(trace_id="trace-1", signal_type="correct", value=1.0)
    with pytest.raises(ValueError, match="integer from 1 to 5"):
        store.record_rating(trace_id="trace-1", rating=6)
