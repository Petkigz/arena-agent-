"""Phase 3: structural analogies influence planning without bypassing gates."""

from types import SimpleNamespace

from app.cognition.action_planner import ActionPlanner


class _AnalogicalMemory:
    def find_analogies(self, **kwargs):
        return [
            SimpleNamespace(
                similarity=0.8,
                past_task=SimpleNamespace(action_type="search_files", success=True),
            )
        ]


def test_structural_success_adjusts_matching_candidate_only():
    goal_rep = SimpleNamespace(
        primary_intent_type="search_intent",
        target_domain="filesystem",
    )
    resource_manager = SimpleNamespace(get_usage_report=lambda: {"budgets": {}})
    candidates = [
        {"name": "Search files", "action_type": "search_files", "payload": {}},
        {"name": "Search web", "action_type": "web_search", "payload": {}},
    ]

    proposal = ActionPlanner.plan_and_evaluate_action(
        "Find project files",
        goal_rep=goal_rep,
        candidates=candidates,
        analogical_memory=_AnalogicalMemory(),
        hardware_self_model={},
        resource_manager=resource_manager,
    )

    branches = {item["action_type"]: item for item in proposal.alternatives_considered}
    assert branches["search_files"]["utility_score"] > branches["web_search"]["utility_score"]
    assert "AnalogyAdj=1.10" in branches["search_files"]["reasoning_summary"]
    assert "AnalogyAdj" not in branches["web_search"]["reasoning_summary"]
    assert "_analogical_adjustment" not in proposal.payload
