"""P0 review #3: dynamic candidate breadth — a fixed 5-result discovery
funnel can lose a NECESSARY capability before planning begins.

"Find the PDF, extract page 4, summarize it, convert it to DOCX and save
it." needs ~6 capabilities. Breadth now scales with the complexity tier
(fast 5 / main 10 / deep 20) AND with the number of distinct action verbs
the goal names — whichever is larger.
"""

from unittest.mock import patch

from app.cognition.goal_interpreter import (
    SemanticGoalInterpreter,
    candidate_breadth,
)

MULTI_STEP = (
    "Find the PDF, extract page 4, summarize it, convert it to DOCX and save it."
)


def test_breadth_scales_with_complexity():
    assert candidate_breadth("open chrome", "fast") == 5
    assert candidate_breadth("open chrome", "main") == 10
    assert candidate_breadth("open chrome", "deep") == 20


def test_multi_step_goal_widens_breadth_regardless_of_routing():
    """Five distinct action verbs must widen the funnel even on the fast
    tier — routing complexity is a latency decision, not a statement about
    how many capabilities the goal needs."""
    breadth = candidate_breadth(MULTI_STEP, "fast")
    assert breadth >= 10, breadth


def test_breadth_is_capped():
    everything = " ".join([
        "find search locate list open read extract parse summarize convert",
        "save write create copy move rename delete compress zip unzip send",
        "email upload download install update check verify monitor analyze",
    ])
    assert candidate_breadth(everything, "deep") <= 24


def test_multi_step_goal_surfaces_necessary_capabilities():
    """THE review case: search_files and the PDF capabilities must reach the
    candidate list — not be cut by a five-slot funnel before planning."""
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="filesystem", user_text=MULTI_STEP, complexity="fast")
    actions = {c.get("action_type") for c in candidates}
    assert "search_files" in actions
    assert any("pdf" in a for a in actions), actions
    assert len(candidates) >= 8, [c.get("action_type") for c in candidates]


def test_rank_tools_receives_the_dynamic_limit():
    captured = {}

    def fake_rank(user_text, limit=6, domain_hint=None, manifest=None):
        captured["limit"] = limit
        return []

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank):
        SemanticGoalInterpreter.synthesize_candidates_from_context(
            domain="filesystem", user_text=MULTI_STEP, complexity="fast")
    assert captured["limit"] == candidate_breadth(MULTI_STEP, "fast")

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank):
        SemanticGoalInterpreter.synthesize_candidates_from_context(
            domain="filesystem", user_text="open chrome", complexity="fast")
    assert captured["limit"] == 5


def test_interpret_goal_threads_complexity_into_discovery():
    captured = {}

    def fake_rank(user_text, limit=6, domain_hint=None, manifest=None):
        captured["limit"] = limit
        return []

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank):
        SemanticGoalInterpreter.interpret_goal("open chrome", complexity="deep")
    assert captured["limit"] == 20
