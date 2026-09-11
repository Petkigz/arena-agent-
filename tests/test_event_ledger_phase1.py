"""Phase 1 — the typed Event ledger (owner go-ahead 2026-09-11).

One event id per request; typed one-way states; append-only receipts;
legacy backfill with empty park reasons labeled 'legacy_unspecified';
fail-open and kill-switched everywhere. The scenarios pinned here are
the owner's live-run requests: 'open it itunes on my pc' and the
ambiguous 'i wanted to search something' + substantive follow-up.
"""

import json

import pytest

from app.cognition import event_ledger as ledger


@pytest.fixture
def ledger_db(monkeypatch, tmp_path):
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "ledger.db"))
    database_module.db._init_db()
    # fresh per-test backfill latch (module-global, one-time-per-process)
    monkeypatch.setattr(ledger, "_backfill_done", False)
    with database_module.db._get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_traces (
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
    return database_module.db


def _park_trace(db, trace_id, text, state="waiting_for_evidence",
                verified=0, park_reason="", created="2026-09-11T10:00:00+00:00",
                session="desktop-chat"):
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO cognitive_traces (trace_id, session_id, user_input, "
            "assistant_reply, actions_json, model_used, latency_ms, "
            "created_at, goal_verified, goal_lifecycle_state, goal_park_reason) "
            "VALUES (?, ?, ?, '', '[]', 'fast', 1.0, ?, ?, ?, ?)",
            (trace_id, session, text, created, verified, state, park_reason))
        conn.commit()


def _result(state="", verified=True, trace_id="trace_x", guard="",
            reason=""):
    out = {
        "assistant_reply": "done",
        "goal_lifecycle_state": state,
        "goal_verified": verified,
        "trace_id": trace_id,
        "executed_actions": [{"action_type": "open_application"}],
    }
    if guard:
        out["announcement_guard"] = guard
    if reason:
        out["reason"] = reason
    return out


class TestEventLifecycle:
    def test_open_dispatch_verify_success(self, ledger_db):
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        assert eid and eid.startswith("evt_")
        assert ledger.get_event(eid)["state"] == ledger.STATE_NEW
        assert ledger.transition_event(
            eid, ledger.STATE_DISPATCHED, receipt={"kind": "dispatch"})
        assert ledger.mark_from_cycle_result(
            "desktop-chat", "open it itunes on my pc",
            _result(state="achieved", verified=True)) == eid
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_VERIFIED_SUCCESS
        assert ev["trace_id"] == "trace_x"
        assert ev["receipts"][-1]["kind"] == "cycle_result"
        assert ev["receipts"][-1]["verified"] is True

    def test_one_event_id_per_request(self, ledger_db):
        # retries / duplicate deliveries never mint a second identity
        e1 = ledger.open_event("desktop-chat", "open it itunes on my pc")
        e2 = ledger.open_event("desktop-chat", "open it itunes on my pc")
        e3 = ledger.open_event("desktop-chat", "Open  it   iTunes on my PC")
        assert e1 == e2 == e3

    def test_waiting_for_evidence_then_recheck_flips_the_original(self,
                                                                  ledger_db):
        eid = ledger.open_event("desktop-chat", "delete the old report file")
        ledger.mark_from_cycle_result(
            "desktop-chat", "delete the old report file",
            _result(state="waiting_for_evidence", verified=False))
        assert ledger.get_event(eid)["state"] == \
            ledger.STATE_OBSERVATION_PENDING
        # the re-check runs as a NEW cycle with the '(automatic re-check #N)'
        # prefix — it must flip the ORIGINAL request's event
        ledger.mark_from_cycle_result(
            "desktop-chat",
            "(automatic re-check #1) delete the old report file",
            _result(state="achieved", verified=True, trace_id="trace_y"))
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_VERIFIED_SUCCESS

    def test_runtime_crash_dict_abandons_with_a_receipt(self, ledger_db):
        # the cognitive_pipeline bridge's honest crash shape
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        ledger.mark_from_cycle_result(
            "desktop-chat", "open it itunes on my pc",
            _result(state="failed", verified=False, reason="runtime exception: X"))
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_ABANDONED
        assert "runtime exception" in ev["reason"]

    def test_honesty_guard_cycle_is_verified_failure_not_success(self,
                                                                 ledger_db):
        # round 8's fabricated-claim replacement: the request was NOT
        # fulfilled, so the event may never read as success
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        ledger.mark_from_cycle_result(
            "desktop-chat", "open it itunes on my pc",
            _result(state="", verified=True,
                    guard="fabricated_claim_replaced"))
        assert ledger.get_event(eid)["state"] == \
            ledger.STATE_VERIFIED_FAILURE

    def test_typed_transitions_are_one_way(self, ledger_db):
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        assert ledger.transition_event(eid, ledger.STATE_VERIFIED_SUCCESS)
        # terminal states refuse everything
        assert not ledger.transition_event(eid, ledger.STATE_NEW)
        assert not ledger.transition_event(eid, ledger.STATE_OBSERVATION_PENDING)
        # an unknown state name is refused outright
        assert not ledger.transition_event(eid, "banana")

    def test_deferred_stays_open(self, ledger_db):
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        ledger.mark_from_cycle_result(
            "desktop-chat", "open it itunes on my pc",
            _result(state="deferred", verified=False))
        assert ledger.get_event(eid)["state"] == \
            ledger.STATE_OBSERVATION_PENDING


class TestSupersessionAndExpiry:
    def test_ambiguous_event_superseded_by_followup(self, ledger_db):
        # her live pattern: ambiguous park, then a substantive follow-up
        _park_trace(ledger_db, "t1", "i wanted to search something")
        eid = ledger.open_event("desktop-chat", "i wanted to search something")
        from app.cognition.parked_goal_recheck import (
            supersede_ambiguous_parked_goals,
        )
        n = supersede_ambiguous_parked_goals(
            "desktop-chat", "the weather in kampala now")
        assert n == 1
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_SUPERSEDED
        assert any(r["kind"] == "superseded" for r in ev["receipts"])

    def test_expiry_sweep(self, ledger_db, monkeypatch):
        from datetime import datetime, timedelta, timezone
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        old = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
        with ledger_db._get_connection() as conn:
            conn.execute(
                "UPDATE cognitive_events SET created_at = ? WHERE event_id = ?",
                (old, eid))
            conn.commit()
        assert ledger.expire_stale_events() == 1
        assert ledger.get_event(eid)["state"] == ledger.STATE_EXPIRED


class TestLegacyBackfill:
    def test_backfill_labels_empty_park_reasons_and_is_idempotent(self,
                                                                  ledger_db):
        _park_trace(ledger_db, "t1", "old goal", state="achieved",
                    verified=1, park_reason="")
        _park_trace(ledger_db, "t2", "parked goal",
                    park_reason="observation_timeout")
        assert ledger._maybe_backfill_legacy() == 2
        # second run backfills nothing (trace_id linkage)
        assert ledger._maybe_backfill_legacy() == 0
        with ledger_db._get_connection() as conn:
            rows = conn.execute(
                "SELECT trace_id, state, reason, source FROM cognitive_events "
                "ORDER BY trace_id").fetchall()
        by_trace = {r[0]: r for r in rows}
        assert by_trace["t1"][1] == ledger.STATE_VERIFIED_SUCCESS
        assert by_trace["t1"][2] == "legacy_unspecified"  # empty -> labeled
        assert by_trace["t1"][3] == "legacy_backfill"
        assert by_trace["t2"][1] == ledger.STATE_OBSERVATION_PENDING
        assert by_trace["t2"][2] == "observation_timeout"
        # history itself was never rewritten
        with ledger_db._get_connection() as conn:
            assert conn.execute(
                "SELECT goal_park_reason FROM cognitive_traces "
                "WHERE trace_id='t1'").fetchone()[0] == ""

    def test_open_event_triggers_backfill_once(self, ledger_db):
        _park_trace(ledger_db, "t1", "old goal", state="achieved", verified=1)
        ledger.open_event("desktop-chat", "open it itunes on my pc")
        with ledger_db._get_connection() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM cognitive_events "
                "WHERE source='legacy_backfill'").fetchone()[0]
        assert n == 1


class TestBoundaries:
    def test_kill_switch_silences_everything(self, ledger_db, monkeypatch):
        monkeypatch.setenv("ARENA_EVENT_LEDGER", "0")
        assert ledger.open_event("desktop-chat", "open it itunes on my pc") is None
        assert ledger.get_event("evt_whatever") is None
        assert ledger.active_events("desktop-chat") == []
        assert ledger.supersede_active_ambiguous_events("c", "x" * 20) == 0

    def test_fail_open_on_broken_db(self, monkeypatch, tmp_path):
        import app.database as database_module
        monkeypatch.setattr(
            database_module.db, "db_path", str(tmp_path / "nope.db"))
        database_module.db._init_db()
        monkeypatch.setattr(ledger, "_backfill_done", True)
        # cognitive_traces missing entirely must not explode the ledger
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        assert eid  # events table is self-created
        assert ledger.mark_from_cycle_result(
            "desktop-chat", "open it itunes on my pc",
            _result(state="achieved")) == eid

    def test_receipts_are_append_only_and_bounded(self, ledger_db):
        eid = ledger.open_event("desktop-chat", "open it itunes on my pc")
        for i in range(60):
            ledger.attach_receipt(eid, "probe", f"detail {i}")
        ev = ledger.get_event(eid)
        assert len(ev["receipts"]) == 50  # bounded tail, none invented
        assert ev["receipts"][-1]["detail"] == "detail 59"

    def test_active_events_introspection(self, ledger_db):
        monkey = ledger.open_event("desktop-chat", "open it itunes on my pc")
        ledger.open_event("desktop-chat", "i wanted to search something")
        actives = ledger.active_events("desktop-chat")
        assert {a["event_id"] for a in actives} >= {monkey}
        assert all(a["state"] in ledger.ACTIVE_STATES for a in actives)

    def test_wiring_is_in_place(self):
        import inspect

        import backend.message_router as mr
        from app.cognition import runtime as cog_runtime
        from app.cognition import parked_goal_recheck as pgr

        assert "open_event(conversation_id, content)" in inspect.getsource(mr)
        assert "mark_from_cycle_result(session_id or \"default\", user_text" \
            in inspect.getsource(cog_runtime)
        assert "supersede_active_ambiguous_events(conversation_id, text)" \
            in inspect.getsource(pgr)
        from app.config import settings
        assert hasattr(settings, "ARENA_EVENT_LEDGER")
