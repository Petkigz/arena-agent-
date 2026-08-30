import pytest
from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.tool_registry import ToolRegistry
from app.cognition.cognitive_pipeline import CognitivePipeline

def test_action_proposal_and_gate():
    prop = ActionProposal(action_type="search_files", payload={"query": "test"})
    res = ActionGate.evaluate_proposal(prop)
    assert res.allowed is True
    assert res.gate_name == "passed_all_gates"

def test_tool_registry():
    tr = ToolRegistry()
    res = tr.execute_registered_tool("search_files", {"query": "test"})
    assert "files" in res or "success" in res

def test_cognitive_pipeline():
    cp = CognitivePipeline()
    res = cp.process_request("Can you open Firefox and search Ordinary?")
    # Honest delegation contract: success is whatever the runtime decided —
    # never manufactured — and failures always carry a reason.
    assert isinstance(res["success"], bool)
    assert "goal_verified" in res and "goal_lifecycle_state" in res and "reason" in res
    if res["success"] is False:
        assert res["reason"]
    assert "session_id" in res
    assert "assistant_reply" in res
