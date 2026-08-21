"""Tests for Autonomous Goal Executor."""

import pytest
import tempfile
import os
from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStatus,
    TaskType,
)
from app.cognition.autonomous_goal_generator import (
    AutonomousGoalGenerator,
    AutonomousGoal,
    GoalSource,
    GoalPriority,
    GoalStatus,
    IntrinsicMotivation,
)


class TestAutonomousGoalExecutor:
    """Test Autonomous Goal Executor functionality."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create a goal executor instance with temporary database."""
        db_path = str(tmp_path / "test_execution.db")
        return AutonomousGoalExecutor(db_path=db_path)

    @pytest.fixture
    def generator(self, tmp_path):
        """Create a goal generator instance with temporary database."""
        db_path = str(tmp_path / "test_goals.db")
        return AutonomousGoalGenerator(db_path=db_path)

    @pytest.fixture
    def sample_goal(self, generator):
        """Create a sample approved goal."""
        goal = AutonomousGoal(
            title="Optimize system performance",
            description="Address performance issue: System running slow",
            source=GoalSource.SYSTEM_OPTIMIZATION,
            motivation=IntrinsicMotivation.COMPETENCE,
            priority=GoalPriority.HIGH,
            status=GoalStatus.APPROVED,
            target_state="System operates efficiently",
            current_state="System running slow",
            success_criteria=["Response time < 1s", "No errors"],
            estimated_effort="high",
            overall_score=0.85,
        )
        generator.add_goal(goal)
        return goal

    def test_initialization(self, executor):
        """Test executor initializes without errors."""
        assert executor is not None
        assert executor.db_path is not None

    def test_create_execution_plan(self, executor, sample_goal):
        """Test creating an execution plan for a goal."""
        plan = executor.create_execution_plan(sample_goal)
        
        assert plan is not None
        assert plan.goal_id == sample_goal.goal_id
        assert plan.goal_title == sample_goal.title
        assert len(plan.steps) > 0
        assert plan.status == ExecutionStatus.PENDING

    def test_generate_steps_for_information_gap(self, executor, generator):
        """Test step generation for information gap goals."""
        goal = AutonomousGoal(
            title="Fill information gap",
            description="Learn about topic X",
            source=GoalSource.INFORMATION_GAP,
            current_state="Missing knowledge",
            success_criteria=["Knowledge acquired"],
        )
        
        plan = executor.create_execution_plan(goal)
        
        # Should have analysis + information gathering + verification steps
        assert len(plan.steps) >= 4
        task_types = [s.task_type for s in plan.steps]
        assert TaskType.ANALYSIS in task_types
        assert TaskType.INFORMATION_GATHERING in task_types

    def test_generate_steps_for_optimization(self, executor, sample_goal):
        """Test step generation for optimization goals."""
        plan = executor.create_execution_plan(sample_goal)
        
        # Should have analysis + optimization + verification steps
        task_types = [s.task_type for s in plan.steps]
        assert TaskType.ANALYSIS in task_types
        assert TaskType.OPTIMIZATION in task_types

    def test_generate_steps_for_maintenance(self, executor):
        """Test step generation for maintenance goals."""
        goal = AutonomousGoal(
            title="Perform maintenance",
            description="Update outdated components",
            source=GoalSource.MAINTENANCE,
            current_state="Outdated components",
            success_criteria=["Components updated"],
        )
        
        plan = executor.create_execution_plan(goal)
        
        task_types = [s.task_type for s in plan.steps]
        assert TaskType.MAINTENANCE in task_types

    def test_execute_step(self, executor, sample_goal):
        """Test executing a single step (no runtime → simulated → UNVERIFIED).

        P0 fix: without a runtime the environment is never verified, so the step
        must NOT be marked COMPLETED — it's UNVERIFIED.
        """
        step = ExecutionStep(
            goal_id=sample_goal.goal_id,
            description="Analyze current state",
            task_type=TaskType.ANALYSIS,
        )
        
        result = executor.execute_step(step)
        
        assert result.status == ExecutionStatus.UNVERIFIED
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.result is not None

    def test_execute_step_failure(self, executor, sample_goal, monkeypatch):
        """Test step execution with failure."""
        step = ExecutionStep(
            goal_id=sample_goal.goal_id,
            description="Failing step",
            task_type=TaskType.ANALYSIS,
        )
        
        # Mock cognitive_runtime to raise an exception
        class MockRuntime:
            def process_cognitive_cycle(self, user_text, complexity):
                raise Exception("Simulated failure")
        
        result = executor.execute_step(step, cognitive_runtime=MockRuntime())
        
        assert result.status == ExecutionStatus.FAILED
        assert result.error is not None
        assert "Simulated failure" in result.error

    def test_execute_plan(self, executor, sample_goal):
        """Test executing an entire plan."""
        plan = executor.create_execution_plan(sample_goal)
        
        result = executor.execute_plan(plan)
        
        assert result.status in [ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL]
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.progress > 0
        assert result.outcome_summary is not None

    def test_execute_plan_progress_tracking(self, executor, sample_goal):
        """Test that plan progress is tracked correctly."""
        plan = executor.create_execution_plan(sample_goal)
        initial_step_count = len(plan.steps)
        
        result = executor.execute_plan(plan)
        
        # Progress should be 1.0 (100%) after all steps are processed.
        assert result.progress == 1.0
        
        # All steps should have reached a terminal state.
        for step in result.steps:
            assert step.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.UNVERIFIED,
                ExecutionStatus.WAITING_APPROVAL,
            ]

    def test_extract_lessons(self, executor, sample_goal):
        """Test lesson extraction from plan execution."""
        plan = executor.create_execution_plan(sample_goal)
        plan = executor.execute_plan(plan)
        
        # Should have at least one lesson
        assert len(plan.lessons_learned) > 0

    def test_execute_next_goal(self, executor, generator, sample_goal):
        """Test executing the next approved goal."""
        plan = executor.execute_next_goal(generator)
        
        assert plan is not None
        assert plan.goal_id == sample_goal.goal_id
        assert plan.status in [ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL, ExecutionStatus.FAILED]
        
        # Verify goal status was updated
        updated_goal = generator.get_goal(sample_goal.goal_id)
        assert updated_goal.status in [GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.DEFERRED]

    def test_execute_next_goal_no_approved(self, executor, generator):
        """Test execute_next_goal when no goals are approved."""
        plan = executor.execute_next_goal(generator)
        assert plan is None

    def test_save_and_get_plan(self, executor, sample_goal):
        """Test saving and retrieving a plan."""
        plan = executor.create_execution_plan(sample_goal)
        
        # Retrieve by plan_id
        retrieved = executor.get_plan(plan.plan_id)
        assert retrieved is not None
        assert retrieved.plan_id == plan.plan_id
        assert retrieved.goal_title == plan.goal_title
        assert len(retrieved.steps) == len(plan.steps)

    def test_get_plan_by_goal(self, executor, sample_goal):
        """Test retrieving a plan by goal ID."""
        plan = executor.create_execution_plan(sample_goal)
        
        retrieved = executor.get_plan_by_goal(sample_goal.goal_id)
        assert retrieved is not None
        assert retrieved.goal_id == sample_goal.goal_id

    def test_list_plans(self, executor):
        """Test listing plans with filters."""
        # Create multiple plans
        for i in range(3):
            goal = AutonomousGoal(
                title=f"Goal {i}",
                description=f"Description {i}",
                source=GoalSource.CURIOSITY,
                status=GoalStatus.APPROVED,
            )
            plan = executor.create_execution_plan(goal)
            plan.status = ExecutionStatus.COMPLETED if i < 2 else ExecutionStatus.FAILED
            executor.save_plan(plan)
        
        # List all
        all_plans = executor.list_plans()
        assert len(all_plans) == 3
        
        # Filter by status
        completed = executor.list_plans(status=ExecutionStatus.COMPLETED)
        assert len(completed) == 2
        
        failed = executor.list_plans(status=ExecutionStatus.FAILED)
        assert len(failed) == 1

    def test_count_plans(self, executor):
        """Test counting plans."""
        # Create plans with different statuses
        for i in range(5):
            goal = AutonomousGoal(
                title=f"Goal {i}",
                description=f"Description {i}",
                source=GoalSource.CURIOSITY,
            )
            plan = executor.create_execution_plan(goal)
            plan.status = ExecutionStatus.COMPLETED if i < 3 else ExecutionStatus.FAILED
            executor.save_plan(plan)
        
        # Count all
        total = executor.count_plans()
        assert total == 5
        
        # Count by status
        completed = executor.count_plans(status=ExecutionStatus.COMPLETED)
        assert completed == 3
        
        failed = executor.count_plans(status=ExecutionStatus.FAILED)
        assert failed == 2

    def test_plan_to_dict_and_from_dict(self):
        """Test plan serialization."""
        plan = ExecutionPlan(
            goal_id="goal_123",
            goal_title="Test Goal",
            steps=[
                ExecutionStep(
                    goal_id="goal_123",
                    description="Step 1",
                    task_type=TaskType.ANALYSIS,
                    status=ExecutionStatus.COMPLETED,
                    result="Done",
                    confidence=0.9,
                ),
                ExecutionStep(
                    goal_id="goal_123",
                    description="Step 2",
                    task_type=TaskType.OPTIMIZATION,
                    status=ExecutionStatus.PENDING,
                ),
            ],
            status=ExecutionStatus.IN_PROGRESS,
            progress=0.5,
            outcome_summary="In progress",
            lessons_learned=["Lesson 1", "Lesson 2"],
        )
        
        # Convert to dict
        data = plan.to_dict()
        assert data["goal_id"] == "goal_123"
        assert len(data["steps"]) == 2
        assert data["progress"] == 0.5
        
        # Convert back
        restored = ExecutionPlan.from_dict(data)
        assert restored.goal_id == plan.goal_id
        assert len(restored.steps) == 2
        assert restored.steps[0].status == ExecutionStatus.COMPLETED
        assert restored.lessons_learned == ["Lesson 1", "Lesson 2"]

    def test_step_to_dict_and_from_dict(self):
        """Test step serialization."""
        step = ExecutionStep(
            goal_id="goal_123",
            description="Test step",
            task_type=TaskType.ANALYSIS,
            status=ExecutionStatus.COMPLETED,
            result="Success",
            confidence=0.85,
        )
        
        # Convert to dict
        data = step.to_dict()
        assert data["description"] == "Test step"
        assert data["task_type"] == "analysis"
        assert data["confidence"] == 0.85
        
        # Convert back
        restored = ExecutionStep.from_dict(data)
        assert restored.description == step.description
        assert restored.task_type == TaskType.ANALYSIS
        assert restored.confidence == 0.85

    def test_full_workflow(self, executor, generator):
        """Test the full workflow: generate → approve → execute."""
        # Generate a goal from an observation
        observation = "System response time is slow"
        goals = generator.generate_goals_from_observation(observation)
        assert len(goals) > 0
        
        # Evaluate and approve
        goal = goals[0]
        generator.evaluate_goal(goal)
        approved = generator.approve_goal(goal.goal_id, auto_approve_threshold=0.5)
        assert approved
        
        # Execute
        plan = executor.execute_next_goal(generator)
        assert plan is not None
        assert plan.status in [ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL, ExecutionStatus.FAILED]
        
        # Verify goal status updated
        updated_goal = generator.get_goal(goal.goal_id)
        assert updated_goal.status in [GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.DEFERRED]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
