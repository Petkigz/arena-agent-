import pytest
from app.cognition.action_proposal import ActionProposal, ActionGate

def test_action_proposal_boundary():
    # 1. Proposal for safe action (read_file)
    prop1 = ActionProposal(action_type="read_file", payload={"file_path": "README.md"})
    gate1 = ActionGate.evaluate_proposal(prop1)
    assert gate1.allowed is True
    assert gate1.gate_name == "passed_all_gates"

    # 2. Proposal for Level 3 action requiring approval (send_email)
    prop2 = ActionProposal(action_type="send_email", payload={"to": "test@example.com"})
    gate2 = ActionGate.evaluate_proposal(prop2)
    assert gate2.allowed is False
    assert gate2.requires_approval is True
    assert gate2.gate_name == "policy_gate"
