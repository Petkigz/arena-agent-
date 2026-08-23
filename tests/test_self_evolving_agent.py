from unittest.mock import patch

from app.agents.self_evolving_agent import SelfEvolvingAgent


def test_self_evolving_agent_refuses_offline_placeholder_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(SelfEvolvingAgent, "DYNAMIC_TOOLS_DIR", tmp_path)
    simulated = {
        "success": False,
        "simulated": True,
        "error": "provider offline",
        "choices": [{"message": {"content": "offline diagnostic"}}],
    }
    with patch(
        "app.agents.self_evolving_agent.llm_client.generate_chat_completion",
        return_value=simulated,
    ):
        result = SelfEvolvingAgent.synthesize_and_hotload_tool(
            task_objective="Calculate Fibonacci sequence up to n=10",
            tool_name_query="fibonacci_calc",
        )

    assert result["success"] is False
    assert result["verified"] is False
    assert result["file_path"] is None
    assert list(tmp_path.iterdir()) == []
