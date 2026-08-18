from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime
from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
from app.cognition.reasoning_loop import CycleTrace


def test_runtime_respects_authoritative_reasoning_decision_without_keyword_override(tmp_path):
    """
    Verify CognitiveRuntime decision router respects reasoning_action directly
    without secondary runtime keyword overrides.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    # Mock reasoning cycle to return ReasoningAction.ANSWER even for a text containing 'find'
    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ANSWER, confidence=0.9, reason="Conversational answer")]
    )

    mock_llm_reply = {
        "choices": [{
            "message": {
                "content": "To find your purpose, reflect on what energizes you."
            }
        }],
        "model": "fast"
    }

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.llm.llm_client.generate_chat_completion", return_value=mock_llm_reply):

        res = runtime.process_cognitive_cycle(user_text="How do I find my purpose in life?")

        # Must follow ReasoningAction.ANSWER branch
        assert res["reasoning_action"] == "answer"
        assert res["action_type"] == "formulate_answer"
        assert "reflect on what energizes you" in res["assistant_reply"]
