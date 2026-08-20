"""Tests for Autonomous Goal Generator."""

import pytest
import tempfile
import os
from app.cognition.autonomous_goal_generator import (
    AutonomousGoalGenerator,
    AutonomousGoal,
    GoalSource,
    GoalPriority,
    GoalStatus,
    IntrinsicMotivation,
)


class TestAutonomousGoalGenerator:
    """Test Autonomous Goal Generator functionality."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create a goal generator instance with temporary database."""
        db_path = str(tmp_path / "test_autonomous_goals.db")
        return AutonomousGoalGenerator(db_path=db_path)

    def test_initialization(self, generator):
        """Test generator initializes without errors."""
        assert generator is not None
        assert generator.db_path is not None

    def test_generate_goals_from_observation(self, generator):
        """Test goal generation from observations."""
        # Information gap
        observation = "Unknown system behavior detected"
        goals = generator.generate_goals_from_observation(observation)
        assert len(goals) > 0
        assert any(g.source == GoalSource.INFORMATION_GAP for g in goals)
        
        # Optimization
        observation = "System running slow with errors"
        goals = generator.generate_goals_from_observation(observation)
        assert len(goals) > 0
        assert any(g.source == GoalSource.SYSTEM_OPTIMIZATION for g in goals)
        
        # Maintenance
        observation = "Outdated knowledge base entries"
        goals = generator.generate_goals_from_observation(observation)
        assert len(goals) > 0
        assert any(g.source == GoalSource.MAINTENANCE for g in goals)

    def test_create_information_gap_goal(self, generator):
        """Test information gap goal creation."""
        observation = "Missing documentation for feature X"
        goals = generator.generate_goals_from_observation(observation)
        
        info_goals = [g for g in goals if g.source == GoalSource.INFORMATION_GAP]
        assert len(info_goals) > 0
        
        goal = info_goals[0]
        assert goal.motivation == IntrinsicMotivation.CURIOSITY
        assert "missing" in goal.current_state.lower()
        assert len(goal.success_criteria) > 0

    def test_create_optimization_goal(self, generator):
        """Test optimization goal creation."""
        observation = "Response time slow for complex queries"
        goals = generator.generate_goals_from_observation(observation)
        
        opt_goals = [g for g in goals if g.source == GoalSource.SYSTEM_OPTIMIZATION]
        assert len(opt_goals) > 0
        
        goal = opt_goals[0]
        assert goal.motivation == IntrinsicMotivation.COMPETENCE
        assert goal.priority == GoalPriority.HIGH
        assert goal.value_score > 0.8

    def test_evaluate_goal(self, generator):
        """Test goal evaluation."""
        goal = AutonomousGoal(
            title="Test goal",
            description="Test description",
            source=GoalSource.INFORMATION_GAP,
            priority=GoalPriority.NORMAL,
            estimated_effort="medium"
        )
        
        evaluated = generator.evaluate_goal(goal)
        
        assert evaluated.feasibility_score > 0
        assert evaluated.value_score > 0
        assert evaluated.urgency_score > 0
        assert evaluated.overall_score > 0
        assert evaluated.status == GoalStatus.EVALUATED
        assert evaluated.evaluated_at is not None

    def test_approve_goal(self, generator):
        """Test goal approval."""
        # Create and add a goal
        goal = AutonomousGoal(
            title="Test goal",
            description="Test description",
            source=GoalSource.INFORMATION_GAP,
            overall_score=0.8
        )
        generator.add_goal(goal)
        
        # Approve it
        approved = generator.approve_goal(goal.goal_id, auto_approve_threshold=0.7)
        assert approved
        
        # Verify status
        retrieved = generator.get_goal(goal.goal_id)
        assert retrieved.status == GoalStatus.APPROVED
        assert retrieved.approved_at is not None

    def test_approve_goal_below_threshold(self, generator):
        """Test goal rejection when below threshold."""
        goal = AutonomousGoal(
            title="Low priority goal",
            description="Test description",
            source=GoalSource.CURIOSITY,
            overall_score=0.3
        )
        generator.add_goal(goal)
        
        # Try to approve with high threshold
        approved = generator.approve_goal(goal.goal_id, auto_approve_threshold=0.7)
        assert not approved
        
        # Verify status unchanged
        retrieved = generator.get_goal(goal.goal_id)
        assert retrieved.status != GoalStatus.APPROVED

    def test_get_next_goal(self, generator):
        """Test getting the next goal for execution."""
        # Add multiple approved goals with different scores
        goal1 = AutonomousGoal(
            title="High priority",
            description="Test",
            source=GoalSource.SYSTEM_OPTIMIZATION,
            status=GoalStatus.APPROVED,
            overall_score=0.9
        )
        goal2 = AutonomousGoal(
            title="Low priority",
            description="Test",
            source=GoalSource.CURIOSITY,
            status=GoalStatus.APPROVED,
            overall_score=0.5
        )
        goal3 = AutonomousGoal(
            title="Not approved",
            description="Test",
            source=GoalSource.INFORMATION_GAP,
            status=GoalStatus.PROPOSED,
            overall_score=1.0
        )
        
        generator.add_goal(goal1)
        generator.add_goal(goal2)
        generator.add_goal(goal3)
        
        # Should get highest-scored approved goal
        next_goal = generator.get_next_goal()
        assert next_goal is not None
        assert next_goal.goal_id == goal1.goal_id
        assert next_goal.status == GoalStatus.APPROVED

    def test_add_and_get_goal(self, generator):
        """Test adding and retrieving goals."""
        goal = AutonomousGoal(
            title="Test goal",
            description="Test description",
            source=GoalSource.CURIOSITY,
            priority=GoalPriority.HIGH
        )
        
        success = generator.add_goal(goal)
        assert success
        
        retrieved = generator.get_goal(goal.goal_id)
        assert retrieved is not None
        assert retrieved.title == "Test goal"
        assert retrieved.source == GoalSource.CURIOSITY
        assert retrieved.priority == GoalPriority.HIGH

    def test_list_goals(self, generator):
        """Test listing goals with filters."""
        # Add various goals
        goal1 = AutonomousGoal(
            title="Goal 1",
            description="Test",
            source=GoalSource.INFORMATION_GAP,
            status=GoalStatus.PROPOSED,
            overall_score=0.8
        )
        goal2 = AutonomousGoal(
            title="Goal 2",
            description="Test",
            source=GoalSource.CURIOSITY,
            status=GoalStatus.APPROVED,
            overall_score=0.6
        )
        goal3 = AutonomousGoal(
            title="Goal 3",
            description="Test",
            source=GoalSource.INFORMATION_GAP,
            status=GoalStatus.APPROVED,
            overall_score=0.9
        )
        
        generator.add_goal(goal1)
        generator.add_goal(goal2)
        generator.add_goal(goal3)
        
        # List all
        all_goals = generator.list_goals()
        assert len(all_goals) == 3
        
        # Filter by status
        approved = generator.list_goals(status=GoalStatus.APPROVED)
        assert len(approved) == 2
        
        # Filter by source
        info_gaps = generator.list_goals(source=GoalSource.INFORMATION_GAP)
        assert len(info_gaps) == 2
        
        # Combined filter
        approved_info = generator.list_goals(
            status=GoalStatus.APPROVED,
            source=GoalSource.INFORMATION_GAP
        )
        assert len(approved_info) == 1
        assert approved_info[0].goal_id == goal3.goal_id

    def test_count_goals(self, generator):
        """Test counting goals."""
        # Add goals with different statuses
        for i in range(5):
            goal = AutonomousGoal(
                title=f"Goal {i}",
                description="Test",
                source=GoalSource.CURIOSITY,
                status=GoalStatus.PROPOSED if i < 3 else GoalStatus.APPROVED
            )
            generator.add_goal(goal)
        
        # Count all
        total = generator.count_goals()
        assert total == 5
        
        # Count by status
        proposed = generator.count_goals(status=GoalStatus.PROPOSED)
        assert proposed == 3
        
        approved = generator.count_goals(status=GoalStatus.APPROVED)
        assert approved == 2

    def test_update_goal(self, generator):
        """Test updating a goal."""
        goal = AutonomousGoal(
            title="Original title",
            description="Original description",
            source=GoalSource.CURIOSITY,
            status=GoalStatus.PROPOSED
        )
        generator.add_goal(goal)
        
        # Update the goal
        goal.title = "Updated title"
        goal.status = GoalStatus.APPROVED
        generator.update_goal(goal)
        
        # Verify update
        retrieved = generator.get_goal(goal.goal_id)
        assert retrieved.title == "Updated title"
        assert retrieved.status == GoalStatus.APPROVED

    def test_goal_to_dict_and_from_dict(self):
        """Test goal serialization and deserialization."""
        goal = AutonomousGoal(
            title="Test goal",
            description="Test description",
            source=GoalSource.SYSTEM_OPTIMIZATION,
            motivation=IntrinsicMotivation.COMPETENCE,
            priority=GoalPriority.HIGH,
            status=GoalStatus.EVALUATED,
            target_state="Optimized state",
            current_state="Current state",
            success_criteria=["Criterion 1", "Criterion 2"],
            estimated_effort="high",
            feasibility_score=0.7,
            value_score=0.9,
            urgency_score=0.8,
            overall_score=0.8
        )
        
        # Convert to dict
        data = goal.to_dict()
        assert data["title"] == "Test goal"
        assert data["source"] == "system_optimization"
        assert data["success_criteria"] == ["Criterion 1", "Criterion 2"]
        
        # Convert back
        restored = AutonomousGoal.from_dict(data)
        assert restored.title == goal.title
        assert restored.source == goal.source
        assert restored.success_criteria == goal.success_criteria
        assert restored.overall_score == goal.overall_score

    def test_multiple_observations_generate_multiple_goals(self, generator):
        """Test that multiple observations can generate multiple goals."""
        observations = [
            "Unknown behavior detected",
            "System running slow",
            "Outdated knowledge base",
        ]
        
        all_goals = []
        for obs in observations:
            goals = generator.generate_goals_from_observation(obs)
            all_goals.extend(goals)
        
        assert len(all_goals) >= 3  # At least one goal per observation
        
        # Verify all goals were saved
        total = generator.count_goals()
        assert total >= 3

    def test_goal_prioritization(self, generator):
        """Test that goals are prioritized correctly."""
        # Create goals with different sources
        goals_data = [
            (GoalSource.SYSTEM_OPTIMIZATION, GoalPriority.HIGH),
            (GoalSource.INFORMATION_GAP, GoalPriority.NORMAL),
            (GoalSource.CURIOSITY, GoalPriority.LOW),
        ]
        
        for source, priority in goals_data:
            goal = AutonomousGoal(
                title=f"Goal from {source.value}",
                description="Test",
                source=source,
                priority=priority,
                status=GoalStatus.PROPOSED
            )
            generator.add_goal(goal)
            generator.evaluate_goal(goal)
        
        # Get all evaluated goals
        evaluated = generator.list_goals(status=GoalStatus.EVALUATED)
        
        # Verify scores are reasonable
        for goal in evaluated:
            assert goal.feasibility_score > 0
            assert goal.value_score > 0
            assert goal.overall_score > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
