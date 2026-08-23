"""Restart-safe commitments and trace-grounded introspection."""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.cognition.commitment_ledger import CommitmentLedger, GroundedIntrospection


def test_commitment_completion_requires_verification_evidence(tmp_path):
    ledger = CommitmentLedger(tmp_path / "commitments.db")
    active = ledger.upsert(
        "Create the report", source_type="explicit_owner", source_id="owner-1",
        evidence=["owner_api:owner-1"],
    )
    assert active.status == "active"

    with pytest.raises(ValueError):
        ledger.upsert(
            "Create the report", source_type="explicit_owner", source_id="owner-1",
            status="completed", evidence=[], completion_verified=False,
        )

    completed = ledger.upsert(
        "Create the report", source_type="explicit_owner", source_id="owner-1",
        status="completed", evidence=["artifact hash matched"], completion_verified=True,
    )
    assert completed.commitment_id == active.commitment_id
    assert completed.completion_verified is True


def test_commitments_survive_restart_and_blocked_has_reason(tmp_path):
    path = tmp_path / "commitments.db"
    first = CommitmentLedger(path)
    first.upsert(
        "Long project", source_type="project", source_id="project-1",
        status="blocked", evidence=["project:project-1"],
        blocked_reason="Waiting for owner approval",
    )

    restored = CommitmentLedger(path).get_by_source("project", "project-1")
    assert restored is not None
    assert restored.status == "blocked"
    assert restored.blocked_reason == "Waiting for owner approval"


def test_project_sync_refuses_status_only_completion(tmp_path):
    ledger = CommitmentLedger(tmp_path / "commitments.db")
    unverified_project = SimpleNamespace(
        project_id="p1", name="Project one",
        status=SimpleNamespace(value="completed"), milestones=[],
    )
    commitment = ledger.sync_project(unverified_project)
    assert commitment.status == "blocked"
    assert commitment.completion_verified is False

    reached = SimpleNamespace(milestone_id="m1", status="reached")
    verified_project = SimpleNamespace(
        project_id="p1", name="Project one",
        status=SimpleNamespace(value="completed"), milestones=[reached],
    )
    commitment = ledger.sync_project(verified_project)
    assert commitment.status == "completed"
    assert commitment.evidence == ["project:p1", "milestone:m1"]


def test_introspection_uses_trace_facts_not_hidden_reasoning(tmp_path):
    path = tmp_path / "traces.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE cognitive_traces (
            trace_id TEXT, session_id TEXT, user_input TEXT, assistant_reply TEXT,
            actions_json TEXT, model_used TEXT, latency_ms REAL, vram_pressure REAL,
            ram_pressure REAL, attention_focus TEXT, belief_confidence REAL,
            gate_decision TEXT, prediction_surprisal REAL, reflection_lesson TEXT,
            goal_verified INTEGER, created_at TEXT
        )""")
        conn.execute(
            "INSERT INTO cognitive_traces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "trace-1", "session-1", "Create note", "Done",
                json.dumps(["created note 4"]), "test-model", 12.0, 0.0, 10.0,
                "exact owner-authorized note", 0.8, "passed_all_gates", 0.1,
                "Use direct note API", 1, "2026-08-23T00:00:00+00:00",
            ),
        )

    report = GroundedIntrospection.explain_trace(path, "trace-1")
    assert report["success"] is True
    assert report["facts"]["goal_verified"] is True
    assert report["facts"]["actions"] == ["created note 4"]
    assert any("chain-of-thought" in item for item in report["unknowns"])
    assert "thought" not in " ".join(report["explanation"]).lower()
