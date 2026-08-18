from unittest.mock import MagicMock
from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_candidate_synthesis_skips_non_executable_world_model_capabilities():
    """
    P1 Fix Verification:
    Verify that Candidate Synthesizer checks capability executability and skips
    WorldModel capability entities that lack an executable handler in ToolRegistry/MasterAgent.
    """
    mock_world = MagicMock()

    executable_cap = MagicMock()
    executable_cap.name = "screen_capture"  # Executable capability

    non_executable_cap = MagicMock()
    non_executable_cap.name = "unsupported_quantum_magic"  # Non-executable capability entity

    mock_world.find_entities.return_value = [executable_cap, non_executable_cap]

    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="vision_desktop",
        user_text="Take screenshot and analyze",
        world_model=mock_world
    )

    action_types = [c.get("action_type") for c in candidates]

    # Executable screen_capture MUST be synthesized
    assert "screen_capture" in action_types

    # Non-executable unsupported_quantum_magic MUST be skipped
    assert "unsupported_quantum_magic" not in action_types
