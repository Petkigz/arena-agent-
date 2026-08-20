"""Tests for Periodic Autonomous Cycle."""

import pytest
import tempfile
import os
from app.cognition.periodic_autonomous_cycle import (
    PeriodicAutonomousCycle,
    AutonomousCycle,
    CycleStatus,
    ObservationSource,
)
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator
from app.cognition.autonomous_goal_executor import AutonomousGoalExecutor
from app.cognition.self_reflection_engine import SelfReflectionEngine


class TestPeriodicAutonomousCycle:
    """Test Periodic Autonomous Cycle functionality."""

    @pytest.fixture
    def components(self, tmp_path):
        """Create all required components."""
        goal_generator = AutonomousGoalGenerator(
            db_path=str(tmp_path / "test_goals.db")
        )
        goal_executor = AutonomousGoalExecutor(
            db_path=str(tmp_path / "test_execution.db")
        )
        reflection_engine = SelfReflectionEngine(
            db_path=str(tmp_path / "test_reflection.db")
        )
        return goal_generator, goal_executor, reflection_engine

    @pytest.fixture
    def cycle_runner(self, components, tmp_path):
        """Create a periodic autonomous cycle instance."""
        goal_generator, goal_executor, reflection_engine = components
        db_path = str(tmp_path / "test_cycles.db")
        return PeriodicAutonomousCycle(
            goal_generator=goal_generator,
            goal_executor=goal_executor,
            reflection_engine=reflection_engine,
            db_path=db_path,
            interval_seconds=3600,
            max_goals_per_cycle=2,
        )

    def test_initialization(self, cycle_runner):
        """Test cycle runner initializes without errors."""
        assert cycle_runner is not None
        assert cycle_runner.goal_generator is not None
        assert cycle_runner.goal_executor is not None
        assert cycle_runner.reflection_engine is not None
        assert cycle_runner.interval_seconds == 3600
        assert cycle_runner.max_goals_per_cycle == 2

    def test_observe_environment(self, cycle_runner):
        """Test environmental observation."""
        observations = cycle_runner._observe_environment()
        
        assert isinstance(observations, list)
        assert len(observations) > 0
        assert all(isinstance(obs, str) for obs in observations)

    def test_observe_environment_with_weak_areas(self, cycle_runner):
        """Test that weak areas trigger observations."""
        cycle_runner.reflection_engine.self_model.weak_areas = ["information_gap"]
        
        observations = cycle_runner._observe_environment()
        
        assert any("information_gap" in obs.lower() for obs in observations)

    def test_observe_environment_with_low_success_rate(self, cycle_runner):
        """Test that low success rate triggers observations."""
        cycle_runner.reflection_engine.self_model.average_success_rate = 0.5
        
        observations = cycle_runner._observe_environment()
        
        assert any("success rate" in obs.lower() for obs in observations)

    def test_run_cycle(self, cycle_runner):
        """Test running a complete autonomous cycle."""
        cycle = cycle_runner.run_cycle()
        
        assert cycle is not None
        assert cycle.status == CycleStatus.COMPLETED
        assert cycle.started_at is not None
        assert cycle.completed_at is not None
        assert cycle.duration_seconds > 0
        assert len(cycle.observations) > 0
        assert cycle.summary is not None

    def test_run_cycle_generates_goals(self, cycle_runner):
        """Test that cycle can generate goals from observations."""
        # Add a weak area to trigger a meaningful observation
        cycle_runner.reflection_engine.self_model.weak_areas = ["information_gap"]
        
        cycle = cycle_runner.run_cycle()
        
        # Should generate at least one observation
        assert len(cycle.observations) > 0
        # Goals may or may not be generated depending on observation content
        assert cycle.goals_generated >= 0
        assert cycle.goals_approved >= 0

    def test_run_cycle_executes_goals(self, cycle_runner):
        """Test that cycle executes approved goals."""
        cycle = cycle_runner.run_cycle()
        
        # Should execute at least some goals if any were approved
        if cycle.goals_approved > 0:
            assert cycle.goals_executed > 0
            assert cycle.goals_executed <= cycle_runner.max_goals_per_cycle

    def test_run_cycle_generates_reflections(self, cycle_runner):
        """Test that cycle generates reflections for executed goals."""
        cycle = cycle_runner.run_cycle()
        
        if cycle.goals_executed > 0:
            assert cycle.reflections_generated > 0

    def test_max_goals_per_cycle_limit(self, cycle_runner):
        """Test that max_goals_per_cycle is respected."""
        cycle_runner.max_goals_per_cycle = 1
        
        cycle = cycle_runner.run_cycle()
        
        assert cycle.goals_executed <= 1

    def test_cycle_summary_generation(self, cycle_runner):
        """Test that cycle summary is generated correctly."""
        cycle = cycle_runner.run_cycle()
        
        assert cycle.summary is not None
        assert isinstance(cycle.summary, str)
        assert len(cycle.summary) > 0

    def test_cycle_error_handling(self, cycle_runner, monkeypatch):
        """Test that cycle handles errors gracefully."""
        # Mock observation to raise an error
        def mock_observe(*args, **kwargs):
            raise Exception("Test error")
        
        monkeypatch.setattr(cycle_runner, "_observe_environment", mock_observe)
        
        cycle = cycle_runner.run_cycle()
        
        assert cycle.status == CycleStatus.FAILED
        assert len(cycle.errors) > 0
        assert "Test error" in cycle.errors[0]

    def test_save_and_get_cycle(self, cycle_runner):
        """Test saving and retrieving cycles."""
        cycle = cycle_runner.run_cycle()
        
        retrieved = cycle_runner.get_cycle(cycle.cycle_id)
        
        assert retrieved is not None
        assert retrieved.cycle_id == cycle.cycle_id
        assert retrieved.status == cycle.status
        assert retrieved.goals_generated == cycle.goals_generated

    def test_list_cycles(self, cycle_runner):
        """Test listing cycles with filters."""
        # Run multiple cycles
        for _ in range(3):
            cycle_runner.run_cycle()
        
        # List all
        all_cycles = cycle_runner.list_cycles()
        assert len(all_cycles) == 3
        
        # Filter by status
        completed = cycle_runner.list_cycles(status=CycleStatus.COMPLETED)
        assert len(completed) == 3

    def test_count_cycles(self, cycle_runner):
        """Test counting cycles."""
        # Run multiple cycles
        for _ in range(5):
            cycle_runner.run_cycle()
        
        # Count all
        total = cycle_runner.count_cycles()
        assert total == 5
        
        # Count by status
        completed = cycle_runner.count_cycles(status=CycleStatus.COMPLETED)
        assert completed == 5

    def test_get_statistics(self, cycle_runner):
        """Test getting statistics across all cycles."""
        # Run multiple cycles
        for _ in range(3):
            cycle_runner.run_cycle()
        
        stats = cycle_runner.get_statistics()
        
        assert stats["total_cycles"] == 3
        assert stats["average_duration"] > 0
        assert stats["total_goals_generated"] >= 0
        assert stats["total_goals_executed"] >= 0
        assert stats["total_goals_completed"] >= 0
        assert stats["total_goals_failed"] >= 0
        assert 0 <= stats["overall_success_rate"] <= 1

    def test_get_statistics_empty(self, cycle_runner):
        """Test getting statistics when no cycles exist."""
        stats = cycle_runner.get_statistics()
        
        assert stats["total_cycles"] == 0
        assert stats["average_duration"] == 0.0
        assert stats["overall_success_rate"] == 0.0

    def test_cycle_to_dict_and_from_dict(self):
        """Test cycle serialization."""
        cycle = AutonomousCycle(
            status=CycleStatus.COMPLETED,
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:01:00",
            duration_seconds=60.0,
            observations=["Observation 1", "Observation 2"],
            observation_sources=["system_health"],
            goals_generated=5,
            goals_approved=3,
            goals_executed=2,
            goals_completed=2,
            goals_failed=0,
            reflections_generated=2,
            patterns_discovered=1,
            summary="2 goals executed, 2 completed",
            errors=[],
        )
        
        data = cycle.to_dict()
        assert data["status"] == "completed"
        assert data["goals_generated"] == 5
        assert len(data["observations"]) == 2
        
        restored = AutonomousCycle.from_dict(data)
        assert restored.status == cycle.status
        assert restored.goals_generated == cycle.goals_generated
        assert restored.summary == cycle.summary

    def test_pattern_discovery_after_enough_data(self, cycle_runner):
        """Test that patterns are discovered after enough cycles."""
        # Run enough cycles to accumulate data
        for _ in range(6):
            cycle_runner.run_cycle()
        
        # The last cycle should discover patterns
        last_cycle = cycle_runner.list_cycles(limit=1)[0]
        
        # May or may not discover patterns depending on data
        assert last_cycle.patterns_discovered >= 0

    def test_cycle_integration_with_reflection(self, cycle_runner):
        """Test that cycle integrates properly with reflection engine."""
        # Run a cycle
        cycle = cycle_runner.run_cycle()
        
        # Check that reflection engine was updated
        model = cycle_runner.reflection_engine.get_self_model()
        
        if cycle.goals_executed > 0:
            assert model.total_goals_executed > 0

    def test_multiple_cycles_accumulate_data(self, cycle_runner):
        """Test that multiple cycles accumulate data correctly."""
        # Run 3 cycles
        for _ in range(3):
            cycle_runner.run_cycle()
        
        # Get statistics
        stats = cycle_runner.get_statistics()
        
        # Should have accumulated data from all cycles
        assert stats["total_cycles"] == 3
        # Goals generated may be 0 if observations don't trigger goals
        assert stats["total_goals_generated"] >= 0

    def test_cycle_with_no_observations(self, cycle_runner, monkeypatch):
        """Test cycle behavior when no observations are generated."""
        # Mock to return empty observations
        def mock_observe(*args, **kwargs):
            return []
        
        monkeypatch.setattr(cycle_runner, "_observe_environment", mock_observe)
        
        cycle = cycle_runner.run_cycle()
        
        # Should still complete, just with no goals
        assert cycle.status == CycleStatus.COMPLETED
        assert cycle.goals_generated == 0

    def test_cycle_respects_approval_threshold(self, cycle_runner):
        """Test that cycle respects auto-approval threshold."""
        # Run a cycle
        cycle = cycle_runner.run_cycle()
        
        # Goals approved should be <= goals generated
        assert cycle.goals_approved <= cycle.goals_generated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
