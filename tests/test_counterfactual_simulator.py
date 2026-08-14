import pytest
from app.cognition.counterfactual_simulator import CounterfactualSimulator

def test_counterfactual_simulator():
    candidates = [
        {"name": "Branch A (Safe Search)", "action_type": "search_files", "payload": {"query": "Ordinary"}},
        {"name": "Branch B (Destructive Delete)", "action_type": "delete_file", "payload": {"file_path": "delete_all.txt"}}
    ]

    sim_res = CounterfactualSimulator.simulate_competing_branches(
        target_goal="Find song Ordinary",
        candidate_actions=candidates
    )

    assert sim_res.simulation_id is not None
    assert sim_res.winning_branch.branch_name == "Branch A (Safe Search)"
    assert sim_res.winning_branch.risk_score < 0.5
