import pytest
from app.agents.master_agent import MasterAgentOrchestrator

def test_master_agent_orchestration():
    res = MasterAgentOrchestrator.process_user_task("Do I have a song called Ordinary in my library on this PC?")
    assert res["success"] is True
    assert "assistant_reply" in res
    assert isinstance(res["assistant_reply"], str)
    assert len(res["assistant_reply"]) > 0

def test_master_agent_browser_intent():
    res = MasterAgentOrchestrator.process_user_task("Can you open Firefox and search for me ordinary on YouTube?")
    assert res["success"] is True
    assert len(res["executed_actions"]) > 0
    assert "Firefox" in res["executed_actions"][0]
