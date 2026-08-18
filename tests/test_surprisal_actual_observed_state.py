from unittest.mock import patch
from app.cognition.runtime import CognitiveRuntime
from app.cognition.goal_lifecycle import GoalLifecycleState


def test_surprisal_evaluation_uses_actual_observed_state_without_fabricated_running(tmp_path):
    """
    P1 Fix Verification:
    Verify PredictionEngine.evaluate_surprisal is passed actual_state derived from
    captured obs_state (WorldModel observations/entities) without a hardcoded app_state='running'.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    evaluated_actual_state = None

    def mock_evaluate_surprisal(prediction, actual_state):
        nonlocal evaluated_actual_state
        evaluated_actual_state = actual_state
        return 0.5

    mock_execute = {
        "executed_actions": ["Attempted to open Photoshop"],
        "assistant_reply": "Photoshop failed to open.",
        "model_used": "fast"
    }

    with patch("app.cognition.prediction_engine.PredictionEngine.evaluate_surprisal", side_effect=mock_evaluate_surprisal), \
         patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", return_value=mock_execute):

        res = runtime.process_cognitive_cycle(user_text="Open Photoshop", complexity="fast")

        assert evaluated_actual_state is not None
        # MUST NOT contain fabricated 'app_state': 'running'
        assert evaluated_actual_state.get("app_state") != "running"
        assert "entities" in evaluated_actual_state
        assert "observations" in evaluated_actual_state
