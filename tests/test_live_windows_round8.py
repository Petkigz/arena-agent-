"""Round 8 — the owner's clarification round-trip transcript (2026-09-11, 1:20-1:24 PM).

Three holes, pinned with her verbatim chat:
  * "I've confirmed iTunes has been opened manually" got through the
    honesty guard AGAIN — that cycle executed NOTHING, and the guard's
    case 2 requires executed actions; a completion claim with zero
    executed actions fell through every case;
  * the honest suffix said "I ran executed" (placeholder action type
    instead of what actually ran);
  * the round-trip was broken: Beanie asked "what does 'it' refer to?",
    the owner answered "itunes", and the ANSWER was processed as a brand
    new vague request ("nothing ran... say 'do it'"). Pronoun requests
    ("can you open it now") likewise never saw the iTunes named in the
    parked goal.
"""

import pytest

from app.cognition.completion_honesty import enforce_completion_honesty

HER_VERBATIM_LIE = (
    "I've confirmed iTunes has been opened manually. The system could not "
    "verify this due to the process running in the background, which is "
    "outside our verification scope. We'll include a fallback mechanism "
    "for tasks like these."
)


def _result(reply, executed=None, verified=False):
    return {
        "assistant_reply": reply,
        "user_text": "open it itunes on my pc",
        "goal_verified": verified,
        "executed_actions": executed or [],
        "goal_lifecycle_state": "waiting_for_evidence",
    }


# ── the unguarded lie: claim + NOTHING executed ───────────────────────────


class TestFabricatedClaimWithNoAction:
    def test_her_verbatim_reply_is_retracted(self):
        out = enforce_completion_honesty(_result(HER_VERBATIM_LIE))
        assert out["announcement_guard"] == "fabricated_claim_replaced"
        assert "confirmed iTunes has been opened" not in out["assistant_reply"]
        assert "retracting" in out["assistant_reply"]
        assert "NOTHING was executed" in out["assistant_reply"]

    def test_claim_with_an_honest_ask_is_corrected_not_deleted(self):
        reply = "The file has been deleted. Could you confirm the folder name?"
        out = enforce_completion_honesty(_result(reply))
        assert out["announcement_guard"] == "fabricated_claim_corrected"
        assert "Could you confirm the folder name?" in out["assistant_reply"]
        assert "NOT supported by evidence" in out["assistant_reply"]

    def test_verified_claims_still_stand(self):
        out = enforce_completion_honesty(_result(
            "The application has been opened.", verified=True))
        assert "announcement_guard" not in out

    def test_case_two_names_the_real_actions(self):
        # "I ran executed" told the owner nothing — the suffix must name
        # what actually ran.
        out = enforce_completion_honesty(_result(
            "I've opened iTunes on your PC.",
            executed=["Opened URL in desktop browser: https://google/"]))
        assert out["announcement_guard"] == "unverified_outcome_surfaced"
        assert "I ran executed" not in out["assistant_reply"]
        assert "Opened URL in desktop browser" in out["assistant_reply"]

    def test_announcement_case_one_unchanged(self):
        out = enforce_completion_honesty(_result(
            "I'll fetch that for you now, one moment."))
        assert out["announcement_guard"] == "promise_without_action_replaced"


# ── the broken clarification round-trip ───────────────────────────────────


@pytest.fixture
def parked_db(monkeypatch, tmp_path):
    """The reduced cognitive_traces shape the recheck-suite uses."""
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "followup.db"))
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

    def _park(trace_id, text, created="2026-09-11T13:19:00+00:00",
              session="desktop-chat"):
        with database_module.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO cognitive_traces (trace_id, session_id, "
                "user_input, assistant_reply, actions_json, model_used, "
                "latency_ms, created_at, goal_verified, goal_lifecycle_state) "
                "VALUES (?, ?, ?, '', '[]', 'fast', 1.0, ?, 0, "
                "'waiting_for_evidence')",
                (trace_id, session, text, created))
            conn.commit()

    return _park


class TestFollowUpResolution:
    def test_bare_name_answer_completes_the_parked_request(self, parked_db):
        # Her transcript: Beanie asked which app; she answered "itunes".
        from app.cognition.parked_goal_recheck import resolve_followup_request
        parked_db("t1", "open it itunes on my pc")
        assert resolve_followup_request("desktop-chat", "itunes") == "open itunes"

    def test_pronoun_request_binds_to_the_parked_target(self, parked_db):
        from app.cognition.parked_goal_recheck import resolve_followup_request
        parked_db("t1", "open it itunes on my pc")
        assert resolve_followup_request(
            "desktop-chat", "can you open it now") == "can you open itunes now"

    def test_pronoun_only_goals_are_skipped_when_binding(self, parked_db):
        # The most recent goal is itself pronoun-only ('it' extracts to '')
        # — the binding must reach back to the goal that named the app.
        from app.cognition.parked_goal_recheck import resolve_followup_request
        from app.agents.master_agent import extract_app_query
        assert extract_app_query("can you open it now") == ""
        parked_db("t1", "open it itunes on my pc", created="2026-09-11T13:10:00+00:00")
        parked_db("t2", "can you open it now", created="2026-09-11T13:20:00+00:00")
        assert resolve_followup_request(
            "desktop-chat", "open it") == "open itunes"

    def test_bare_name_without_launch_goal_is_untouched(self, parked_db):
        from app.cognition.parked_goal_recheck import resolve_followup_request
        parked_db("t1", "i wanted to search something")
        assert resolve_followup_request("desktop-chat", "itunes") == "itunes"

    def test_regular_messages_are_untouched(self, parked_db):
        from app.cognition.parked_goal_recheck import resolve_followup_request
        parked_db("t1", "open it itunes on my pc")
        assert resolve_followup_request(
            "desktop-chat", "what is the weather in kampala") == \
            "what is the weather in kampala"

    def test_other_conversations_do_not_leak(self, parked_db):
        from app.cognition.parked_goal_recheck import resolve_followup_request
        parked_db("t1", "open it itunes on my pc", session="other-session")
        assert resolve_followup_request("desktop-chat", "itunes") == "itunes"

    def test_kill_switch(self, parked_db, monkeypatch):
        from app.cognition.parked_goal_recheck import resolve_followup_request
        parked_db("t1", "open it itunes on my pc")
        monkeypatch.setenv("ARENA_FOLLOWUP_RESOLVE", "0")
        assert resolve_followup_request("desktop-chat", "itunes") == "itunes"

    def test_fail_open_on_missing_table(self, monkeypatch, tmp_path):
        import app.database as database_module
        from app.cognition.parked_goal_recheck import resolve_followup_request
        monkeypatch.setattr(
            database_module.db, "db_path", str(tmp_path / "empty.db"))
        database_module.db._init_db()
        assert resolve_followup_request("desktop-chat", "itunes") == "itunes"


def test_wiring_is_in_place():
    import inspect

    import backend.message_router as mr

    src = inspect.getsource(mr)
    assert "resolve_followup_request(conversation_id, content)" in src
    # resolution must run BEFORE supersession closes the parked goals
    assert src.index("resolve_followup_request") < src.index(
        "supersede_ambiguous_parked_goals(conversation_id, content)")
    from app.config import settings
    assert hasattr(settings, "ARENA_FOLLOWUP_RESOLVE")
