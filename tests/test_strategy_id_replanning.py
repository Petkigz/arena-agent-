from app.cognition.goal_replanner import GoalReplanner
from app.cognition.action_proposal import ActionProposal


def test_compute_strategy_id_generates_deterministic_strategy_ids():
    """
    P1 Fix Verification:
    Verify compute_strategy_id produces deterministic, query-differentiated strategy_id strings
    for candidate dictionaries and ActionProposal objects.
    """
    candidate_a = {
        "name": "Local Filesystem Search",
        "action_type": "search_files",
        "payload": {"query": "contract_2026.pdf", "action_type": "search_files"}
    }
    candidate_b = {
        "name": "Broader Filesystem Search",
        "action_type": "search_files",
        "payload": {"query": "contract_2026", "action_type": "search_files"}
    }

    id_a = GoalReplanner.compute_strategy_id(candidate_a)
    id_b = GoalReplanner.compute_strategy_id(candidate_b)

    assert id_a != id_b
    assert id_a.startswith("search_files::")
    assert "contract_2026pdf" in id_a
    assert "contract_2026" in id_b

    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "contract_2026.pdf", "action_type": "search_files"}
    )
    id_prop = GoalReplanner.compute_strategy_id(proposal)

    # Strategy ID for proposal with same query and action_type matches candidate_a's strategy query signature
    assert "search_files::" in id_prop
    assert "contract_2026pdf" in id_prop
