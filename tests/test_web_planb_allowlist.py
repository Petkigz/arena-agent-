"""F5 (DIAG D9): web Plan-B must EARN its place — an allowlist, not a denylist.

Live bug (owner machine, 2026-09-01): 'Set up a project to organize my
photo collection ...' — the primary action failed and the GoalReplanner's
Plan-B ladder reached the blanket 'Web Research Fallback': the owner's
project-setup request was sent to google.com (429) and could never verify
there.

The pre-fix filter was a DENYLIST: web actions were excluded only when the
goal's conditions contained local-ARTIFACT keys. The live goal's conditions
came from the LLM v2 path ('project_created = true', 'photos_grouped =
true') — no artifact key — so the denylist missed and web_search stayed in
the ladder. A denylist that depends on condition VOCABULARY loses every
time the model words conditions differently.

The inversion: web-research actions may enter the Plan-B ladder only for
INFORMATION goals — the domain is web research, or the goal is a knowledge
query whose conditions are reply-shaped. Action goals (create / set up /
organize / install / compute) can never be satisfied by a public search,
and routing them there leaks the request. First-attempt discovery breadth
is untouched (the P2 constraint); this is the replan ranking layer.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_replanner import GoalReplanner


D9_TEXT = ("Set up a project to organize my photo collection (diag-abc123): "
           "scan the pictures folder, group photos by date, find "
           "duplicates, then report a summary.")


def _goal(intent, domain, conditions):
    return SimpleNamespace(
        primary_intent_type=intent,
        target_domain=domain,
        success_conditions=list(conditions),
        unknowns=[],
        confidence=0.7,
        entities=[],
    )


def _failed(action_type="read_document"):
    return SimpleNamespace(
        is_unknown=False,
        failed_conditions=["primary strategy failed"],
        verification_reason="nope",
        failed_action_type=action_type,
        failed_payload={},
    )


def _replan(goal_rep, text=D9_TEXT):
    tracker = GoalTracker(user_query=text)
    tracker.current_state = GoalLifecycleState.FAILED
    return GoalReplanner.execute_reassessment_and_replan(
        text, goal_rep, _failed(), tracker)


# ── the inverted predicate ──────────────────────────────────────────────

def test_web_actions_blocked_for_action_intent_goals():
    """The exact live D9 shape: action intent, LLM-authored conditions
    WITHOUT local-artifact keys — the denylist's blind spot."""
    goal = _goal("action_intent", "filesystem",
                 ["project_created = true", "photos_grouped = true"])
    assert GoalReplanner._cannot_satisfy_goal_conditions("web_search", goal) is True
    assert GoalReplanner._cannot_satisfy_goal_conditions("open_url", goal) is True


def test_web_actions_blocked_for_local_content_knowledge_queries():
    """D2 shape: a knowledge query whose answer must come from LOCAL data
    (the CSV's mean) — a public search cannot produce it."""
    goal = _goal("knowledge_query", "data",
                 ["answer_value_in_reply = true"])
    assert GoalReplanner._cannot_satisfy_goal_conditions("web_search", goal) is True


def test_web_actions_allowed_for_web_domain():
    goal = _goal("action_intent", "web_research",
                 ["search_results_retrieved = true"])
    assert GoalReplanner._cannot_satisfy_goal_conditions("web_search", goal) is False


def test_web_actions_allowed_for_pure_knowledge_queries():
    """A plain information question keeps the web as a legitimate Plan-B."""
    goal = _goal("knowledge_query", "conversation",
                 ["response_delivered = true"])
    assert GoalReplanner._cannot_satisfy_goal_conditions("web_search", goal) is False


def test_metadata_less_goal_falls_back_to_condition_shape():
    """Back-compat with condition-only goal views: the shape of the
    conditions decides (the pre-existing contract)."""
    # web-shaped condition -> allowed
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "web_search", SimpleNamespace(success_conditions=["search_results_retrieved = true"])) is False
    # local artifact condition -> blocked
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "web_search", SimpleNamespace(success_conditions=["file_path_identified = true"])) is True
    # no conditions -> no structural filter
    assert GoalReplanner._cannot_satisfy_goal_conditions(
        "web_search", SimpleNamespace(success_conditions=[])) is False


def test_local_actions_are_never_filtered_by_the_web_allowlist():
    goal = _goal("action_intent", "filesystem",
                 ["project_created = true"])
    for action in ("search_files", "investigate", "read_document", "list_directory"):
        assert GoalReplanner._cannot_satisfy_goal_conditions(action, goal) is False


# ── the replan ladder ───────────────────────────────────────────────────

def _interpret_with_llm_payload(text, payload):
    """The live v2 shape: the model's representation, as the pipeline
    actually received it (mocked LLM, deterministic offline)."""
    import json
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value={"success": True,
                             "choices": [{"message": {"content": json.dumps(payload)}}]}):
        return SemanticGoalInterpreter.interpret_goal(text, complexity="main")


D9_LIVE_PAYLOAD = {
    "primary_intent_type": "action_intent",
    "target_domain": "filesystem",
    "goal": "Organize the photo collection into a project",
    "desired_outcome": "Project created with milestones and photos organized",
    "entities": ["photo collection", "pictures folder"],
    "success_conditions": ["project_created = true", "photos_grouped = true"],
    "failure_conditions": ["project_creation_failed = true"],
    "required_capabilities": ["filesystem.search"],
    "risk_factors": ["low"],
}


def test_d9_live_shape_ladder_never_proposes_web():
    """The live goal representation (LLM v2, no artifact keys) — the
    Plan-B proposal must be a local/diagnostic branch, never web."""
    goal = _interpret_with_llm_payload(D9_TEXT, D9_LIVE_PAYLOAD)
    assert goal.primary_intent_type == "action_intent"
    tracker = GoalTracker(user_query=D9_TEXT)
    tracker.current_state = GoalLifecycleState.FAILED
    proposal = GoalReplanner.execute_reassessment_and_replan(
        D9_TEXT, goal, _failed(), tracker)
    assert proposal is not None
    assert proposal.action_type not in ("web_search", "open_url"), \
        f"an action goal's Plan-B must not route to the public web: {proposal.action_type}"


def test_information_goal_keeps_web_planb():
    """Guard against over-narrowing: an information question that failed
    its primary branch may still fall back to web research."""
    text = "What is the release date of the Ligero framework?"
    goal = SemanticGoalInterpreter.interpret_goal(text)
    assert goal.primary_intent_type == "knowledge_query"
    tracker = GoalTracker(user_query=text)
    tracker.current_state = GoalLifecycleState.FAILED
    proposal = GoalReplanner.execute_reassessment_and_replan(
        text, goal, _failed(), tracker)
    assert proposal is not None
    # The web branch is still IN the ladder for information goals — the
    # proposal itself may legitimately be web_search.
    assert proposal.action_type not in ("code_explain", "resize_image")


# ── end to end: no browser for the D9 request ───────────────────────────

def test_d9_full_chat_never_opens_a_browser():
    from app.cognition.cognitive_pipeline import CognitivePipeline

    opened: list = []

    def _spy_open(url, *a, **k):
        opened.append(url)
        return False

    with patch("webbrowser.open", side_effect=_spy_open):
        res = CognitivePipeline.process_chat(user_text=D9_TEXT, complexity="fast")

    assert opened == [], \
        f"a project-setup goal must never be routed to the public web: {opened}"
    assert res.get("success") is not True or res.get("goal_verified") is not True
