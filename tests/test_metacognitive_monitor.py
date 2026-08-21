"""
Tests for Phase 18: Metacognitive Monitoring
"""

import pytest
import tempfile
import os
from app.cognition.metacognitive_monitor import (
    MetacognitiveMonitor,
    CognitiveProcess,
    ReasoningStrategy,
    CognitiveBias,
    CognitiveLoad,
    CognitiveProcessRecord,
    CognitiveProfile,
    CognitiveOptimization
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing (isolated via tmp_path)."""
    yield str(tmp_path / "test.db")


@pytest.fixture
def monitor(temp_db):
    """Create a metacognitive monitor with temp database."""
    return MetacognitiveMonitor(db_path=temp_db)


class TestMetacognitiveMonitor:
    """Test suite for metacognitive monitoring functionality."""
    
    def test_record_process(self, monitor):
        """Test recording a cognitive process."""
        record = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={"premises": ["All humans are mortal", "Socrates is human"]},
            output_data={"conclusion": "Socrates is mortal"},
            execution_time_ms=150.5,
            confidence=0.95,
            success=True
        )
        
        assert record.record_id is not None
        assert record.process_type == CognitiveProcess.REASONING
        assert record.strategy == ReasoningStrategy.DEDUCTIVE
        assert record.execution_time_ms == 150.5
        assert record.confidence == 0.95
        assert record.success is True
        assert len(record.lessons_learned) > 0
    
    def test_record_process_with_errors(self, monitor):
        """Test recording a process with errors."""
        record = monitor.record_process(
            process_type=CognitiveProcess.PROBLEM_SOLVING,
            strategy=ReasoningStrategy.HEURISTIC,
            input_data={"problem": "Complex optimization"},
            output_data={"solution": None},
            execution_time_ms=2500.0,
            confidence=0.3,
            success=False,
            errors=["Timeout", "Insufficient data"]
        )
        
        assert record.success is False
        assert len(record.errors) == 2
        assert "Timeout" in record.errors
        assert record.cognitive_load in [CognitiveLoad.HIGH, CognitiveLoad.OVERLOAD]
    
    def test_detect_overconfidence_bias(self, monitor):
        """Test detection of overconfidence bias."""
        record = monitor.record_process(
            process_type=CognitiveProcess.DECISION_MAKING,
            strategy=ReasoningStrategy.HEURISTIC,
            input_data={"options": ["A", "B", "C"]},
            output_data={"decision": "A"},
            execution_time_ms=100.0,
            confidence=0.98,  # Very high confidence
            success=True
        )
        
        assert CognitiveBias.OVERCONFIDENCE in record.biases_detected
    
    def test_detect_confirmation_bias(self, monitor):
        """Test detection of confirmation bias."""
        # All evidence supports the same conclusion
        evidence = [
            {"supports": True, "data": "Evidence 1"},
            {"supports": True, "data": "Evidence 2"},
            {"supports": True, "data": "Evidence 3"},
            {"supports": True, "data": "Evidence 4"}
        ]
        
        record = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.INDUCTIVE,
            input_data={"evidence": evidence},
            output_data={"conclusion": "Hypothesis confirmed"},
            execution_time_ms=200.0,
            confidence=0.85,
            success=True
        )
        
        assert CognitiveBias.CONFIRMATION_BIAS in record.biases_detected
    
    def test_detect_anchoring_bias(self, monitor):
        """Test detection of anchoring bias."""
        record = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.HEURISTIC,
            input_data={"initial_estimate": 100},
            output_data={"final_estimate": 105},  # Very close to initial
            execution_time_ms=150.0,
            confidence=0.75,
            success=True
        )
        
        assert CognitiveBias.ANCHORING_BIAS in record.biases_detected
    
    def test_assess_cognitive_load(self, monitor):
        """Test cognitive load assessment."""
        # Low load
        record1 = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=500.0,
            confidence=0.9,
            success=True
        )
        assert record1.cognitive_load == CognitiveLoad.LOW
        
        # Moderate load
        record2 = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=1500.0,
            confidence=0.9,
            success=True
        )
        assert record2.cognitive_load == CognitiveLoad.MODERATE
        
        # High load
        record3 = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=2500.0,
            confidence=0.9,
            success=True
        )
        assert record3.cognitive_load == CognitiveLoad.HIGH
        
        # Overload
        record4 = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=6000.0,
            confidence=0.9,
            success=True
        )
        assert record4.cognitive_load == CognitiveLoad.OVERLOAD
    
    def test_generate_lessons(self, monitor):
        """Test lesson generation."""
        # Successful process
        record1 = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=100.0,
            confidence=0.9,
            success=True
        )
        assert any("worked well" in lesson for lesson in record1.lessons_learned)
        
        # Failed process
        record2 = monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=100.0,
            confidence=0.9,
            success=False,
            errors=["Test error"]
        )
        assert any("failed" in lesson for lesson in record2.lessons_learned)
        
        # Process with biases
        record3 = monitor.record_process(
            process_type=CognitiveProcess.DECISION_MAKING,
            strategy=ReasoningStrategy.HEURISTIC,
            input_data={},
            output_data={},
            execution_time_ms=100.0,
            confidence=0.98,
            success=True
        )
        assert any("bias" in lesson.lower() for lesson in record3.lessons_learned)
    
    def test_update_profile(self, monitor):
        """Test cognitive profile updates."""
        # Record multiple processes
        for i in range(5):
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.DEDUCTIVE if i < 3 else ReasoningStrategy.INDUCTIVE,
                input_data={},
                output_data={},
                execution_time_ms=100.0 + i * 50,
                confidence=0.8 + i * 0.02,
                success=True if i < 4 else False
            )
        
        # Get profile
        profile = monitor.get_profile(CognitiveProcess.REASONING)
        
        assert profile is not None
        assert profile.process_type == CognitiveProcess.REASONING
        assert profile.total_executions == 5
        assert profile.average_execution_time_ms > 0
        assert profile.average_confidence > 0
        assert profile.success_rate == 0.8  # 4 out of 5 succeeded
        assert "deductive" in profile.strategy_preferences
        assert "inductive" in profile.strategy_preferences
    
    def test_get_profile(self, monitor):
        """Test getting cognitive profile."""
        # Initially no profile
        profile = monitor.get_profile(CognitiveProcess.REASONING)
        assert profile is None
        
        # Record a process
        monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=100.0,
            confidence=0.9,
            success=True
        )
        
        # Now profile exists
        profile = monitor.get_profile(CognitiveProcess.REASONING)
        assert profile is not None
        assert profile.total_executions == 1
    
    def test_get_all_profiles(self, monitor):
        """Test getting all cognitive profiles."""
        # Record processes for different types
        monitor.record_process(
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={},
            output_data={},
            execution_time_ms=100.0,
            confidence=0.9,
            success=True
        )
        
        monitor.record_process(
            process_type=CognitiveProcess.PLANNING,
            strategy=ReasoningStrategy.HEURISTIC,
            input_data={},
            output_data={},
            execution_time_ms=200.0,
            confidence=0.8,
            success=True
        )
        
        profiles = monitor.get_all_profiles()
        
        assert len(profiles) == 2
        process_types = {p.process_type for p in profiles}
        assert CognitiveProcess.REASONING in process_types
        assert CognitiveProcess.PLANNING in process_types
    
    def test_get_process_history(self, monitor):
        """Test getting process history."""
        # Record multiple processes
        for i in range(5):
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.DEDUCTIVE,
                input_data={"iteration": i},
                output_data={},
                execution_time_ms=100.0,
                confidence=0.9,
                success=True
            )
        
        # Get history
        history = monitor.get_process_history(CognitiveProcess.REASONING, limit=10)
        
        assert len(history) == 5
        # Should be in reverse chronological order
        assert history[0].input_data["iteration"] == 4
        assert history[4].input_data["iteration"] == 0
    
    def test_analyze_patterns(self, monitor):
        """Test pattern analysis."""
        # Record multiple processes with different strategies
        for i in range(10):
            strategy = ReasoningStrategy.DEDUCTIVE if i < 6 else ReasoningStrategy.INDUCTIVE
            success = i < 8  # 8 out of 10 succeed
            
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=strategy,
                input_data={},
                output_data={},
                execution_time_ms=100.0,
                confidence=0.9,
                success=success
            )
        
        # Analyze patterns
        patterns = monitor.analyze_patterns(CognitiveProcess.REASONING, time_window_hours=24)
        
        assert patterns["process_type"] == "reasoning"
        assert patterns["total_executions"] == 10
        assert patterns["most_common_strategy"] == "deductive"
        assert "deductive" in patterns["strategy_usage"]
        assert "inductive" in patterns["strategy_usage"]
        assert patterns["strategy_usage"]["deductive"] == 6
        assert patterns["strategy_usage"]["inductive"] == 4
    
    def test_generate_optimizations(self, monitor):
        """Test optimization generation."""
        # Create a profile with low success rate
        for i in range(15):
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.DEDUCTIVE,
                input_data={},
                output_data={},
                execution_time_ms=100.0,
                confidence=0.9,
                success=i < 7  # Only 7 out of 15 succeed (< 60%)
            )
        
        # Generate optimizations
        optimizations = monitor.generate_optimizations()
        
        assert len(optimizations) > 0
        assert any(opt.recommendation.startswith("Improve reasoning success rate") for opt in optimizations)
    
    def test_generate_optimizations_for_biases(self, monitor):
        """Test optimization generation for biases."""
        # Create processes with multiple biases for the same process type
        # Overconfidence bias (high confidence in decision making)
        for i in range(8):
            monitor.record_process(
                process_type=CognitiveProcess.DECISION_MAKING,
                strategy=ReasoningStrategy.HEURISTIC,
                input_data={},
                output_data={},
                execution_time_ms=100.0,
                confidence=0.98,  # Triggers overconfidence
                success=True
            )
        
        # Anchoring bias (final estimate close to initial)
        for i in range(8):
            monitor.record_process(
                process_type=CognitiveProcess.DECISION_MAKING,
                strategy=ReasoningStrategy.HEURISTIC,
                input_data={"initial_estimate": 100},
                output_data={"final_estimate": 105},  # Triggers anchoring
                execution_time_ms=150.0,
                confidence=0.75,
                success=True
            )
        
        # Generate optimizations
        optimizations = monitor.generate_optimizations()
        
        # Should have at least one optimization for biases
        assert len(optimizations) > 0
        # At least one should mention bias
        assert any("bias" in opt.recommendation.lower() for opt in optimizations)
    
    def test_generate_optimizations_for_performance(self, monitor):
        """Test optimization generation for slow performance."""
        # Create slow processes
        for i in range(15):
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.DEDUCTIVE,
                input_data={},
                output_data={},
                execution_time_ms=4000.0,  # Slow (> 3s)
                confidence=0.9,
                success=True
            )
        
        # Generate optimizations
        optimizations = monitor.generate_optimizations()
        
        assert len(optimizations) > 0
        assert any("performance" in opt.recommendation.lower() or "optimize" in opt.recommendation.lower() for opt in optimizations)
    
    def test_get_optimizations(self, monitor):
        """Test getting optimizations."""
        # First, create processes that will trigger optimizations
        # Create processes with low success rate
        for i in range(15):
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.DEDUCTIVE,
                input_data={},
                output_data={},
                execution_time_ms=100.0,
                confidence=0.9,
                success=i < 7  # Only 7 out of 15 succeed (< 60%)
            )
        
        # Generate optimizations
        monitor.generate_optimizations()
        
        # Get all optimizations
        optimizations = monitor.get_optimizations()
        assert len(optimizations) > 0
        
        # Get pending optimizations
        pending = monitor.get_optimizations(implemented=False)
        assert len(pending) == len(optimizations)
        
        # Get implemented optimizations (should be empty)
        implemented = monitor.get_optimizations(implemented=True)
        assert len(implemented) == 0
    
    def test_mark_optimization_implemented(self, monitor):
        """Test marking optimization as implemented."""
        # Generate optimizations
        optimizations = monitor.generate_optimizations()
        
        if len(optimizations) > 0:
            opt_id = optimizations[0].optimization_id
            
            # Mark as implemented
            updated = monitor.mark_optimization_implemented(opt_id)
            
            assert updated is not None
            assert updated.implemented is True
            assert updated.implemented_at is not None
            
            # Verify it's now in implemented list
            implemented = monitor.get_optimizations(implemented=True)
            assert len(implemented) == 1
            assert implemented[0].optimization_id == opt_id
    
    def test_get_cognitive_summary(self, monitor):
        """Test getting cognitive summary."""
        # Record some processes
        for i in range(5):
            monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.DEDUCTIVE,
                input_data={},
                output_data={},
                execution_time_ms=100.0,
                confidence=0.9,
                success=True
            )
        
        for i in range(3):
            monitor.record_process(
                process_type=CognitiveProcess.PLANNING,
                strategy=ReasoningStrategy.HEURISTIC,
                input_data={},
                output_data={},
                execution_time_ms=200.0,
                confidence=0.8,
                success=True
            )
        
        # Get summary
        summary = monitor.get_cognitive_summary()
        
        assert summary["total_processes"] == 8
        assert summary["process_types"] == 2
        assert summary["average_success_rate"] == 1.0
        assert "reasoning" in summary["profiles"]
        assert "planning" in summary["profiles"]
        assert summary["profiles"]["reasoning"]["executions"] == 5
        assert summary["profiles"]["planning"]["executions"] == 3
    
    def test_process_record_serialization(self):
        """Test process record serialization."""
        record = CognitiveProcessRecord(
            record_id="test123",
            process_type=CognitiveProcess.REASONING,
            strategy=ReasoningStrategy.DEDUCTIVE,
            input_data={"test": "data"},
            output_data={"result": "success"},
            execution_time_ms=150.5,
            confidence=0.95,
            cognitive_load=CognitiveLoad.MODERATE,
            biases_detected=[CognitiveBias.OVERCONFIDENCE],
            errors=["Error 1"],
            success=True,
            lessons_learned=["Lesson 1", "Lesson 2"]
        )
        
        # Serialize
        record_dict = record.to_dict()
        
        # Deserialize
        restored = CognitiveProcessRecord.from_dict(record_dict)
        
        assert restored.record_id == record.record_id
        assert restored.process_type == record.process_type
        assert restored.strategy == record.strategy
        assert restored.execution_time_ms == record.execution_time_ms
        assert restored.confidence == record.confidence
        assert restored.cognitive_load == record.cognitive_load
        assert restored.biases_detected == record.biases_detected
        assert restored.errors == record.errors
        assert restored.success == record.success
        assert restored.lessons_learned == record.lessons_learned
    
    def test_profile_serialization(self):
        """Test profile serialization."""
        profile = CognitiveProfile(
            profile_id="profile123",
            process_type=CognitiveProcess.REASONING,
            strategy_preferences={"deductive": 0.8, "inductive": 0.6},
            average_execution_time_ms=150.5,
            average_confidence=0.85,
            success_rate=0.9,
            common_biases=[CognitiveBias.OVERCONFIDENCE, CognitiveBias.CONFIRMATION_BIAS],
            strengths=["Fast execution", "High confidence"],
            weaknesses=["Occasional bias"],
            total_executions=100
        )
        
        # Serialize
        profile_dict = profile.to_dict()
        
        # Deserialize
        restored = CognitiveProfile.from_dict(profile_dict)
        
        assert restored.profile_id == profile.profile_id
        assert restored.process_type == profile.process_type
        assert restored.strategy_preferences == profile.strategy_preferences
        assert restored.average_execution_time_ms == profile.average_execution_time_ms
        assert restored.average_confidence == profile.average_confidence
        assert restored.success_rate == profile.success_rate
        assert restored.common_biases == profile.common_biases
        assert restored.strengths == profile.strengths
        assert restored.weaknesses == profile.weaknesses
        assert restored.total_executions == profile.total_executions
    
    def test_optimization_serialization(self):
        """Test optimization serialization."""
        optimization = CognitiveOptimization(
            optimization_id="opt123",
            process_type=CognitiveProcess.REASONING,
            recommendation="Improve success rate",
            rationale="Current rate is below threshold",
            expected_improvement=0.2,
            priority=1,
            implemented=False
        )
        
        # Serialize
        opt_dict = optimization.to_dict()
        
        # Deserialize
        restored = CognitiveOptimization.from_dict(opt_dict)
        
        assert restored.optimization_id == optimization.optimization_id
        assert restored.process_type == optimization.process_type
        assert restored.recommendation == optimization.recommendation
        assert restored.rationale == optimization.rationale
        assert restored.expected_improvement == optimization.expected_improvement
        assert restored.priority == optimization.priority
        assert restored.implemented == optimization.implemented


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
