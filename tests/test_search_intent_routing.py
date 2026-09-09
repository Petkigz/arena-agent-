"""Search-intent routing + parked-goal supersession (owner transcript
2026-09-09, increment approved with her 'go').

The live failures, reproduced from her transcript:

  1. 'the weather in kampala now' carries no control verb, so the tool
     matcher returned None and the turn degraded into a conversational
     deflection ('Have you tried searching...?') instead of running a
     real web search;
  2. the parked goal 'i wanted to search something' was rechecked by
     web-searching the literal word 'something' (Bing, 0 results) while
     her follow-up 'the weather in kampala now' carried the actual
     intent in its own trace — the stale vague goal kept being rechecked.

Fixes pinned here: obvious info queries route deterministically to
web_search with the utterance itself as the query (verbless, before the
control-verb gate), and a substantive follow-up in a conversation with an
AMBIGUOUS parked goal ('something'/'stuff'/'things') supersedes it. Both
have kill switches (ARENA_INFO_QUERY_SEARCH=0,
ARENA_PARKED_SUPERSESSION=0).
"""

import pytest

from app.cognition.tool_matcher import match_control_tool
from app.cognition.parked_goal_recheck import (
    collect_parked_goals,
    supersede_ambiguous_parked_goals,
)


# ── 1. Info queries route to a real web search ──────────────────────────────


class TestInfoQueryRouting:
    def test_weather_with_city_routes_to_the_weather_tool(self):
        # The exact live failure: no control verb, must not deflect to
        # chat. The manifest ships a dedicated `weather` tool that takes
        # a city (audit 2026-09-09) — a named city goes there, not to a
        # generic web search.
        m = match_control_tool("the weather in kampala now")
        assert m is not None
        assert m.action_type == "weather"
        assert m.payload.get("city") == "kampala"

    def test_forecast_for_city_extracts_the_city(self):
        m = match_control_tool("weather forecast for entebbe tomorrow")
        assert m is not None and m.action_type == "weather"
        assert m.payload.get("city") == "entebbe"

    def test_cityless_weather_falls_back_to_web_search(self):
        m = match_control_tool("any weather updates")
        assert m is not None and m.action_type == "web_search"
        assert "weather" in m.payload.get("query", "")

    def test_news_query_routes_with_filler_stripped(self):
        m = match_control_tool("what's the news today")
        assert m is not None and m.action_type == "web_search"
        assert "news" in m.payload.get("query", "")
        assert not m.payload["query"].startswith(("what", "the"))

    def test_exchange_rate_query_routes(self):
        m = match_control_tool("exchange rate usd to ugx")
        assert m is not None and m.action_type == "web_search"

    def test_control_verb_request_keeps_the_normal_path(self):
        # 'open the weather app' is a launch, never a web search.
        m = match_control_tool("open the weather app")
        assert m is None or m.action_type != "web_search"

    def test_file_operand_is_not_hijacked(self):
        # A filename containing 'weather' is file work, not a web lookup.
        m = match_control_tool("weather_report.pdf is missing from downloads")
        assert m is None or m.action_type != "web_search"

    def test_ordinary_chat_is_not_routed(self):
        assert match_control_tool("how are you doing today") is None
        assert match_control_tool("tell me about yourself") is None

    def test_existing_search_synonyms_still_route(self):
        # Regression: the verb path from the same transcript
        # ('search for me on twitter') must keep working.
        m = match_control_tool("search for me on twitter")
        assert m is not None and m.action_type == "web_search"
        assert "twitter" in (m.payload.get("query") or "")

    def test_kill_switch_disables_info_routing(self, monkeypatch):
        monkeypatch.setenv("ARENA_INFO_QUERY_SEARCH", "0")
        assert match_control_tool("the weather in kampala now") is None


# ── 2. A follow-up supersedes its ambiguous parked goal ────────────────────


@pytest.fixture
def supersede_db(monkeypatch, tmp_path):
    """Same reduced cognitive_traces shape the recheck-suite uses."""
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "supersede.db"))
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

    def _insert(trace_id, session_id, text, state="waiting_for_evidence",
                park_reason=None):
        with database_module.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO cognitive_traces (trace_id, session_id, "
                "user_input, assistant_reply, actions_json, model_used, "
                "latency_ms, created_at, goal_verified, goal_lifecycle_state, "
                "goal_park_reason)"
                " VALUES (?, ?, ?, '', '[]', 'fast', 1.0, "
                "'2026-09-09T13:00:00+00:00', 0, ?, ?)",
                (trace_id, session_id, text, state, park_reason),
            )
            conn.commit()

    _insert("t-ambiguous", "sess_a", "i wanted to search something")
    _insert("t-concrete", "sess_a", "find the file kaba and play it")
    _insert("t-other-conv", "sess_b", "i wanted to search something")
    return _insert


class TestParkedGoalSupersession:
    def test_follow_up_supersedes_only_the_ambiguous_goal(self, supersede_db):
        n = supersede_ambiguous_parked_goals(
            "sess_a", "the weather in kampala now")
        assert n == 1
        remaining = {g["trace_id"] for g in collect_parked_goals(limit=10)}
        assert "t-ambiguous" not in remaining   # left the recheck queue
        assert "t-concrete" in remaining        # concrete goals untouched

    def test_other_conversation_is_untouched(self, supersede_db):
        supersede_ambiguous_parked_goals("sess_a", "the weather in kampala now")
        remaining = {g["trace_id"] for g in collect_parked_goals(limit=10)}
        assert "t-other-conv" in remaining

    @pytest.mark.parametrize("text", [
        "hi",                       # greeting
        "yes",                      # too short
        "thanks!",                  # greeting
        "(automatic re-check #1) the weather in kampala now",  # a recheck
    ])
    def test_non_substantive_turns_never_supersede(self, supersede_db, text):
        assert supersede_ambiguous_parked_goals("sess_a", text) == 0
        remaining = {g["trace_id"] for g in collect_parked_goals(limit=10)}
        assert "t-ambiguous" in remaining

    def test_state_is_marked_superseded_not_achieved(self, supersede_db):
        import app.database as database_module

        supersede_ambiguous_parked_goals("sess_a", "the weather in kampala now")
        with database_module.db._get_connection() as conn:
            state, verified = conn.execute(
                "SELECT goal_lifecycle_state, goal_verified "
                "FROM cognitive_traces WHERE trace_id = 't-ambiguous'"
            ).fetchone()
        assert state == "superseded_by_followup"
        assert not verified  # honest: nothing was accomplished

    def test_kill_switch_disables_supersession(self, supersede_db, monkeypatch):
        monkeypatch.setenv("ARENA_PARKED_SUPERSESSION", "0")
        assert supersede_ambiguous_parked_goals(
            "sess_a", "the weather in kampala now") == 0
        remaining = {g["trace_id"] for g in collect_parked_goals(limit=10)}
        assert "t-ambiguous" in remaining


# ── 3. The router hook is wired ─────────────────────────────────────────────


def test_router_calls_supersession_for_owner_messages_only():
    """The seam in _handle_user_message: owner turns supersede, automatic
    rechecks never do (a recheck must not supersede its own goal)."""
    import inspect

    import backend.message_router as router_module

    src = inspect.getsource(router_module.MessageRouter._handle_user_message)
    assert "supersede_ambiguous_parked_goals" in src
    assert 'message_source != "auto_recheck"' in src
