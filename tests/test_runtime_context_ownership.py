from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime
from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_runtime_passes_authoritative_world_memory_and_registry_to_interpreter(tmp_path):
    """
    Verify CognitiveRuntime passes its authoritative self.memory, self.world, and self.registry
    instances down to SemanticGoalInterpreter.interpret_goal during candidate strategy synthesis.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    passed_memory = None
    passed_world = None
    passed_registry = None

    def mock_interpret_goal(user_text, complexity="fast", memory_store=None, world_model=None, tool_registry=None, **kwargs):
        nonlocal passed_memory, passed_world, passed_registry
        passed_memory = memory_store
        passed_world = world_model
        passed_registry = tool_registry
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
        assert passed_registry is not None
        assert passed_memory == runtime.memory
        assert passed_world == runtime.world
        assert passed_registry == runtime.registry


def test_candidate_synthesis_does_not_instantiate_fallback_stores_when_unsupplied():
    """
    Verify candidate strategy synthesis does not instantiate new MemoryStore() or WorldModel()
    when memory_store or world_model are not passed, preventing uncoordinated store creation.
    """
    with patch("app.cognition.memory.MemoryStore.__init__", side_effect=RuntimeError("MemoryStore instantiated!")) as mock_ms_init, \
         patch("app.cognition.world_model.WorldModel.__init__", side_effect=RuntimeError("WorldModel instantiated!")) as mock_wm_init:

        # Should synthesize baseline domain candidates cleanly without instantiating MemoryStore or WorldModel
        candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
            domain="desktop_os",
            user_text="Open Photoshop",
            memory_store=None,
            world_model=None
        )

        assert len(candidates) > 0
        action_types = [c.get("action_type") for c in candidates]
        assert "open_application" in action_types
        assert mock_ms_init.call_count == 0
        assert mock_wm_init.call_count == 0

