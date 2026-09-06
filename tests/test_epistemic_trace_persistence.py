"""Trace persistence contracts for the epistemic presentation layer."""

import json
import sqlite3

from app.cognition.epistemic_presentation import presentation_for_cycle
from app.cognition.response_grounding import ResponseGrounding
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
    trace.retrieved_memories = [{
        "memory_id": "memory-1",
        "kind": "semantic",
        "source": "owner_note",
    }]
    trace.resource_allocation = {
        "complexity": "moderate",
        "model": "fast",
        "max_tokens": 500,
    }
    trace.criticality_review = {
        "severity": "moderate",
        "triggers": ["no_verified_action_history"],
        "required": True,
    }
    trace.route_comparison = {
        "agreement": False,
        "selected_route": "act",
    }
    trace.finalize(
        reply="The process is running.\n\n" + presentation.user_text(),
        actions=["probe_process"],
        latency=3.0,
        epistemic_presentation=presentation.to_dict(),
        grounding_result=ResponseGrounding(
            status="verified",
            supported=True,
            authoritative_facts=["fresh observation"],
        ).to_dict(),
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT epistemic_presentation_json, grounding_result_json, "
            "retrieved_memories_json, resource_allocation_json, "
            "criticality_review_json, route_comparison_json "
            "FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()

    assert row is not None
    persisted = json.loads(row[0])
    grounding = json.loads(row[1])
    retrieved = json.loads(row[2])
    allocation = json.loads(row[3])
    review = json.loads(row[4])
    route = json.loads(row[5])
    assert persisted["confidence_label"] == "Highly confident"
    assert persisted["evidence_basis"] == ["fresh observation"]
    assert grounding["status"] == "verified"
    assert grounding["authoritative_facts"] == ["fresh observation"]
    assert retrieved == [{"memory_id": "memory-1", "kind": "semantic", "source": "owner_note"}]
    assert allocation["complexity"] == "moderate"
    assert allocation["max_tokens"] == 500
    assert review["triggers"] == ["no_verified_action_history"]
    assert route["agreement"] is False
    assert trace.epistemic_presentation["evidence_state"] == "verified"
    assert trace.grounding_result["status"] == "verified"

    assert CognitiveTrace.update_persisted_reply(
        trace.trace_id, "The process is running.\n\nReminder due: check it again"
    ) is True
    with sqlite3.connect(db_path) as conn:
        reply = conn.execute(
            "SELECT assistant_reply FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()[0]
    assert "Reminder due: check it again" in reply
