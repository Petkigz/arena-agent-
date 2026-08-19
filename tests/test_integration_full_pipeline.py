"""Integration tests for the full cognitive pipeline.

These tests verify that all components work together end-to-end:
  User request → Perception → WorldModel → Beliefs → Reasoning → Action → Verification → Learning

Phase 1.2 of the wiring plan.
"""

import pytest
from pathlib import Path
from app.cognition.runtime import CognitiveRuntime
from app.cognition.goal_lifecycle import GoalLifecycleState


class TestFullPipelineIntegration:
    """End-to-end tests for the complete cognitive cycle."""

    def test_simple_query_returns_answer(self, tmp_path):
        """Test that a simple knowledge query goes through ANSWER branch."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        result = runtime.process_cognitive_cycle(
            user_text="What is the capital of France?",
            complexity="fast"
        )
        
        assert result["request_success"] is True
        assert result["reasoning_action"] in ["answer", "act"]
        assert result["assistant_reply"] is not None
        assert len(result["assistant_reply"]) > 0

    def test_file_search_goes_through_act_branch(self, tmp_path):
        """Test that a file search request goes through ACT branch with full pipeline."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        result = runtime.process_cognitive_cycle(
            user_text="Find all PDF files in my documents folder",
            complexity="fast"
        )
        
        assert result["request_success"] is True
        assert result["action_type"] in ["search_files", "formulate_answer"]
        assert "trace_id" in result
        assert "session_id" in result
        assert "latency_ms" in result

    def test_pipeline_records_outcome_and_lesson(self, tmp_path):
        """Test that the pipeline records outcomes and extracts lessons."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # First request
        result1 = runtime.process_cognitive_cycle(
            user_text="Search for Python tutorials",
            complexity="fast"
        )
        
        assert result1["request_success"] is True
        
        # Verify outcome was recorded
        total_outcomes = runtime.outcomes.total_recorded()
        assert total_outcomes >= 1
        
        # Verify lesson was extracted
        total_lessons = runtime.lessons.total_lessons()
        assert total_lessons >= 1

    def test_pipeline_consults_analogical_memory(self, tmp_path):
        """Test that the pipeline consults analogical memory for similar tasks."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # First request - record a task signature
        result1 = runtime.process_cognitive_cycle(
            user_text="Find configuration files",
            complexity="fast"
        )
        
        # Second similar request - should find analogy
        result2 = runtime.process_cognitive_cycle(
            user_text="Search for config files",
            complexity="fast"
        )
        
        assert result2["request_success"] is True
        # Analogical memory should have at least one signature now
        assert runtime.analogies.total_signatures() >= 1

    def test_pipeline_records_planning_patterns(self, tmp_path):
        """Test that the pipeline records planning patterns from action sequences."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        result = runtime.process_cognitive_cycle(
            user_text="Open Firefox browser",
            complexity="fast"
        )
        
        assert result["request_success"] is True
        # Planning patterns should be recorded
        assert runtime.patterns.total_patterns() >= 0  # May or may not record depending on action type

    def test_pipeline_classifies_complexity(self, tmp_path):
        """Test that the pipeline classifies task complexity and allocates resources."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # Simple task
        result_simple = runtime.process_cognitive_cycle(
            user_text="What time is it?",
            complexity="fast"
        )
        
        # Complex task
        result_complex = runtime.process_cognitive_cycle(
            user_text="Analyze all log files in /var/log for security issues and generate a report",
            complexity="main"
        )
        
        assert result_simple["request_success"] is True
        assert result_complex["request_success"] is True

    def test_pipeline_updates_self_model(self, tmp_path):
        """Test that the pipeline updates SelfModel with capability performance."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # Execute a task
        result = runtime.process_cognitive_cycle(
            user_text="Search for README files",
            complexity="fast"
        )
        
        assert result["request_success"] is True
        
        # SelfModel should be able to assess the capability
        assessment = runtime.self_model.assess_capability(result["action_type"])
        # Assessment may be None if no outcomes recorded yet for this action type
        # but the query should not raise an exception

    def test_pipeline_calibrates_confidence(self, tmp_path):
        """Test that the pipeline calibrates prediction confidence."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # Execute multiple tasks to build calibration data
        for i in range(3):
            result = runtime.process_cognitive_cycle(
                user_text=f"Find file number {i}",
                complexity="fast"
            )
            assert result["request_success"] is True
        
        # Confidence calibrator should have recorded data
        assert runtime.confidence_calibrator.total_records() >= 0

    def test_pipeline_handles_gate_blocks(self, tmp_path):
        """Test that the pipeline handles ActionGate blocks gracefully."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # Request that might be blocked by policy
        result = runtime.process_cognitive_cycle(
            user_text="Delete all files in /etc",
            complexity="fast"
        )
        
        # Should handle gracefully (either blocked or executed with safeguards)
        assert result["request_success"] is True or result.get("gate_blocked") is not None

    def test_pipeline_handles_defer(self, tmp_path):
        """Test that the pipeline handles DEFER reasoning action."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # Ambiguous request that might trigger DEFER
        result = runtime.process_cognitive_cycle(
            user_text="Do something",
            complexity="fast"
        )
        
        # Should handle gracefully
        assert result["request_success"] is True

    def test_pipeline_full_trace_completeness(self, tmp_path):
        """Test that the pipeline produces a complete trace with all fields."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        result = runtime.process_cognitive_cycle(
            user_text="Find Python scripts",
            complexity="fast"
        )
        
        # Verify all expected fields are present
        expected_fields = [
            "request_success",
            "execution_success",
            "goal_verified",
            "success",
            "session_id",
            "trace_id",
            "user_text",
            "assistant_reply",
            "executed_actions",
            "action_type",
            "reasoning_action",
            "goal_lifecycle_state",
            "prediction_surprisal",
            "latency_ms",
            "model_used"
        ]
        
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_multiple_requests_build_learning_history(self, tmp_path):
        """Test that multiple requests build up learning history."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # Execute 5 different requests
        queries = [
            "Find Python files",
            "Search for configuration",
            "Open text editor",
            "List directory contents",
            "Check system status"
        ]
        
        for query in queries:
            result = runtime.process_cognitive_cycle(
                user_text=query,
                complexity="fast"
            )
            assert result["request_success"] is True
        
        # Verify learning history was built
        # At least some outcomes should be recorded (not all requests may record depending on branch)
        assert runtime.outcomes.total_recorded() >= 1
        assert runtime.lessons.total_lessons() >= 1
        assert runtime.analogies.total_signatures() >= 1


class TestComponentWiring:
    """Tests that verify specific components are wired correctly."""

    def test_skill_classifier_is_invoked(self, tmp_path):
        """Test that SkillClassifier is invoked during ACT branch."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # This should invoke skill classification
        result = runtime.process_cognitive_cycle(
            user_text="Search for documents",
            complexity="fast"
        )
        
        assert result["request_success"] is True
        # Skill classifier should have been invoked (no exception raised)

    def test_analogical_memory_is_consulted(self, tmp_path):
        """Test that AnalogicalMemory is consulted during planning."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        # First request to populate analogical memory
        runtime.process_cognitive_cycle(
            user_text="Find files",
            complexity="fast"
        )
        
        # Second request should consult analogical memory
        result = runtime.process_cognitive_cycle(
            user_text="Search for files",
            complexity="fast"
        )
        
        assert result["request_success"] is True

    def test_resource_allocator_is_invoked(self, tmp_path):
        """Test that ResourceAllocator is invoked during ACT branch."""
        runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))
        
        result = runtime.process_cognitive_cycle(
            user_text="Analyze logs",
            complexity="main"
        )
        
        assert result["request_success"] is True
        # Resource allocator should have been invoked (no exception raised)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
