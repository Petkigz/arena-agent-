from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime


def test_runtime_passes_authoritative_world_and_memory_to_interpreter(tmp_path):
    """
    Verify CognitiveRuntime passes its authoritative self.memory and self.world
    instances down to SemanticGoalInterpreter.interpret_goal during candidate strategy synthesis.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    passed_memory = None
    passed_world = None

    def mock_interpret_goal(user_text, complexity="fast", memory_store=None, world_model=None):
        nonlocal passed_memory, passed_world
        passed_memory = memory_store
        passed_world = world_model
        from app.cognition.goal_interpreter import SemanticGoalRepresentation
        return SemanticGoalRepresentation(
            user_query=user_text,
            primary_intent_type="knowledge_query",
            target_domain="conversation",
            goal="Respond",
            desired_outcome="Delivered",
            entities=[],
            constraints=[],
            assumptions=[],
            unknowns=[],
            preconditions=[],
            success_conditions=["response_delivered = true"],
            failure_conditions=[],
            required_capabilities=["llm.generate"],
            risk_factors=[]
        )

    with patch("app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal", side_effect=mock_interpret_goal):
        runtime.process_cognitive_cycle("Hello assistant", complexity="fast")

        assert passed_memory is not None
        assert passed_world is not None
        assert passed_memory == runtime.memory
        assert passed_world == runtime.world
