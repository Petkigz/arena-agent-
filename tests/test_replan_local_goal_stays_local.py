"""Plan-B for local-file goals stays local (external audit 2026-09).

The audited misroute: 'Find files matching goal_verifier, then tell me how
many you found.' — search_files (with the then-garbled query) found
nothing, verification failed, and the GoalReplanner's Plan-B ladder picked
web_search: the owner's PRIVATE local-file request was sent to google.com
in a desktop browser. Two independent problems with that branch:
  * it can never verify — web_search cannot produce a local file path, so
    'file_path_identified = true' is unsatisfiable there;
  * it leaks the request — a local-file question routed to a public
    search engine.

The fix lives in the REPLAN ranking layer (first-attempt discovery breadth
is untouched): Plan-B candidates that structurally cannot satisfy the
goal's success conditions are filtered out of the replan ladder.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_replanner import GoalReplanner

# ── the predicate ────────────────────────────────────────────────────────────

def _goal(conditions):
    return SimpleNamespace(success_conditions=list(conditions))


def test_web_actions_cannot_satisfy_local_artifact_conditions():
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "web_search", _goal(["file_path_identified = true"])) is True
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "open_url", _goal(["path_found = true"])) is True


def test_local_actions_are_never_filtered():
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "search_files", _goal(["file_path_identified = true"])) is False
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "list_directory", _goal(["file_path_identified = true"])) is False


def test_web_goals_keep_web_actions_no_over_narrowing():
    # A web-research goal's success conditions have no local-artifact key:
    # web_search stays a legitimate Plan-B branch there.
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "web_search", _goal(["search_results_retrieved = true"])) is False


def test_no_conditions_means_no_structural_filter():
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "web_search", _goal([])) is False


# ── the replan ladder ────────────────────────────────────────────────────────

def test_replan_of_a_failed_local_search_never_proposes_web_search():
    """The audited cascade, unit level: filesystem goal, failed search_files
    instance — the replan proposal must be a LOCAL or diagnostic branch,
    never web_search/open_url."""
    from app.cognition.goal_lifecycle import GoalTracker

    text = "Find files matching zzz_definitely_not_on_disk, then tell me how many you found."
    goal_rep = SemanticGoalInterpreter.interpret_goal(text)
    assert goal_rep.target_domain == "filesystem", "test premise"

    failed = SimpleNamespace(
        is_unknown=False,
        failed_conditions=["file_path_identified = true"],
        verification_reason="no file matched",
        failed_action_type="search_files",
        failed_payload={"query": "zzz_definitely_not_on_disk"},
    )
    tracker = GoalTracker(user_query=text)
    # Realistic lifecycle position for a replan: the goal executed,
    # verification FAILED, and the replanner takes over (FAILED ->
    # REASSESSING is the valid transition the replanner drives).
    from app.cognition.goal_lifecycle import GoalLifecycleState
    tracker.current_state = GoalLifecycleState.FAILED
    proposal = GoalReplanner.execute_reassessment_and_replan(
        text, goal_rep, failed, tracker)
    assert proposal is not None
    assert proposal.action_type not in ("web_search", "open_url"), \
        f"a local-file goal's Plan-B must not route to the public web: {proposal.action_type}"


def test_full_chat_loop_never_opens_a_browser_for_a_local_file_goal():
    """End-to-end through the real cognitive pipeline, the exact scenario
    class the external audit hit (LLM offline, local search genuinely
    misses): no browser may be opened — not even attempted."""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    opened: list = []

    def _spy_open(url, *a, **k):
        opened.append(url)
        return False

    text = ("Find files matching zzz_definitely_not_on_disk_anywhere, "
            "then tell me how many you found.")
    with patch("webbrowser.open", side_effect=_spy_open):
        res = CognitivePipeline.process_chat(user_text=text, complexity="fast")

    assert opened == [], \
        f"a local-file goal must never be routed to the public web: {opened}"
    # and the loop must still be honest about the miss
    assert res.get("success") is not True or res.get("goal_verified") is not True
