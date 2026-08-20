"""
Tests for Phase 18: Metacognitive Monitoring
"""

import pytest
import tempfile
import time
from app.cognition.metacognitive_monitor import (
    MetacognitiveMonitor,
    CognitiveProcess,
    CognitiveProcessType,
    CognitiveState,
    ErrorType,
    OptimizationStrategy,
    CognitiveInsight,
    CognitiveStrategy
)


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    import os
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def monitor(temp_db):
    """Create a MetacognitiveMonitor instance."""
    return MetacognitiveMonitor(db_path=temp_db)


class TestMetacognitiveMonitor:
    """Test suite for MetacognitiveMonitor."""
    
    def test_initialization(self, monitor):
        """Test monitor initialization."""
        assert monitor is not None
        assert len(monitor.strategies) > 0  # Should have default strategies
    
    def test_start_process(self, monitor):
        """Test starting a cognitive process."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.REASONING,
            description="Test reasoning process",
            total_steps=5
        )
        
        assert process_id is not None
        assert process_id in monitor.processes
        
        process = monitor.get_process(process_id)
        assert process is not None
        assert process.process_type == CognitiveProcessType.REASONING
        assert process.description == "Test reasoning process"
        assert process.total_steps == 5
        assert process.state == CognitiveState.RUNNING
        assert process.steps_completed == 0
    
    def test_update_process(self, monitor):
        """Test updating a cognitive process."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.PLANNING,
            description="Test planning",
            total_steps=10
        )
        
        # Update process
        monitor.update_process(
            process_id=process_id,
            steps_completed=5,
            confidence_level=0.7,
            resource_usage={"cpu": 0.5, "memory": 0.3},
            intermediate_result="Step 5 result"
        )
        
        process = monitor.get_process(process_id)
        assert process.steps_completed == 5
        assert process.confidence_level == 0.7
        assert process.resource_usage["cpu"] == 0.5
        assert len(process.intermediate_results) == 1
        assert process.intermediate_results[0] == "Step 5 result"
    
    def test_complete_process(self, monitor):
        """Test completing a cognitive process."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.PROBLEM_SOLVING,
            description="Test problem solving"
        )
        
        monitor.update_process(process_id, steps_completed=3, confidence_level=0.8)
        monitor.complete_process(process_id, state=CognitiveState.COMPLETED)
        
        process = monitor.get_process(process_id)
        assert process.state == CognitiveState.COMPLETED
        assert process.end_time is not None
        assert process.duration > 0
    
    def test_process_duration(self, monitor):
        """Test process duration calculation."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.REASONING,
            description="Test duration"
        )
        
        time.sleep(0.1)  # Small delay
        
        process = monitor.get_process(process_id)
        assert process.duration >= 0.1
        
        monitor.complete_process(process_id)
        
        process = monitor.get_process(process_id)
        assert process.duration >= 0.1
    
    def test_process_progress(self, monitor):
        """Test process progress calculation."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.PLANNING,
            description="Test progress",
            total_steps=10
        )
        
        process = monitor.get_process(process_id)
        assert process.progress == 0.0
        
        monitor.update_process(process_id, steps_completed=5)
        process = monitor.get_process(process_id)
        assert process.progress == 0.5
        
        monitor.update_process(process_id, steps_completed=10)
        process = monitor.get_process(process_id)
        assert process.progress == 1.0
    
    def test_process_efficiency_score(self, monitor):
        """Test process efficiency score calculation."""
        # High efficiency process
        process_id1 = monitor.start_process(
            process_type=CognitiveProcessType.REASONING,
            description="High efficiency"
        )
        monitor.update_process(process_id1, confidence_level=0.9, steps_completed=5)
        monitor.complete_process(process_id1)
        
        process1 = monitor.get_process(process_id1)
        assert process1.efficiency_score > 0.7
        
        # Low efficiency process
        process_id2 = monitor.start_process(
            process_type=CognitiveProcessType.REASONING,
            description="Low efficiency"
        )
        monitor.update_process(process_id2, confidence_level=0.3, steps_completed=1)
        monitor.detect_error(process_id2, ErrorType.LOGICAL_FALLACY, "Test error")
        monitor.complete_process(process_id2)
        
        process2 = monitor.get_process(process_id2)
        assert process2.efficiency_score < process1.efficiency_score
    
    def test_detect_error(self, monitor):
        """Test error detection."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.REASONING,
            description="Test error detection"
        )
        
        monitor.detect_error(
            process_id=process_id,
            error_type=ErrorType.BIAS,
            description="Confirmation bias detected"
        )
        
        process = monitor.get_process(process_id)
        assert ErrorType.BIAS in process.errors_detected
        
        # Check that an insight was generated
        assert len(monitor.insights) > 0
        insight = monitor.insights[-1]
        assert insight.insight_type == "error"
        assert "bias" in insight.description.lower()
        assert insight.actionable
        assert len(insight.recommended_actions) > 0
    
    def test_suggest_optimization(self, monitor):
        """Test optimization suggestions."""
        process_id = monitor.start_process(
            process_type=CognitiveProcessType.PROBLEM_SOLVING,
            description="Test optimization"
        )
        
        monitor.suggest_optimization(
            process_id=process_id,
            strategy=OptimizationStrategy.DECOMPOSE,
            reason="Problem is too complex"
        )
        
        process = monitor.get_process(process_id)
        assert OptimizationStrategy.DECOMPOSE in process.optimization_suggestions
        
        # Check that an insight was generated
        assert len(monitor.insights) > 0
        insight = monitor.insights[-1]
        assert insight.insight_type == "optimization"
        assert "decompose" in insight.description.lower()
    
    def test_get_active_processes(self, monitor):
        """Test getting active processes."""
        # Start multiple processes
        id1 = monitor.start_process(CognitiveProcessType.REASONING, "Process 1")
        id2 = monitor.start_process(CognitiveProcessType.PLANNING, "Process 2")
        id3 = monitor.start_process(CognitiveProcessType.LEARNING, "Process 3")
        
        # Complete one
        monitor.complete_process(id2)
        
        # Get active processes
        active = monitor.get_active_processes()
        assert len(active) == 2
        
        active_ids = [p.process_id for p in active]
        assert id1 in active_ids
        assert id3 in active_ids
        assert id2 not in active_ids
    
    def test_get_process_history(self, monitor):
        """Test getting process history."""
        # Create several processes
        for i in range(5):
            process_id = monitor.start_process(
                CognitiveProcessType.REASONING,
                f"Process {i}"
            )
            monitor.complete_process(process_id)
        
        # Get history
        history = monitor.get_process_history(limit=3)
        assert len(history) == 3
        
        # Check that they're in reverse chronological order
        assert history[0].start_time >= history[1].start_time
        assert history[1].start_time >= history[2].start_time
        
        # Filter by type
        monitor.start_process(CognitiveProcessType.PLANNING, "Planning process")
        history = monitor.get_process_history(
            process_type=CognitiveProcessType.REASONING,
            limit=10
        )
        assert all(p.process_type == CognitiveProcessType.REASONING for p in history)
    
    def test_get_insights(self, monitor):
        """Test getting insights."""
        # Create a process with errors
        process_id = monitor.start_process(
            CognitiveProcessType.REASONING,
            "Test process"
        )
        monitor.detect_error(process_id, ErrorType.BIAS, "Test bias")
        monitor.detect_error(process_id, ErrorType.INCONSISTENCY, "Test inconsistency")
        monitor.complete_process(process_id)
        
        # Get insights
        insights = monitor.get_insights(limit=10)
        assert len(insights) >= 2  # At least the error insights
        
        # Filter by type
        error_insights = monitor.get_insights(insight_type="error", limit=10)
        assert all(i.insight_type == "error" for i in error_insights)
        
        # Filter by process type
        reasoning_insights = monitor.get_insights(
            process_type=CognitiveProcessType.REASONING,
            limit=10
        )
        assert all(i.process_type == CognitiveProcessType.REASONING for i in reasoning_insights)
    
    def test_recommend_strategy(self, monitor):
        """Test strategy recommendation."""
        # Recommend strategy for problem solving
        strategy = monitor.recommend_strategy(
            process_type=CognitiveProcessType.PROBLEM_SOLVING,
            context={}
        )
        
        assert strategy is not None
        assert CognitiveProcessType.PROBLEM_SOLVING in strategy.applicable_to
        
        # Recommend strategy for creativity
        strategy = monitor.recommend_strategy(
            process_type=CognitiveProcessType.CREATIVITY,
            context={}
        )
        
        assert strategy is not None
        assert CognitiveProcessType.CREATIVITY in strategy.applicable_to
    
    def test_record_strategy_use(self, monitor):
        """Test recording strategy use."""
        # Get a strategy
        strategy = list(monitor.strategies.values())[0]
        strategy_id = strategy.strategy_id
        
        initial_times_used = strategy.times_used
        initial_success_rate = strategy.success_rate
        
        # Record successful use
        monitor.record_strategy_use(
            strategy_id=strategy_id,
            success=True,
            efficiency=0.8
        )
        
        strategy = monitor.strategies[strategy_id]
        assert strategy.times_used == initial_times_used + 1
        assert strategy.last_used is not None
        assert strategy.success_rate > initial_success_rate  # Should increase
        
        # Record unsuccessful use
        monitor.record_strategy_use(
            strategy_id=strategy_id,
            success=False,
            efficiency=0.3
        )
        
        strategy = monitor.strategies[strategy_id]
        assert strategy.times_used == initial_times_used + 2
    
    def test_get_cognitive_profile(self, monitor):
        """Test getting cognitive profile."""
        # Create some processes
        for i in range(5):
            process_id = monitor.start_process(
                CognitiveProcessType.REASONING,
                f"Process {i}"
            )
            monitor.update_process(process_id, confidence_level=0.7)
            if i % 2 == 0:
                monitor.detect_error(process_id, ErrorType.BIAS, "Test error")
            monitor.complete_process(process_id)
        
        # Get profile
        profile = monitor.get_cognitive_profile()
        
        assert profile["total_processes"] == 5
        assert 0.0 <= profile["average_efficiency"] <= 1.0
        assert 0.0 <= profile["error_rate"] <= 1.0
        assert 0.0 <= profile["average_confidence"] <= 1.0
        assert isinstance(profile["most_common_errors"], list)
        assert isinstance(profile["best_strategies"], list)
    
    def test_process_serialization(self, monitor):
        """Test process serialization."""
        process_id = monitor.start_process(
            CognitiveProcessType.REASONING,
            "Test serialization"
        )
        monitor.update_process(process_id, confidence_level=0.8, steps_completed=3)
        monitor.detect_error(process_id, ErrorType.BIAS, "Test error")
        
        process = monitor.get_process(process_id)
        process_dict = process.to_dict()
        
        assert "process_id" in process_dict
        assert "process_type" in process_dict
        assert process_dict["process_type"] == "reasoning"
        assert "confidence_level" in process_dict
        assert process_dict["confidence_level"] == 0.8
        assert "errors_detected" in process_dict
        assert "bias" in process_dict["errors_detected"]
    
    def test_insight_serialization(self):
        """Test insight serialization."""
        insight = CognitiveInsight(
            process_type=CognitiveProcessType.REASONING,
            insight_type="error",
            description="Test insight",
            evidence=["Evidence 1", "Evidence 2"],
            confidence=0.9,
            actionable=True,
            recommended_actions=["Action 1", "Action 2"]
        )
        
        insight_dict = insight.to_dict()
        
        assert "insight_id" in insight_dict
        assert "process_type" in insight_dict
        assert insight_dict["process_type"] == "reasoning"
        assert "insight_type" in insight_dict
        assert insight_dict["insight_type"] == "error"
        assert "evidence" in insight_dict
        assert len(insight_dict["evidence"]) == 2
        assert "actionable" in insight_dict
        assert insight_dict["actionable"] is True
    
    def test_strategy_serialization(self):
        """Test strategy serialization."""
        strategy = CognitiveStrategy(
            name="Test Strategy",
            description="Test description",
            applicable_to=[CognitiveProcessType.REASONING, CognitiveProcessType.PLANNING],
            success_rate=0.8,
            average_efficiency=0.75,
            times_used=10
        )
        
        strategy_dict = strategy.to_dict()
        
        assert "strategy_id" in strategy_dict
        assert "name" in strategy_dict
        assert strategy_dict["name"] == "Test Strategy"
        assert "applicable_to" in strategy_dict
        assert "reasoning" in strategy_dict["applicable_to"]
        assert "success_rate" in strategy_dict
        assert strategy_dict["success_rate"] == 0.8
    
    def test_database_persistence(self, temp_db):
        """Test that processes are saved to database."""
        # Create monitor and add process
        monitor1 = MetacognitiveMonitor(db_path=temp_db)
        process_id = monitor1.start_process(
            CognitiveProcessType.REASONING,
            "Test persistence"
        )
        monitor1.update_process(process_id, confidence_level=0.8)
        monitor1.complete_process(process_id)
        
        # Create new monitor with same database
        monitor2 = MetacognitiveMonitor(db_path=temp_db)
        
        # Should be able to retrieve the process
        history = monitor2.get_process_history(limit=10)
        assert len(history) > 0
        
        process_ids = [p.process_id for p in history]
        assert process_id in process_ids
    
    def test_multiple_error_types(self, monitor):
        """Test detecting multiple error types."""
        process_id = monitor.start_process(
            CognitiveProcessType.REASONING,
            "Test multiple errors"
        )
        
        monitor.detect_error(process_id, ErrorType.BIAS, "Bias error")
        monitor.detect_error(process_id, ErrorType.LOGICAL_FALLACY, "Logic error")
        monitor.detect_error(process_id, ErrorType.INCONSISTENCY, "Inconsistency")
        
        process = monitor.get_process(process_id)
        assert len(process.errors_detected) == 3
        assert ErrorType.BIAS in process.errors_detected
        assert ErrorType.LOGICAL_FALLACY in process.errors_detected
        assert ErrorType.INCONSISTENCY in process.errors_detected
    
    def test_low_confidence_insight(self, monitor):
        """Test that low confidence generates insight."""
        process_id = monitor.start_process(
            CognitiveProcessType.REASONING,
            "Test low confidence"
        )
        
        monitor.update_process(process_id, confidence_level=0.3)
        monitor.complete_process(process_id)
        
        # Should generate low confidence insight
        insights = monitor.get_insights(insight_type="low_confidence", limit=10)
        assert len(insights) > 0
        
        insight = insights[0]
        assert "confidence" in insight.description.lower()
        assert insight.actionable
    
    def test_inefficiency_insight(self, monitor):
        """Test that inefficiency generates insight."""
        process_id = monitor.start_process(
            CognitiveProcessType.REASONING,
            "Test inefficiency"
        )
        
        # Make it inefficient - add many errors and low confidence
        monitor.update_process(process_id, confidence_level=0.2)
        for i in range(5):
            monitor.detect_error(process_id, ErrorType.BIAS, f"Error {i}")
        monitor.complete_process(process_id)
        
        process = monitor.get_process(process_id)
        # With 5 errors (0.5 penalty) and low confidence (0.16 penalty), score should be low
        assert process.efficiency_score < 0.5
        
        # Should generate inefficiency insight
        insights = monitor.get_insights(insight_type="inefficiency", limit=10)
        assert len(insights) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
