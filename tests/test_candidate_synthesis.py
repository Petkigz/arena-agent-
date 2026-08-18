from unittest.mock import MagicMock
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.action_planner import ActionPlanner


def test_candidate_strategy_synthesis_combines_context():
    """
    Verify candidate strategy synthesis generates candidates combining domain baseline,
    WorldModel capabilities, and MemoryStore reflections.
    """
    mock_memory = MagicMock()
    mock_mem_item = MagicMock()
    mock_mem_item.content = "Used strategy: investigate system logs before launching app"
    mock_mem_item.task_id = "t_past123"
    mock_memory.search.return_value = [mock_mem_item]

    mock_world = MagicMock()
    mock_cap_entity = MagicMock()
    mock_cap_entity.name = "screen_capture"
    mock_world.find_entities.return_value = [mock_cap_entity]

    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os",
        user_text="Open Photoshop and scan system",
        memory_store=mock_memory,
        world_model=mock_world
    )

    action_types = [c.get("action_type") for c in candidates]
    sources = [c.get("source", "domain_baseline") for c in candidates]

    # Baseline desktop candidates included
    assert "open_application" in action_types
    assert "web_search" in action_types

    # Memory strategy candidate included
    assert "memory_store" in sources

    # WorldModel dynamic capability candidate included
    assert "world_model_capability" in sources
    assert "screen_capture" in action_types
