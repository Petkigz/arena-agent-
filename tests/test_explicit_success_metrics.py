from unittest.mock import patch
from app.cognition.runtime import CognitiveRuntime


def test_runtime_exposes_distinct_success_concepts(tmp_path):
    """
    P1 Fix Verification:
    Verify CognitiveRuntime exposes request_success, execution_success, and goal_verified as distinct concepts.
    When execution succeeds but goal verification fails, execution_success=True while goal_verified=False.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    mock_execute = {
        "success": True,
        "executed_actions": ["Launched Photoshop"],
        "assistant_reply": "Photoshop process crashed immediately with code 1.",
        "model_used": "fast"
    }

    with patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", return_value=mock_execute):
        res = runtime.process_cognitive_cycle(user_text="Open Photoshop", complexity="fast")

        # 3 distinct concepts verified
        assert "request_success" in res
        assert "execution_success" in res
        assert "goal_verified" in res

        # Request processed cleanly
        assert res["request_success"] is True
        # Tool execution attempt ran
        assert res["execution_success"] is True
        # Goal verification failed due to crash
        assert res["goal_verified"] is False
