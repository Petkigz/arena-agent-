"""
Tests for Phase 17: Social Cognition Module
"""

import pytest
import tempfile
import os
from app.cognition.social_cognition import (
    SocialCognitionEngine,
    MentalState,
    Emotion,
    SocialNorm,
    RelationshipType,
    MentalStateModel,
    EmotionalState,
    SocialRelationship,
    SocialInteraction
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing (isolated via tmp_path)."""
    yield str(tmp_path / "test.db")


@pytest.fixture
def social_engine(temp_db):
    """Create a social cognition engine with temp database."""
    return SocialCognitionEngine(db_path=temp_db)


class TestSocialCognition:
    """Test suite for social cognition functionality."""
    
    def test_infer_mental_state(self, social_engine):
        """Test inferring mental states."""
        state = social_engine.infer_mental_state(
            agent_id="user123",
            state_type=MentalState.BELIEF,
            content="User believes the project is behind schedule",
            evidence=["User mentioned delays", "User asked about timeline"],
            confidence=0.8
        )
        
        assert state.state_id is not None
        assert state.agent_id == "user123"
        assert state.state_type == MentalState.BELIEF
        assert state.content == "User believes the project is behind schedule"
        assert state.confidence == 0.8
        assert len(state.evidence) == 2
        
        # Verify it was saved
        retrieved = social_engine.get_mental_state(state.state_id)
        assert retrieved is not None
        assert retrieved.content == state.content
    
    def test_update_mental_state(self, social_engine):
        """Test updating mental states."""
        state = social_engine.infer_mental_state(
            agent_id="user123",
            state_type=MentalState.DESIRE,
            content="User wants to finish the project",
            evidence=["User mentioned deadline"],
            confidence=0.7
        )
        
        # Update the state
        updated = social_engine.update_mental_state(
            state_id=state.state_id,
            content="User wants to finish the project early",
            confidence=0.9,
            evidence=["User asked about accelerating timeline"]
        )
        
        assert updated is not None
        assert updated.content == "User wants to finish the project early"
        assert updated.confidence == 0.9
        assert len(updated.evidence) == 2  # Original + new
    
    def test_get_agent_mental_states(self, social_engine):
        """Test getting all mental states for an agent."""
        # Create multiple mental states
        social_engine.infer_mental_state(
            agent_id="user123",
            state_type=MentalState.BELIEF,
            content="Belief 1",
            evidence=["Evidence 1"],
            confidence=0.8
        )
        
        social_engine.infer_mental_state(
            agent_id="user123",
            state_type=MentalState.DESIRE,
            content="Desire 1",
            evidence=["Evidence 2"],
            confidence=0.7
        )
        
        social_engine.infer_mental_state(
            agent_id="user456",
            state_type=MentalState.BELIEF,
            content="Belief 2",
            evidence=["Evidence 3"],
            confidence=0.6
        )
        
        # Get states for user123
        states = social_engine.get_agent_mental_states("user123")
        assert len(states) == 2
        assert all(s.agent_id == "user123" for s in states)
        
        # Filter by type
        beliefs = social_engine.get_agent_mental_states("user123", MentalState.BELIEF)
        assert len(beliefs) == 1
        assert beliefs[0].state_type == MentalState.BELIEF
    
    def test_recognize_emotion(self, social_engine):
        """Test recognizing emotions."""
        emotion = social_engine.recognize_emotion(
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.9,
            triggers=["Received good news", "Project completed"],
            secondary_emotions=[Emotion.SURPRISE]
        )
        
        assert emotion.emotion_id is not None
        assert emotion.agent_id == "user123"
        assert emotion.primary_emotion == Emotion.JOY
        assert emotion.intensity == 0.9
        assert len(emotion.triggers) == 2
        assert len(emotion.secondary_emotions) == 1
    
    def test_get_agent_emotions(self, social_engine):
        """Test getting recent emotions for an agent."""
        # Create multiple emotions
        social_engine.recognize_emotion(
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.9,
            triggers=["Trigger 1"]
        )
        
        social_engine.recognize_emotion(
            agent_id="user123",
            primary_emotion=Emotion.SADNESS,
            intensity=0.7,
            triggers=["Trigger 2"]
        )
        
        social_engine.recognize_emotion(
            agent_id="user456",
            primary_emotion=Emotion.ANGER,
            intensity=0.8,
            triggers=["Trigger 3"]
        )
        
        # Get emotions for user123
        emotions = social_engine.get_agent_emotions("user123", limit=10)
        assert len(emotions) == 2
        assert all(e.agent_id == "user123" for e in emotions)
        
        # Check ordering (most recent first)
        assert emotions[0].primary_emotion == Emotion.SADNESS
        assert emotions[1].primary_emotion == Emotion.JOY
    
    def test_respond_to_emotion(self, social_engine):
        """Test generating appropriate responses to emotions."""
        # Test different emotions
        joy = EmotionalState(
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.9,
            triggers=["Good news"]
        )
        
        sadness = EmotionalState(
            agent_id="user123",
            primary_emotion=Emotion.SADNESS,
            intensity=0.8,
            triggers=["Bad news"]
        )
        
        anger = EmotionalState(
            agent_id="user123",
            primary_emotion=Emotion.ANGER,
            intensity=0.7,
            triggers=["Frustration"]
        )
        
        # Get responses
        joy_response = social_engine.respond_to_emotion("user123", joy)
        sadness_response = social_engine.respond_to_emotion("user123", sadness)
        anger_response = social_engine.respond_to_emotion("user123", anger)
        
        # Check responses are appropriate
        assert "happy" in joy_response.lower() or "wonderful" in joy_response.lower()
        assert "sorry" in sadness_response.lower() or "help" in sadness_response.lower()
        assert "understand" in anger_response.lower() or "frustrated" in anger_response.lower()
    
    def test_create_relationship(self, social_engine):
        """Test creating social relationships."""
        relationship = social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.6,
            shared_interests=["programming", "AI"]
        )
        
        assert relationship.relationship_id is not None
        assert relationship.agent1_id == "user123"
        assert relationship.agent2_id == "user456"
        assert relationship.relationship_type == RelationshipType.COLLEAGUE
        assert relationship.trust_level == 0.6
        assert len(relationship.shared_interests) == 2
        
        # Verify it was saved
        retrieved = social_engine.get_relationship("user123", "user456")
        assert retrieved is not None
        assert retrieved.relationship_id == relationship.relationship_id
    
    def test_update_relationship(self, social_engine):
        """Test updating relationships after interactions."""
        relationship = social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.FRIEND,
            trust_level=0.5
        )
        
        # Positive interaction
        updated = social_engine.update_relationship(
            relationship_id=relationship.relationship_id,
            positive=True
        )
        
        assert updated is not None
        assert updated.interaction_count == 1
        assert updated.positive_interactions == 1
        assert updated.negative_interactions == 0
        assert updated.trust_level > 0.5  # Trust should increase
        
        # Negative interaction
        updated = social_engine.update_relationship(
            relationship_id=relationship.relationship_id,
            positive=False
        )
        
        assert updated.interaction_count == 2
        assert updated.positive_interactions == 1
        assert updated.negative_interactions == 1
        assert updated.trust_level < 0.55  # Trust should decrease
    
    def test_get_relationship_bidirectional(self, social_engine):
        """Test that relationships can be retrieved in either direction."""
        relationship = social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.7
        )
        
        # Retrieve in original order
        retrieved1 = social_engine.get_relationship("user123", "user456")
        assert retrieved1 is not None
        assert retrieved1.relationship_id == relationship.relationship_id
        
        # Retrieve in reverse order
        retrieved2 = social_engine.get_relationship("user456", "user123")
        assert retrieved2 is not None
        assert retrieved2.relationship_id == relationship.relationship_id
    
    def test_get_agent_relationships(self, social_engine):
        """Test getting all relationships for an agent."""
        # Create multiple relationships
        social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.FRIEND,
            trust_level=0.8
        )
        
        social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user789",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.6
        )
        
        social_engine.create_relationship(
            agent1_id="user456",
            agent2_id="user789",
            relationship_type=RelationshipType.ACQUAINTANCE,
            trust_level=0.4
        )
        
        # Get relationships for user123
        relationships = social_engine.get_agent_relationships("user123")
        assert len(relationships) == 2
        assert all("user123" in [r.agent1_id, r.agent2_id] for r in relationships)
    
    def test_record_interaction(self, social_engine):
        """Test recording social interactions."""
        # Create a relationship first
        relationship = social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.5
        )
        
        # Record interaction
        emotion1 = EmotionalState(
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.8,
            triggers=["Good collaboration"]
        )
        
        emotion2 = EmotionalState(
            agent_id="user456",
            primary_emotion=Emotion.JOY,
            intensity=0.7,
            triggers=["Productive discussion"]
        )
        
        interaction = social_engine.record_interaction(
            participants=["user123", "user456"],
            interaction_type="collaboration",
            context="Working on project together",
            norms_followed=[SocialNorm.COOPERATION, SocialNorm.RESPECT],
            norms_violated=[],
            emotional_outcomes={
                "user123": emotion1,
                "user456": emotion2
            },
            outcome="positive"
        )
        
        assert interaction.interaction_id is not None
        assert len(interaction.participants) == 2
        assert interaction.interaction_type == "collaboration"
        assert len(interaction.norms_followed) == 2
        assert len(interaction.norms_violated) == 0
        assert interaction.outcome == "positive"
        
        # Check that relationship was updated
        updated_rel = social_engine.get_relationship("user123", "user456")
        assert updated_rel.interaction_count == 1
        assert updated_rel.positive_interactions == 1
    
    def test_get_agent_interactions(self, social_engine):
        """Test getting interactions for an agent."""
        # Record multiple interactions
        for i in range(3):
            social_engine.record_interaction(
                participants=["user123", f"user{i}"],
                interaction_type="conversation",
                context=f"Discussion {i}",
                norms_followed=[SocialNorm.RESPECT],
                norms_violated=[],
                emotional_outcomes={},
                outcome="positive"
            )
        
        # Get interactions for user123
        interactions = social_engine.get_agent_interactions("user123", limit=10)
        assert len(interactions) == 3
        assert all("user123" in i.participants for i in interactions)
    
    def test_check_norm_compliance(self, social_engine):
        """Test checking social norm compliance."""
        interaction = SocialInteraction(
            participants=["user123", "user456"],
            interaction_type="conversation",
            context="Discussion",
            norms_followed=[SocialNorm.RESPECT, SocialNorm.POLITENESS],
            norms_violated=[SocialNorm.HONESTY],
            emotional_outcomes={},
            outcome="neutral"
        )
        
        compliance = social_engine.check_norm_compliance(interaction)
        
        assert compliance[SocialNorm.RESPECT] is True
        assert compliance[SocialNorm.POLITENESS] is True
        assert compliance[SocialNorm.HONESTY] is False
        assert compliance[SocialNorm.COOPERATION] is None  # Not applicable
    
    def test_suggest_norm_adherence(self, social_engine):
        """Test suggesting social norms for a context."""
        # Test collaboration context
        norms = social_engine.suggest_norm_adherence(
            context="Let's collaborate on this project",
            participants=["user123", "user456"]
        )
        
        assert SocialNorm.COOPERATION in norms
        assert SocialNorm.RESPECT in norms
        
        # Test emotional context
        norms = social_engine.suggest_norm_adherence(
            context="I understand you're feeling frustrated",
            participants=["user123"]
        )
        
        assert SocialNorm.EMPATHY in norms
    
    def test_facilitate_collaboration(self, social_engine):
        """Test facilitating collaborative problem solving."""
        # Create relationships with different trust levels
        social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.8
        )
        
        social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user789",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.7
        )
        
        social_engine.create_relationship(
            agent1_id="user456",
            agent2_id="user789",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.6
        )
        
        # Facilitate collaboration
        plan = social_engine.facilitate_collaboration(
            participants=["user123", "user456", "user789"],
            problem="Solve complex AI problem",
            context={"domain": "AI", "difficulty": "high"}
        )
        
        assert plan["problem"] == "Solve complex AI problem"
        assert len(plan["participants"]) == 3
        assert "roles" in plan
        assert "norms" in plan
        assert plan["average_trust"] > 0.6  # Should be around 0.7
        assert len(plan["recommendations"]) > 0
    
    def test_get_social_summary(self, social_engine):
        """Test getting social cognition summary."""
        # Create some data
        social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.FRIEND,
            trust_level=0.8
        )
        
        social_engine.create_relationship(
            agent1_id="user123",
            agent2_id="user789",
            relationship_type=RelationshipType.COLLEAGUE,
            trust_level=0.6
        )
        
        social_engine.recognize_emotion(
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.9,
            triggers=["Good news"]
        )
        
        social_engine.record_interaction(
            participants=["user123", "user456"],
            interaction_type="conversation",
            context="Chat",
            norms_followed=[SocialNorm.RESPECT],
            norms_violated=[],
            emotional_outcomes={},
            outcome="positive"
        )
        
        # Get summary
        summary = social_engine.get_social_summary("user123")
        
        assert summary["total_relationships"] == 2
        # Average trust is (0.81 + 0.6) / 2 = 0.705 because the first relationship
        # was updated with a positive interaction
        assert abs(summary["average_trust"] - 0.705) < 0.01
        assert summary["total_interactions"] == 1
        assert summary["positive_interactions"] == 1
        assert summary["positive_interaction_rate"] == 1.0
        assert "joy" in summary["emotion_distribution"]
        assert summary["relationship_types"][RelationshipType.FRIEND.value] == 1
        assert summary["relationship_types"][RelationshipType.COLLEAGUE.value] == 1
    
    def test_mental_state_serialization(self):
        """Test mental state serialization."""
        state = MentalStateModel(
            state_id="state123",
            agent_id="user123",
            state_type=MentalState.BELIEF,
            content="Test belief",
            confidence=0.8,
            evidence=["Evidence 1", "Evidence 2"]
        )
        
        # Serialize
        state_dict = state.to_dict()
        
        # Deserialize
        restored = MentalStateModel.from_dict(state_dict)
        
        assert restored.state_id == state.state_id
        assert restored.agent_id == state.agent_id
        assert restored.state_type == state.state_type
        assert restored.content == state.content
        assert restored.confidence == state.confidence
        assert restored.evidence == state.evidence
    
    def test_emotional_state_serialization(self):
        """Test emotional state serialization."""
        emotion = EmotionalState(
            emotion_id="emotion123",
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.9,
            secondary_emotions=[Emotion.SURPRISE],
            triggers=["Trigger 1", "Trigger 2"]
        )
        
        # Serialize
        emotion_dict = emotion.to_dict()
        
        # Deserialize
        restored = EmotionalState.from_dict(emotion_dict)
        
        assert restored.emotion_id == emotion.emotion_id
        assert restored.agent_id == emotion.agent_id
        assert restored.primary_emotion == emotion.primary_emotion
        assert restored.intensity == emotion.intensity
        assert restored.secondary_emotions == emotion.secondary_emotions
        assert restored.triggers == emotion.triggers
    
    def test_relationship_serialization(self):
        """Test relationship serialization."""
        relationship = SocialRelationship(
            relationship_id="rel123",
            agent1_id="user123",
            agent2_id="user456",
            relationship_type=RelationshipType.FRIEND,
            trust_level=0.8,
            interaction_count=10,
            positive_interactions=8,
            negative_interactions=2,
            shared_interests=["AI", "programming"]
        )
        
        # Serialize
        rel_dict = relationship.to_dict()
        
        # Deserialize
        restored = SocialRelationship.from_dict(rel_dict)
        
        assert restored.relationship_id == relationship.relationship_id
        assert restored.agent1_id == relationship.agent1_id
        assert restored.agent2_id == relationship.agent2_id
        assert restored.relationship_type == relationship.relationship_type
        assert restored.trust_level == relationship.trust_level
        assert restored.interaction_count == relationship.interaction_count
        assert restored.shared_interests == relationship.shared_interests
    
    def test_interaction_serialization(self):
        """Test interaction serialization."""
        emotion = EmotionalState(
            emotion_id="emotion123",
            agent_id="user123",
            primary_emotion=Emotion.JOY,
            intensity=0.8,
            triggers=["Good news"]
        )
        
        interaction = SocialInteraction(
            interaction_id="interaction123",
            participants=["user123", "user456"],
            interaction_type="conversation",
            context="Discussion",
            norms_followed=[SocialNorm.RESPECT, SocialNorm.POLITENESS],
            norms_violated=[],
            emotional_outcomes={"user123": emotion},
            outcome="positive"
        )
        
        # Serialize
        interaction_dict = interaction.to_dict()
        
        # Deserialize
        restored = SocialInteraction.from_dict(interaction_dict)
        
        assert restored.interaction_id == interaction.interaction_id
        assert restored.participants == interaction.participants
        assert restored.interaction_type == interaction.interaction_type
        assert restored.context == interaction.context
        assert restored.norms_followed == interaction.norms_followed
        assert restored.norms_violated == interaction.norms_violated
        assert restored.outcome == interaction.outcome


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
