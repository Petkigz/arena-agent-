import pytest
import os
from app.agents.self_evolving_agent import SelfEvolvingAgent

def test_self_evolving_agent():
    res = SelfEvolvingAgent.synthesize_and_hotload_tool(
        task_objective="Calculate Fibonacci sequence up to n=10",
        tool_name_query="fibonacci_calc"
    )
    assert res["success"] is True
    assert "file_path" in res
    assert os.path.exists(res["file_path"])
