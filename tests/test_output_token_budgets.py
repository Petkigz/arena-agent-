"""P0 #19: output token budgets are task-dependent, not a flat 150.

The main conversational/action paths called the local LLM with
max_tokens=150, so ambiguity understanding, multi-step planning, structured
reasoning and evidence answers were truncated into "the model doesn't
understand" — when the real issue was the tiny output budget.

Contract: every important path draws its budget from app.llm.output_budget,
scaled by task kind and complexity.
"""

from unittest.mock import patch

from app.llm import OUTPUT_TOKEN_BUDGETS, llm_client, output_budget
from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_budget_table_contract():
    kinds = {"conversational", "evidence_answer", "action_summary", "structured"}
    assert set(OUTPUT_TOKEN_BUDGETS) == kinds
    for kind, table in OUTPUT_TOKEN_BUDGETS.items():
        assert set(table) == {"fast", "main", "deep"}, kind
        # More complexity -> at least as much room, never less.
        assert table["deep"] >= table["main"] >= table["fast"], kind
    # Structured reasoning (planning, interpretation) is the most expensive
    # kind; action summaries are the cheapest.
    for level in ("fast", "main", "deep"):
        assert OUTPUT_TOKEN_BUDGETS["structured"][level] >= \
               OUTPUT_TOKEN_BUDGETS["conversational"][level]
        assert OUTPUT_TOKEN_BUDGETS["action_summary"][level] <= \
               OUTPUT_TOKEN_BUDGETS["conversational"][level]


def test_budgets_leave_the_flat_150_behind():
    assert output_budget("conversational", "fast") == 300
    assert output_budget("evidence_answer", "fast") == 500
    assert output_budget("structured", "fast") == 600
    assert output_budget("structured", "deep") == 3000


def test_unknown_kind_fails_loudly():
    try:
        output_budget(" essays ")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown budget kind must raise")


def test_unknown_complexity_falls_back_to_main():
    assert output_budget("conversational", "extravagant") == \
        OUTPUT_TOKEN_BUDGETS["conversational"]["main"]


def _capture_client(reply="OK."):
    """Patch the shared LLM client and record every max_tokens it receives."""
    captured = []

    def fake(messages=None, complexity="fast", max_tokens=512, **kw):
        captured.append({"complexity": complexity, "max_tokens": max_tokens})
        return {
            "id": "chat-real",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                         "finish_reason": "stop"}],
        }

    return captured, fake


def test_goal_interpretation_gets_structured_budget():
    """The 'understand ambiguity' JSON step was capped at 300 tokens."""
    captured, fake = _capture_client(reply="not json, but the call is what matters")
    with patch.object(llm_client, "generate_chat_completion", side_effect=fake, create=True):
        try:
            # complexity="main" triggers the deeper interpretation path
            SemanticGoalInterpreter.interpret_goal(
                "organize my files and back them up to the external drive",
                complexity="main")
        except Exception:
            pass  # parse may reject the canned reply; the budget is the contract
    assert captured, "goal interpreter never called the LLM"
    assert all(c["max_tokens"] >= output_budget("structured", "fast") for c in captured)
    assert all(c["max_tokens"] != 300 for c in captured)


def test_evidence_answer_cycle_gets_evidence_budget(tmp_path):
    """A file-existence question forces the evidence-grounded ANSWER branch;
    its reply budget must be the evidence_answer budget (main model), not 150."""
    import sys
    sys.path.insert(0, ".")
    from app.cognition.runtime import CognitiveRuntime

    captured, fake = _capture_client(
        reply="Yes — I found it. The file 'london.mp3' exists in your Music folder."
    )
    rt = CognitiveRuntime(db_path=str(tmp_path / "t.db"))
    with patch.object(llm_client, "generate_chat_completion", side_effect=fake, create=True):
        rt.process_cognitive_cycle(
            user_text="do i have a song called london", complexity="fast")
    assert captured, "cycle never called the LLM"
    reply_calls = [c for c in captured if c["max_tokens"] >= 400]
    assert reply_calls, f"no call got an evidence-scale budget: {captured}"
    assert all(c["max_tokens"] != 150 for c in captured)


def test_action_summary_budget(tmp_path):
    """The ACT branch's post-execution reply draws the action_summary budget."""
    import sys
    sys.path.insert(0, ".")
    from app.agents.master_agent import MasterAgentOrchestrator
    from app.cognition.action_proposal import ActionProposal

    captured, fake = _capture_client(reply="Searched your files.")
    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "report.pdf"},
        recommendation_reason="test",
        confidence=0.8,
    )
    with patch.object(llm_client, "generate_chat_completion", side_effect=fake, create=True):
        MasterAgentOrchestrator.execute_proposal(
            proposal, "find report.pdf", complexity="fast")
    assert captured, "execute_proposal never called the LLM"
    assert captured[-1]["max_tokens"] == output_budget("action_summary", "fast")
    assert captured[-1]["max_tokens"] != 150
