"""Round 7 — the owner's second Windows smoke run (2026-09-11), pinned.

Her typo run "open it itunes on my pc" exposed three holes:
  * the planner DERAILED to web_search and googled the raw command
    sentence verbatim (browser opened search?q=open+it+itunes+on+my+pc,
    then HTTP 429) while os.launch_app sat ready;
  * the reply claimed "I've confirmed iTunes has been opened manually"
    with NOTHING launched and verification UNKNOWN — the honesty
    guard's claim patterns only knew deletion words;
  * extraction returned 'it itunes' for the typo.
"""

from types import SimpleNamespace

import pytest

from app.agents.master_agent import extract_app_query
from app.cognition.action_planner import ActionPlanner
from app.cognition.completion_honesty import enforce_completion_honesty


# ── the typo extraction ───────────────────────────────────────────────────


class TestLeadingFiller:
    @pytest.mark.parametrize("text,expected", [
        ("open it itunes on my pc", "itunes"),
        ("open it up spotify", "spotify"),
        ("launch that vlc", "vlc"),
    ])
    def test_filler_words_are_stripped(self, text, expected):
        assert extract_app_query(text) == expected

    def test_single_word_candidates_survive(self):
        # stripping must never empty the candidate
        assert extract_app_query("open it") == ""  # 'it' alone is filler → honest ask
        assert extract_app_query("open firefox") == "firefox"


# ── the false completion claim ────────────────────────────────────────────


class TestHonestyGuardCoversLaunchClaims:
    def _result(self, reply, verified=False):
        return {
            "assistant_reply": reply,
            "user_text": "open it itunes on my pc",
            "goal_verified": verified,
            "executed_actions": ["Opened URL in desktop browser: https://google/..."],
            "goal_lifecycle_state": "waiting_for_evidence",
        }

    def test_confirmed_opened_manually_is_surfaced_as_unverified(self):
        # Her exact reply, verbatim.
        out = enforce_completion_honesty(self._result(
            "I've confirmed iTunes has been opened manually. The system could "
            "not verify this due to the process running in the background."))
        assert out["announcement_guard"] == "unverified_outcome_surfaced"
        assert "UNVERIFIED" in out["assistant_reply"]
        assert "NOT confirmed" in out["assistant_reply"]

    def test_has_been_opened_is_a_completion_claim(self):
        out = enforce_completion_honesty(self._result(
            "The application has been opened on your PC."))
        assert out["announcement_guard"] == "unverified_outcome_surfaced"

    def test_is_now_running_is_a_completion_claim(self):
        out = enforce_completion_honesty(self._result("iTunes is now running."))
        assert out["announcement_guard"] == "unverified_outcome_surfaced"

    def test_verified_outcomes_are_not_touched(self):
        reply = "The application has been opened on your PC."
        out = enforce_completion_honesty(self._result(reply, verified=True))
        assert "announcement_guard" not in out
        assert out["assistant_reply"] == reply


# ── the literal-command search derailment ─────────────────────────────────


def _branch(action, name, utility, query=None):
    return SimpleNamespace(
        hypothetical_action=action, branch_name=name, utility_score=utility,
        candidate_payload={"query_term": query} if query is not None else {},
        branch_id=name,
    )


class TestLiteralCommandSearchGuard:
    GOAL = "open it itunes on my pc"

    def test_googling_the_command_hands_the_win_to_a_real_branch(self):
        web = _branch("web_search", "Web Browser Fallback Search", 0.845, query=self.GOAL)
        launch = _branch("open_application", "Desktop Application Launch", 0.845)
        sim = SimpleNamespace(competing_branches=[web, launch])
        winner = ActionPlanner._guard_literal_command_search(sim, web, self.GOAL)
        assert winner.hypothetical_action == "open_application"

    def test_near_echo_queries_are_caught(self):
        web = _branch("web_search", "Search", 0.9, query="Open it iTunes on my PC!")
        other = _branch("list_windows", "Windows", 0.4)
        sim = SimpleNamespace(competing_branches=[web, other])
        assert ActionPlanner._guard_literal_command_search(
            sim, web, self.GOAL).hypothetical_action == "list_windows"

    def test_legitimate_search_is_untouched(self):
        web = _branch("web_search", "Search", 0.9, query="itunes download page")
        sim = SimpleNamespace(competing_branches=[web])
        assert ActionPlanner._guard_literal_command_search(
            sim, web, self.GOAL) is web

    def test_non_search_winners_are_untouched(self):
        launch = _branch("open_application", "Launch", 0.9)
        sim = SimpleNamespace(competing_branches=[launch])
        assert ActionPlanner._guard_literal_command_search(
            sim, launch, self.GOAL) is launch

    def test_derail_with_no_alternative_stands(self):
        # honest: a derail is still better than nothing — and the reply
        # layer remains bound by the honesty guard.
        web = _branch("web_search", "Search", 0.9, query=self.GOAL)
        sim = SimpleNamespace(competing_branches=[web])
        assert ActionPlanner._guard_literal_command_search(sim, web, self.GOAL) is web


def test_wiring_is_in_place():
    import inspect

    import app.cognition.action_planner as ap

    src = inspect.getsource(ap)
    assert "_guard_literal_command_search(sim_res, winner, goal_text)" in src
