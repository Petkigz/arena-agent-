"""Trace persistence contracts for the epistemic presentation layer."""

import json
import sqlite3

from app.cognition.epistemic_presentation import presentation_for_cycle
from app.cognition.trace import CognitiveTrace


def test_trace_persists_user_facing_epistemic_presentation(tmp_path, monkeypatch):
    from app.config import settings

    db_path = tmp_path / "trace.db"
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    presentation = presentation_for_cycle(
        goal_verified=True,
        environment_observed=True,
        evidence_items=["fresh observation"],
    )
    trace = CognitiveTrace(user_input="Check the process", session_id="sess-test")
    trace.finalize(
        reply="The process is running.\n\n" + presentation.user_text(),
        actions=["probe_process"],
        latency=3.0,
        epistemic_presentation=presentation.to_dict(),
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT epistemic_presentation_json FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()

    assert row is not None
    persisted = json.loads(row[0])
    assert persisted["confidence_label"] == "Highly confident"
    assert persisted["evidence_basis"] == ["fresh observation"]
    assert trace.epistemic_presentation["evidence_state"] == "verified"
