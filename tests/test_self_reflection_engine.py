"""Tests for Self-Reflection Engine."""

import pytest
import tempfile
import os
from app.cognition.self_reflection_engine import (
    SelfReflectionEngine,
    SelfReflection,
    ExecutionPattern,
    SelfModel,
    ReflectionType,
)
from app.cognition.autonomous_goal_generator import (
    AutonomousGoalGenerator,
    AutonomousGoal,
    GoalSource,
    GoalStatus,
)
from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStatus,
    TaskType,
)


def _mark_completed(goal_executor, plan):
    """Explicitly mark a plan (and its steps) as VERIFIED complete.

    This replaces the old pattern of relying on `execute_plan(plan)` with no
    runtime — which used to (incorrectly) mark simulated steps COMPLETED. After
    the P0 fix, no-runtime steps are UNVERIFIED, so tests that need a
    "successful" plan must construct one explicitly.
    """
    for s in plan.steps:
        s.status = ExecutionStatus.COMPLETED
        s.confidence = 0.9
        s.result = "verified"
    plan.status = ExecutionStatus.COMPLETED
    plan.progress = 1.0
    plan.outcome_summary = "All steps verified complete"
    goal_executor.save_plan(plan)
    return plan


class TestSelfReflectionEngine:
    """Test Self-Reflection Engine functionality."""

    @pytest.fixture
    def reflection_engine(self, tmp_path):
        """Create a self-reflection engine instance."""
        db_path = str(tmp_path / "test_reflection.db")
        return SelfReflectionEngine(db_path=db_path)

    @pytest.fixture
    def goal_generator(self, tmp_path):
        """Create a goal generator instance."""
        db_path = str(tmp_path / "test_goals.db")
        return AutonomousGoalGenerator(db_path=db_path)

    @pytest.fixture
    def goal_executor(self, tmp_path):
        """Create a goal executor instance."""
        db_path = str(tmp_path / "test_execution.db")
        return AutonomousGoalExecutor(db_path=db_path)

    @pytest.fixture
    def sample_plan(self, goal_executor):
        """Create a sample completed (verified) execution plan."""
        goal = AutonomousGoal(
            title="Optimize system performance",
            description="Address slow response times",
            source=GoalSource.SYSTEM_OPTIMIZATION,
            status=GoalStatus.APPROVED,
        )
        plan = goal_executor.create_execution_plan(goal)
        plan = _mark_completed(goal_executor, plan)
        return plan, goal

    @pytest.fixture
    def sample_failed_plan(self, goal_executor):
        """Create a sample failed execution plan."""
        goal = AutonomousGoal(
            title="Fill information gap",
            description="Learn about missing topic",
            source=GoalSource.INFORMATION_GAP,
            status=GoalStatus.APPROVED,
        )
        plan = goal_executor.create_execution_plan(goal)
        # Simulate failure
        plan.status = ExecutionStatus.FAILED
        plan.steps[0].status = ExecutionStatus.FAILED
        plan.steps[0].error = "Test failure"
        plan.outcome_summary = "1 step failed"
        goal_executor.save_plan(plan)
        return plan, goal

    def test_initialization(self, reflection_engine):
        """Test reflection engine initializes without errors."""
        assert reflection_engine is not None
        assert reflection_engine.db_path is not None
        assert reflection_engine.self_model is not None

    def test_reflect_on_successful_execution(self, reflection_engine, sample_plan):
        """Test reflection on a successful execution."""
        plan, goal = sample_plan
        
        reflections = reflection_engine.reflect_on_execution(plan, goal)
        
        assert len(reflections) > 0
        assert reflections[0].reflection_type == ReflectionType.SUCCESS_ANALYSIS
        assert reflections[0].confidence > 0
        assert len(reflections[0].evidence) > 0

    def test_reflect_on_failed_execution(self, reflection_engine, sample_failed_plan):
        """Test reflection on a failed execution."""
        plan, goal = sample_failed_plan
        
        reflections = reflection_engine.reflect_on_execution(plan, goal)
        
        assert len(reflections) > 0
        assert reflections[0].reflection_type == ReflectionType.FAILURE_ANALYSIS
        assert reflections[0].actionable is True
        assert "failure" in reflections[0].insight.lower()

    def test_self_model_updates_on_success(self, reflection_engine, sample_plan):
        """Test that self-model updates after successful execution."""
        plan, goal = sample_plan
        
        initial_executed = reflection_engine.self_model.total_goals_executed
        initial_completed = reflection_engine.self_model.total_goals_completed
        
        reflection_engine.reflect_on_execution(plan, goal)
        
        assert reflection_engine.self_model.total_goals_executed == initial_executed + 1
        assert reflection_engine.self_model.total_goals_completed == initial_completed + 1

    def test_self_model_updates_on_failure(self, reflection_engine, sample_failed_plan):
        """Test that self-model updates after failed execution."""
        plan, goal = sample_failed_plan
        
        initial_executed = reflection_engine.self_model.total_goals_executed
        initial_failed = reflection_engine.self_model.total_goals_failed
        
        reflection_engine.reflect_on_execution(plan, goal)
        
        assert reflection_engine.self_model.total_goals_executed == initial_executed + 1
        assert reflection_engine.self_model.total_goals_failed == initial_failed + 1

    def test_success_rate_calculation(self, reflection_engine, goal_executor):
        """Test that success rate is calculated correctly."""
        # Create 3 goals: 2 completed, 1 failed
        for i in range(3):
            goal = AutonomousGoal(
                title=f"Goal {i}",
                description=f"Description {i}",
                source=GoalSource.CURIOSITY,
                status=GoalStatus.APPROVED,
            )
            plan = goal_executor.create_execution_plan(goal)
            
            if i < 2:
                plan = _mark_completed(goal_executor, plan)
            else:
                plan.status = ExecutionStatus.FAILED
                goal_executor.save_plan(plan)
            
            reflection_engine.reflect_on_execution(plan, goal)
        
        # 2/3 = 66.7%
        assert abs(reflection_engine.self_model.average_success_rate - 0.667) < 0.01

    def test_discover_patterns(self, reflection_engine, goal_executor):
        """Test pattern discovery across multiple plans."""
        # Create multiple plans
        plans = []
        for i in range(5):
            goal = AutonomousGoal(
                title=f"System optimization {i}",
                description=f"Optimize {i}",
                source=GoalSource.SYSTEM_OPTIMIZATION,
                status=GoalStatus.APPROVED,
            )
            plan = goal_executor.create_execution_plan(goal)
            plan = _mark_completed(goal_executor, plan)
            plans.append(plan)
        
        # Discover patterns
        patterns = reflection_engine.discover_patterns(plans)
        
        assert len(patterns) > 0
        pattern = patterns[0]
        assert pattern.goal_source == "system_optimization"
        assert pattern.sample_size == 5
        assert pattern.success_rate > 0

    def test_pattern_statistics(self, reflection_engine, goal_executor):
        """Test that pattern statistics are calculated correctly."""
        plans = []
        for i in range(3):
            goal = AutonomousGoal(
                title=f"Maintenance task {i}",
                description=f"Maintain {i}",
                source=GoalSource.MAINTENANCE,
                status=GoalStatus.APPROVED,
            )
            plan = goal_executor.create_execution_plan(goal)
            plan = _mark_completed(goal_executor, plan)
            plans.append(plan)
        
        patterns = reflection_engine.discover_patterns(plans)
        
        assert len(patterns) > 0
        pattern = patterns[0]
        assert pattern.average_steps > 0
        assert pattern.average_confidence > 0

    def test_get_recommendations(self, reflection_engine, goal_executor):
        """Test getting recommendations based on performance."""
        # Create some failed plans to trigger recommendations
        for i in range(3):
            goal = AutonomousGoal(
                title=f"Curiosity exploration {i}",
                description=f"Explore {i}",
                source=GoalSource.CURIOSITY,
                status=GoalStatus.APPROVED,
            )
            plan = goal_executor.create_execution_plan(goal)
            plan.status = ExecutionStatus.FAILED
            goal_executor.save_plan(plan)
            reflection_engine.reflect_on_execution(plan, goal)
        
        recommendations = reflection_engine.get_recommendations()
        
        assert len(recommendations) > 0
        assert any("weak" in r.lower() or "success" in r.lower() for r in recommendations)

    def test_adjust_goal_generation(self, reflection_engine, goal_generator):
        """Test adjusting goal generation based on reflections."""
        # Add some weak areas
        reflection_engine.self_model.weak_areas = ["information_gap", "curiosity"]
        
        # Should not raise an error
        reflection_engine.adjust_goal_generation(goal_generator)

    def test_save_and_list_reflections(self, reflection_engine):
        """Test saving and listing reflections."""
        reflection1 = SelfReflection(
            reflection_type=ReflectionType.SUCCESS_ANALYSIS,
            insight="Test insight 1",
            evidence=["Evidence 1"],
            confidence=0.8,
            actionable=False,
        )
        reflection2 = SelfReflection(
            reflection_type=ReflectionType.FAILURE_ANALYSIS,
            insight="Test insight 2",
            evidence=["Evidence 2"],
            confidence=0.9,
            actionable=True,
        )
        
        reflection_engine._save_reflection(reflection1)
        reflection_engine._save_reflection(reflection2)
        
        # List all
        all_reflections = reflection_engine.list_reflections()
        assert len(all_reflections) == 2
        
        # Filter by type
        success_only = reflection_engine.list_reflections(reflection_type=ReflectionType.SUCCESS_ANALYSIS)
        assert len(success_only) == 1
        assert success_only[0].insight == "Test insight 1"

    def test_save_and_list_patterns(self, reflection_engine):
        """Test saving and listing patterns."""
        pattern1 = ExecutionPattern(
            goal_source="system_optimization",
            success_rate=0.8,
            average_steps=5,
            average_confidence=0.85,
            sample_size=10,
        )
        pattern2 = ExecutionPattern(
            goal_source="information_gap",
            success_rate=0.6,
            average_steps=4,
            average_confidence=0.7,
            sample_size=8,
        )
        
        reflection_engine._save_pattern(pattern1)
        reflection_engine._save_pattern(pattern2)
        
        patterns = reflection_engine.list_patterns()
        assert len(patterns) == 2

    def test_get_self_model(self, reflection_engine):
        """Test getting the self-model."""
        model = reflection_engine.get_self_model()
        
        assert isinstance(model, SelfModel)
        assert model.total_goals_executed == 0
        assert model.average_success_rate == 0.0

    def test_self_model_persistence(self, tmp_path):
        """Test that self-model persists across instances."""
        db_path = str(tmp_path / "test_persistence.db")
        
        # Create first instance and update model
        engine1 = SelfReflectionEngine(db_path=db_path)
        engine1.self_model.total_goals_executed = 10
        engine1.self_model.total_goals_completed = 8
        engine1.self_model.average_success_rate = 0.8
        engine1.self_model.strong_areas = ["system_optimization"]
        engine1._save_self_model()
        
        # Create second instance and verify persistence
        engine2 = SelfReflectionEngine(db_path=db_path)
        assert engine2.self_model.total_goals_executed == 10
        assert engine2.self_model.total_goals_completed == 8
        assert engine2.self_model.average_success_rate == 0.8
        assert "system_optimization" in engine2.self_model.strong_areas

    def test_reflection_to_dict_and_from_dict(self):
        """Test reflection serialization."""
        reflection = SelfReflection(
            reflection_type=ReflectionType.SUCCESS_ANALYSIS,
            insight="Test insight",
            evidence=["Evidence 1", "Evidence 2"],
            confidence=0.85,
            actionable=True,
            action_taken="Adjusted threshold",
        )
        
        data = reflection.to_dict()
        assert data["insight"] == "Test insight"
        assert data["confidence"] == 0.85
        assert len(data["evidence"]) == 2
        
        restored = SelfReflection.from_dict(data)
        assert restored.insight == reflection.insight
        assert restored.confidence == reflection.confidence
        assert restored.actionable == reflection.actionable

    def test_pattern_to_dict_and_from_dict(self):
        """Test pattern serialization."""
        pattern = ExecutionPattern(
            goal_source="system_optimization",
            success_rate=0.75,
            average_steps=6,
            average_confidence=0.8,
            common_failure_reasons=["timeout", "permission_denied"],
            recommended_actions=["Increase timeout", "Check permissions"],
            sample_size=20,
        )
        
        data = pattern.to_dict()
        assert data["goal_source"] == "system_optimization"
        assert data["success_rate"] == 0.75
        assert len(data["common_failure_reasons"]) == 2
        
        restored = ExecutionPattern.from_dict(data)
        assert restored.goal_source == pattern.goal_source
        assert restored.success_rate == pattern.success_rate
        assert restored.sample_size == pattern.sample_size


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
