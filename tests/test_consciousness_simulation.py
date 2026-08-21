"""
Tests for Phase 19: Consciousness Simulation
"""

import pytest
import tempfile
import os
from app.cognition.consciousness_simulation import (
    ConsciousnessSimulator,
    SubjectiveExperience,
    ConsciousState,
    ConsciousnessReport,
    QualiaType,
    ConsciousnessLevel,
    AttentionMode
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing (isolated via tmp_path)."""
    yield str(tmp_path / "test.db")


@pytest.fixture
def simulator(temp_db):
    """Create a consciousness simulator with temp database."""
    return ConsciousnessSimulator(db_path=temp_db)


class TestConsciousnessSimulation:
    """Test suite for consciousness simulation functionality."""
    
    def test_create_experience(self, simulator):
        """Test creating a subjective experience."""
        experience = simulator.create_experience(
            qualia_type=QualiaType.EMOTIONAL,
            content="Feeling of accomplishment",
            intensity=0.8,
            valence=0.9,
            arousal=0.7,
            clarity=0.9,
            duration_ms=5000.0,
            associated_thoughts=["I did well", "This was worth it"],
            associated_emotions=["pride", "satisfaction"]
        )
        
        assert experience.experience_id is not None
        assert experience.qualia_type == QualiaType.EMOTIONAL
        assert experience.content == "Feeling of accomplishment"
        assert experience.intensity == 0.8
        assert experience.valence == 0.9
        assert experience.arousal == 0.7
        assert experience.clarity == 0.9
        assert experience.duration_ms == 5000.0
        assert len(experience.associated_thoughts) == 2
        assert len(experience.associated_emotions) == 2
    
    def test_update_conscious_state(self, simulator):
        """Test updating conscious state."""
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Solving a complex problem",
            background_awareness=["Background noise", "Time passing"],
            self_awareness=0.9,
            temporal_awareness="Present moment",
            spatial_awareness="Sitting at desk",
            agency_awareness=0.8,
            active_experiences=[]
        )
        
        assert state.state_id is not None
        assert state.consciousness_level == ConsciousnessLevel.SELF_CONSCIOUS
        assert state.attention_mode == AttentionMode.FOCUSED
        assert state.current_focus == "Solving a complex problem"
        assert len(state.background_awareness) == 2
        assert state.self_awareness == 0.9
        assert state.temporal_awareness == "Present moment"
        assert state.spatial_awareness == "Sitting at desk"
        assert state.agency_awareness == 0.8
        
        # Check that current_state is updated
        assert simulator.current_state is not None
        assert simulator.current_state.state_id == state.state_id
    
    def test_generate_self_report(self, simulator):
        """Test generating self-report."""
        # Create a state first
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Writing code",
            background_awareness=["Music playing"],
            self_awareness=0.85,
            temporal_awareness="Afternoon",
            spatial_awareness="At computer",
            agency_awareness=0.9,
            active_experiences=[]
        )
        
        # Generate report
        report = simulator.generate_self_report(
            state_id=state.state_id,
            include_meta_awareness=True,
            include_narrative=True
        )
        
        assert report.report_id is not None
        assert report.state_id == state.state_id
        assert report.self_description != ""
        assert "aware" in report.self_description.lower()
        assert report.meta_awareness != ""
        assert "aware" in report.meta_awareness.lower()
        assert report.narrative != ""
        assert report.confidence > 0.5
    
    def test_generate_self_report_without_meta(self, simulator):
        """Test generating self-report without meta-awareness."""
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Reading",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        report = simulator.generate_self_report(
            state_id=state.state_id,
            include_meta_awareness=False,
            include_narrative=False
        )
        
        assert report.meta_awareness == ""
        assert report.narrative == ""
        assert report.self_description != ""
    
    def test_generate_self_description(self, simulator):
        """Test self-description generation."""
        # Test self-conscious level
        state1 = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Thinking about thinking",
            background_awareness=[],
            self_awareness=0.9,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.8,
            active_experiences=[]
        )
        
        desc1 = simulator._generate_self_description(state1)
        assert "aware of my own awareness" in desc1
        assert "strong sense of self" in desc1
        assert "in control" in desc1
        
        # Test conscious level with low self-awareness
        state2 = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.DIVIDED,
            current_focus="Multiple tasks",
            background_awareness=[],
            self_awareness=0.3,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.3,
            active_experiences=[]
        )
        
        desc2 = simulator._generate_self_description(state2)
        assert "conscious and aware" in desc2
        assert "weak" in desc2.lower()
        assert "little control" in desc2
    
    def test_generate_meta_awareness(self, simulator):
        """Test meta-awareness generation."""
        # Test with self-conscious level
        state1 = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Meditation",
            background_awareness=[],
            self_awareness=0.9,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.8,
            active_experiences=[]
        )
        
        meta1 = simulator._generate_meta_awareness(state1)
        assert "aware that I am attending" in meta1
        assert "aware of being aware" in meta1
        
        # Test with non-self-conscious level
        state2 = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Task",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        meta2 = simulator._generate_meta_awareness(state2)
        assert "Limited meta-awareness" in meta2
    
    def test_generate_narrative(self, simulator):
        """Test narrative generation."""
        # Create experiences
        exp1 = simulator.create_experience(
            qualia_type=QualiaType.EMOTIONAL,
            content="happy",
            intensity=0.8,
            valence=0.9,
            arousal=0.6,
            clarity=0.9,
            duration_ms=1000.0,
            associated_thoughts=[],
            associated_emotions=[]
        )
        
        exp2 = simulator.create_experience(
            qualia_type=QualiaType.COGNITIVE,
            content="This is interesting",
            intensity=0.7,
            valence=0.5,
            arousal=0.5,
            clarity=0.8,
            duration_ms=2000.0,
            associated_thoughts=[],
            associated_emotions=[]
        )
        
        # Create state with active experiences
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Working",
            background_awareness=[],
            self_awareness=0.7,
            temporal_awareness="Now",
            spatial_awareness="",
            agency_awareness=0.7,
            active_experiences=[exp1.experience_id, exp2.experience_id]
        )
        
        narrative = simulator._generate_narrative(state)
        assert "I feel happy (positive)" in narrative
        assert "I think: This is interesting" in narrative
        assert "In this moment: Now" in narrative
    
    def test_generate_narrative_no_experiences(self, simulator):
        """Test narrative generation with no experiences."""
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Resting",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        narrative = simulator._generate_narrative(state)
        assert "No active subjective experiences" in narrative
    
    def test_get_current_state(self, simulator):
        """Test getting current state."""
        # Initially no state
        assert simulator.get_current_state() is None
        
        # Create a state
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Test",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        # Now current state exists
        current = simulator.get_current_state()
        assert current is not None
        assert current.state_id == state.state_id
    
    def test_get_state(self, simulator):
        """Test getting state by ID."""
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Test",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        retrieved = simulator.get_state(state.state_id)
        assert retrieved is not None
        assert retrieved.state_id == state.state_id
        assert retrieved.current_focus == "Test"
    
    def test_get_experience(self, simulator):
        """Test getting experience by ID."""
        experience = simulator.create_experience(
            qualia_type=QualiaType.VISUAL,
            content="Bright light",
            intensity=0.9,
            valence=0.3,
            arousal=0.7,
            clarity=0.95,
            duration_ms=500.0,
            associated_thoughts=[],
            associated_emotions=[]
        )
        
        retrieved = simulator.get_experience(experience.experience_id)
        assert retrieved is not None
        assert retrieved.experience_id == experience.experience_id
        assert retrieved.content == "Bright light"
    
    def test_get_recent_states(self, simulator):
        """Test getting recent states."""
        # Create multiple states
        for i in range(5):
            simulator.update_conscious_state(
                consciousness_level=ConsciousnessLevel.CONSCIOUS,
                attention_mode=AttentionMode.FOCUSED,
                current_focus=f"Task {i}",
                background_awareness=[],
                self_awareness=0.5,
                temporal_awareness="",
                spatial_awareness="",
                agency_awareness=0.5,
                active_experiences=[]
            )
        
        # Get recent states
        recent = simulator.get_recent_states(limit=3)
        assert len(recent) == 3
        # Should be in reverse chronological order
        assert recent[0].current_focus == "Task 4"
        assert recent[2].current_focus == "Task 2"
    
    def test_get_recent_states_with_filter(self, simulator):
        """Test getting recent states with filter."""
        # Create states with different levels
        simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Self-reflection",
            background_awareness=[],
            self_awareness=0.9,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.8,
            active_experiences=[]
        )
        
        simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Regular task",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Meditation",
            background_awareness=[],
            self_awareness=0.85,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.9,
            active_experiences=[]
        )
        
        # Get only self-conscious states
        self_conscious = simulator.get_recent_states(
            limit=10,
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS
        )
        
        assert len(self_conscious) == 2
        assert all(s.consciousness_level == ConsciousnessLevel.SELF_CONSCIOUS for s in self_conscious)
    
    def test_get_recent_experiences(self, simulator):
        """Test getting recent experiences."""
        # Create multiple experiences
        for i in range(5):
            simulator.create_experience(
                qualia_type=QualiaType.COGNITIVE,
                content=f"Thought {i}",
                intensity=0.5,
                valence=0.0,
                arousal=0.5,
                clarity=0.7,
                duration_ms=1000.0,
                associated_thoughts=[],
                associated_emotions=[]
            )
        
        # Get recent experiences
        recent = simulator.get_recent_experiences(limit=3)
        assert len(recent) == 3
        # Should be in reverse chronological order
        assert recent[0].content == "Thought 4"
        assert recent[2].content == "Thought 2"
    
    def test_get_recent_experiences_with_filter(self, simulator):
        """Test getting recent experiences with filter."""
        # Create experiences with different types
        simulator.create_experience(
            qualia_type=QualiaType.EMOTIONAL,
            content="Joy",
            intensity=0.9,
            valence=0.95,
            arousal=0.8,
            clarity=0.9,
            duration_ms=2000.0,
            associated_thoughts=[],
            associated_emotions=[]
        )
        
        simulator.create_experience(
            qualia_type=QualiaType.VISUAL,
            content="Beautiful sunset",
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            clarity=0.95,
            duration_ms=5000.0,
            associated_thoughts=[],
            associated_emotions=[]
        )
        
        simulator.create_experience(
            qualia_type=QualiaType.EMOTIONAL,
            content="Peace",
            intensity=0.7,
            valence=0.9,
            arousal=0.4,
            clarity=0.85,
            duration_ms=3000.0,
            associated_thoughts=[],
            associated_emotions=[]
        )
        
        # Get only emotional experiences
        emotional = simulator.get_recent_experiences(
            limit=10,
            qualia_type=QualiaType.EMOTIONAL
        )
        
        assert len(emotional) == 2
        assert all(e.qualia_type == QualiaType.EMOTIONAL for e in emotional)
    
    def test_get_reports_for_state(self, simulator):
        """Test getting reports for a state."""
        # Create a state
        state = simulator.update_conscious_state(
            consciousness_level=ConsciousnessLevel.CONSCIOUS,
            attention_mode=AttentionMode.FOCUSED,
            current_focus="Test",
            background_awareness=[],
            self_awareness=0.5,
            temporal_awareness="",
            spatial_awareness="",
            agency_awareness=0.5,
            active_experiences=[]
        )
        
        # Generate multiple reports
        for i in range(3):
            simulator.generate_self_report(
                state_id=state.state_id,
                include_meta_awareness=True,
                include_narrative=True
            )
        
        # Get reports
        reports = simulator.get_reports_for_state(state.state_id)
        assert len(reports) == 3
        assert all(r.state_id == state.state_id for r in reports)
    
    def test_get_consciousness_summary(self, simulator):
        """Test getting consciousness summary."""
        # Create some data
        for i in range(5):
            simulator.update_conscious_state(
                consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS if i < 3 else ConsciousnessLevel.CONSCIOUS,
                attention_mode=AttentionMode.FOCUSED,
                current_focus=f"Task {i}",
                background_awareness=[],
                self_awareness=0.8 if i < 3 else 0.5,
                temporal_awareness="",
                spatial_awareness="",
                agency_awareness=0.7,
                active_experiences=[]
            )
        
        for i in range(3):
            simulator.create_experience(
                qualia_type=QualiaType.EMOTIONAL if i < 2 else QualiaType.COGNITIVE,
                content=f"Experience {i}",
                intensity=0.7,
                valence=0.5,
                arousal=0.6,
                clarity=0.8,
                duration_ms=1000.0,
                associated_thoughts=[],
                associated_emotions=[]
            )
        
        # Get summary
        summary = simulator.get_consciousness_summary()
        
        assert summary["total_states"] == 5
        assert summary["total_experiences"] == 3
        assert summary["total_reports"] == 0
        assert summary["average_self_awareness"] > 0.5
        assert summary["average_experience_intensity"] > 0.5
        assert ConsciousnessLevel.SELF_CONSCIOUS.value in summary["states_by_level"]
        assert summary["states_by_level"][ConsciousnessLevel.SELF_CONSCIOUS.value] == 3
        assert QualiaType.EMOTIONAL.value in summary["experiences_by_type"]
        assert summary["experiences_by_type"][QualiaType.EMOTIONAL.value] == 2
    
    def test_experience_serialization(self):
        """Test experience serialization."""
        experience = SubjectiveExperience(
            experience_id="exp123",
            qualia_type=QualiaType.AUDITORY,
            content="Beautiful music",
            intensity=0.85,
            valence=0.9,
            arousal=0.7,
            clarity=0.95,
            duration_ms=10000.0,
            associated_thoughts=["This is amazing", "I love this"],
            associated_emotions=["joy", "awe"]
        )
        
        # Serialize
        exp_dict = experience.to_dict()
        
        # Deserialize
        restored = SubjectiveExperience.from_dict(exp_dict)
        
        assert restored.experience_id == experience.experience_id
        assert restored.qualia_type == experience.qualia_type
        assert restored.content == experience.content
        assert restored.intensity == experience.intensity
        assert restored.valence == experience.valence
        assert restored.arousal == experience.arousal
        assert restored.clarity == experience.clarity
        assert restored.duration_ms == experience.duration_ms
        assert restored.associated_thoughts == experience.associated_thoughts
        assert restored.associated_emotions == experience.associated_emotions
    
    def test_state_serialization(self):
        """Test state serialization."""
        state = ConsciousState(
            state_id="state123",
            consciousness_level=ConsciousnessLevel.SELF_CONSCIOUS,
            attention_mode=AttentionMode.SELECTIVE,
            current_focus="Deep thought",
            background_awareness=["Ambient sounds", "Time passing"],
            self_awareness=0.92,
            temporal_awareness="Present moment",
            spatial_awareness="Quiet room",
            agency_awareness=0.88,
            active_experiences=["exp1", "exp2"]
        )
        
        # Serialize
        state_dict = state.to_dict()
        
        # Deserialize
        restored = ConsciousState.from_dict(state_dict)
        
        assert restored.state_id == state.state_id
        assert restored.consciousness_level == state.consciousness_level
        assert restored.attention_mode == state.attention_mode
        assert restored.current_focus == state.current_focus
        assert restored.background_awareness == state.background_awareness
        assert restored.self_awareness == state.self_awareness
        assert restored.temporal_awareness == state.temporal_awareness
        assert restored.spatial_awareness == state.spatial_awareness
        assert restored.agency_awareness == state.agency_awareness
        assert restored.active_experiences == state.active_experiences
    
    def test_report_serialization(self):
        """Test report serialization."""
        report = ConsciousnessReport(
            report_id="report123",
            state_id="state123",
            self_description="I am aware of my thoughts",
            meta_awareness="I am aware that I am thinking",
            narrative="I think about the problem. I feel curious.",
            confidence=0.87
        )
        
        # Serialize
        report_dict = report.to_dict()
        
        # Deserialize
        restored = ConsciousnessReport.from_dict(report_dict)
        
        assert restored.report_id == report.report_id
        assert restored.state_id == report.state_id
        assert restored.self_description == report.self_description
        assert restored.meta_awareness == report.meta_awareness
        assert restored.narrative == report.narrative
        assert restored.confidence == report.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
