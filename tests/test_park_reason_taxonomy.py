"""Typed park reasons for parked goals (owner-pasted architecture audit
2026-09-09).

The live defect: 'waiting_for_evidence' had become a GENERIC failure
bucket — an unresolvable app name ('open RichST TV'), an underspecified
intent ('i wanted to search something'), a missing capability, a pending
approval, and a dead model provider all parked under the same state, and
the auto-recheck replayed the full chat cycle for cases re-running can
never fix ('Have you tried Task Manager?' on loop).

Pinned here: parked goals carry a typed reason; ONLY observation-pending
goals (and legacy rows predating the taxonomy) are eligible for evidence
rechecks; the owner-visible status line names the reason and says
whether an auto-recheck could ever help. The lifecycle state itself is
unchanged — the reason is an added column, so every existing reader of
'waiting_for_evidence' keeps working.
"""

import pytest

from app.cognition.goal_lifecycle import (
    PARK_AUTHORIZATION_REQUIRED,
    PARK_CAPABILITY_UNAVAILABLE,
    PARK_NEEDS_CLARIFICATION,
    PARK_OBSERVATION_PENDING,
    PARK_PROVIDER_UNAVAILABLE,
    PARK_REASONS,
    PARK_TARGET_AMBIGUOUS,
    RECHECK_ELIGIBLE_PARK_REASONS,
    classify_park_reason,
    park_status_line,
)
from app.cognition.parked_goal_recheck import collect_parked_goals


class TestParkReasonClassifier:
    def test_simulated_reply_is_provider_unavailable(self):
        # Her 2:13 PM transcript: '[Simulated Response - Local LLM Server
        # Offline]' parked like any other goal and fed the recheck loop.
        result = {"assistant_reply":
                  "[Simulated Response - Local LLM Server Offline]\n\n..."}
        assert classify_park_reason(result) == PARK_PROVIDER_UNAVAILABLE
        assert classify_park_reason({"simulated": True}) == PARK_PROVIDER_UNAVAILABLE

    def test_approval_request_is_authorization_required(self):
        result = {"approval_request": {"id": "ap_1", "action": "open_application"}}
        assert classify_park_reason(result) == PARK_AUTHORIZATION_REQUIRED

    def test_unresolved_capability_is_capability_unavailable(self):
        # The live 'kaba' log: "Capability phrase unresolved ...
        # 'play media file capability'".
        result = {"capability_status": {
            "file search capability": {"status": "ready"},
            "play media file capability": {"status": "unresolved"},
        }}
        assert classify_park_reason(result) == PARK_CAPABILITY_UNAVAILABLE
        # The text marker path (reply/reason wording) classifies too.
        text = {"reason": "Capability phrase unresolved: play media file capability"}
        assert classify_park_reason(text) == PARK_CAPABILITY_UNAVAILABLE

    def test_ambiguity_is_target_ambiguous(self):
        result = {"reason": "3 matching applications found — target ambiguous"}
        assert classify_park_reason(result) == PARK_TARGET_AMBIGUOUS

    def test_pending_question_is_needs_clarification(self):
        result = {"question_asked": {"id": "q_1", "text": "which folder?"}}
        assert classify_park_reason(result) == PARK_NEEDS_CLARIFICATION

    def test_default_is_observation_pending(self):
        # An action happened (or was attempted) and its outcome awaits
        # observation — the honest legacy meaning stays the default.
        assert classify_park_reason(
            {"executed_actions": ["open_application"]}) == PARK_OBSERVATION_PENDING
        assert classify_park_reason({}) == PARK_OBSERVATION_PENDING

    def test_every_reason_has_a_status_line(self):
        for reason in PARK_REASONS:
            line = park_status_line(reason)
            assert reason in line
            assert "will not auto-recheck" in line or "re-check" in line

    def test_only_observation_pending_and_legacy_are_recheck_eligible(self):
        assert RECHECK_ELIGIBLE_PARK_REASONS == {PARK_OBSERVATION_PENDING, ""}
        assert PARK_NEEDS_CLARIFICATION not in RECHECK_ELIGIBLE_PARK_REASONS


# ── Recheck eligibility against the store ───────────────────────────────────


@pytest.fixture
def parked_db(monkeypatch, tmp_path):
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "parked.db"))
    database_module.db._init_db()
    with database_module.db._get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE cognitive_traces (
                trace_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_input TEXT NOT NULL,
                assistant_reply TEXT NOT NULL DEFAULT '',
                actions_json TEXT NOT NULL DEFAULT '[]',
                model_used TEXT NOT NULL DEFAULT 'fast',
                latency_ms REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                goal_verified INTEGER,
                goal_lifecycle_state TEXT,
                goal_park_reason TEXT
            )
            """
        )
        conn.commit()

    def _insert(trace_id, text, park_reason, when="13:00:00"):
        with database_module.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO cognitive_traces (trace_id, session_id, "
                "user_input, assistant_reply, actions_json, model_used, "
                "latency_ms, created_at, goal_verified, goal_lifecycle_state, "
                "goal_park_reason) VALUES (?, 'sess_a', ?, '', '[]', 'fast', "
                "1.0, ?, 0, 'waiting_for_evidence', ?)",
                (trace_id, text, f"2026-09-09T{when}+00:00", park_reason),
            )
            conn.commit()

    return _insert


class TestRecheckEligibility:
    def test_typed_non_evidence_reasons_are_not_rechecked(self, parked_db):
        parked_db("t-provider", "hey open richst tv", PARK_PROVIDER_UNAVAILABLE,
                  "13:00:01")
        parked_db("t-clarify", "i wanted to search something",
                  PARK_NEEDS_CLARIFICATION, "13:00:02")
        parked_db("t-observe", "find the file kaba and play it",
                  PARK_OBSERVATION_PENDING, "13:00:03")
        collected = {g["trace_id"] for g in collect_parked_goals(limit=10)}
        assert collected == {"t-observe"}

    def test_legacy_rows_keep_the_historical_behavior(self, parked_db):
        # Rows predating the taxonomy (NULL reason) stay recheck-eligible:
        # bounded by the 3-attempt limit and follow-up supersession.
        parked_db("t-legacy", "find the file kaba and play it", None)
        collected = {g["trace_id"] for g in collect_parked_goals(limit=10)}
        assert collected == {"t-legacy"}


# ── Trace persistence roundtrip ─────────────────────────────────────────────


def test_trace_persists_the_park_reason(monkeypatch, tmp_path):
    import sqlite3

    from app.cognition.trace import CognitiveTrace

    db_file = tmp_path / "trace.db"
    # The trace store persists through settings.DB_PATH (its own
    # sqlite3.connect), not the db singleton.
    monkeypatch.setattr("app.config.settings.DB_PATH", db_file)

    trace = CognitiveTrace(user_input="open richst tv")
    trace.finalize(
        reply="[Simulated Response - Local LLM Server Offline]",
        actions=[],
        latency=10.0,
        goal_verified=False,
        goal_lifecycle_state="waiting_for_evidence",
        goal_park_reason=PARK_PROVIDER_UNAVAILABLE,
    )
    conn = sqlite3.connect(db_file)
    try:
        row = conn.execute(
            "SELECT goal_lifecycle_state, goal_park_reason "
            "FROM cognitive_traces WHERE trace_id = ?",
            (trace.trace_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "waiting_for_evidence"   # state unchanged for old readers
    assert row[1] == PARK_PROVIDER_UNAVAILABLE  # … plus the typed reason
