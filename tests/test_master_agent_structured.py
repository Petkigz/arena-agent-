from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal


def test_execute_proposal_unknown_action_type_returns_structured_failure():
    """
    Verify passing an unknown proposal action_type to execute_proposal returns
    a structured failure response without calling process_user_task fallback.
    """
    unknown_proposal = ActionProposal(
        action_type="unsupported_quantum_magic",
        payload={"target": "system"}
    )

    res = MasterAgentOrchestrator.execute_proposal(
        proposal=unknown_proposal,
        user_text="Perform quantum magic"
    )

    assert res["success"] is False
    assert res["unsupported_capability"] == "unsupported_quantum_magic"
    assert "unsupported by capability resolvers" in res["assistant_reply"]
    assert len(res["executed_actions"]) == 0


def test_execute_proposal_supported_action_type_succeeds():
    """
    Verify supported proposal action_types (e.g. search_files) execute directly.
    """
    search_proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "Ordinary"}
    )

    res = MasterAgentOrchestrator.execute_proposal(
        proposal=search_proposal,
        user_text="Find my song Ordinary"
    )

    assert res["success"] is True
    assert len(res["executed_actions"]) > 0
