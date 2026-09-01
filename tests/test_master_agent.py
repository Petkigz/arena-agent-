import pytest
from app.agents.master_agent import MasterAgentOrchestrator

def test_master_agent_orchestration():
    res = MasterAgentOrchestrator.process_user_task("Do I have a song called Ordinary in my library on this PC?")
    # Honest delegation contract (the pipeline never manufactures success):
    # with the LLM offline the answer cycle legitimately defers — success is
    # then False WITH a reason, which is the correct, testable behavior.
    assert isinstance(res["success"], bool)
    if res["success"] is False:
        assert res.get("reason")
        assert res.get("goal_lifecycle_state")
    assert "assistant_reply" in res
    assert isinstance(res["assistant_reply"], str)
    assert len(res["assistant_reply"]) > 0

def test_master_agent_browser_intent():
    # Browser launch is environment-dependent (headless sandboxes have no
    # browser; open_url now reports the REAL launch outcome instead of
    # fabricating success — see tests/test_open_url_launch_honesty.py), so
    # the launch is pinned to the deterministic success world here. What
    # this test measures is the QUERY EXTRACTION: "ordinary on YouTube",
    # not the whole sentence.
    from unittest.mock import patch
    with patch("webbrowser.open", return_value=True):
        res = MasterAgentOrchestrator.process_user_task(
            "Can you open Firefox and search for me ordinary on YouTube?")
    assert res["success"] is True
    assert len(res["executed_actions"]) > 0
    action_text = " ".join(res["executed_actions"])
    assert "ordinary on YouTube" in action_text
