from unittest.mock import patch
from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_heuristic_baseline_query_confidence():
    """
    Ambiguous / conversational query without explicit keyword defaults to baseline confidence 0.55.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("What is the nature of consciousness?")
    assert goal_rep.confidence == 0.55
    assert goal_rep.provenance_source == "heuristic_baseline"


def test_clear_deterministic_keyword_intent_confidence():
    """
    Explicit action keyword command yields clear intent confidence 0.90.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    assert goal_rep.confidence == 0.90
    assert goal_rep.provenance_source == "clear_deterministic_keyword_intent"


def test_llm_heuristic_agreement_yields_high_confidence():
    """
    When LLM domain & intent agree with heuristics, confidence is boosted to 0.95.
    """
    mock_llm_reply = {
        "choices": [{
            "message": {
                "content": '{"primary_intent_type": "action_intent", "target_domain": "desktop_os", "goal": "Launch Photoshop", "desired_outcome": "Photoshop process running"}'
            }
        }]
    }

    with patch("app.llm.llm_client.generate_chat_completion", return_value=mock_llm_reply):
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop", complexity="main")
        assert goal_rep.confidence == 0.95
        assert goal_rep.provenance_source == "llm_heuristic_agreement"


def test_llm_heuristic_conflict_calibrates_lower_confidence():
    """
    When LLM domain or intent conflicts with heuristics, confidence drops to 0.60.
    """
    mock_llm_reply = {
        "choices": [{
            "message": {
                "content": '{"primary_intent_type": "knowledge_query", "target_domain": "conversation", "goal": "Chat about Photoshop", "desired_outcome": "Conversational response delivered"}'
            }
        }]
    }

    with patch("app.llm.llm_client.generate_chat_completion", return_value=mock_llm_reply):
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop", complexity="main")
        assert goal_rep.confidence == 0.60
        assert goal_rep.provenance_source == "llm_heuristic_conflict"
