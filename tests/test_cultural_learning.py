"""
Tests for Phase 21: Cultural Learning
"""

import pytest
import tempfile
import os
from app.cognition.cultural_learning import (
    CulturalLearningEngine,
    CulturalNorm,
    ObservedBehavior,
    CulturalPractice,
    ImitationAttempt,
    CulturalProfile,
    NormType,
    LearningMechanism,
    CulturalContext
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def engine(temp_db):
    """Create a cultural learning engine with temp database."""
    return CulturalLearningEngine(db_path=temp_db)


class TestCulturalLearning:
    """Test suite for cultural learning functionality."""
    
    def test_add_cultural_norm(self, engine):
        """Test adding a cultural norm."""
        norm = engine.add_cultural_norm(
            name="Handshake Greeting",
            description="Greeting others with a handshake",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL,
            region="Western",
            importance=0.8,
            prevalence=0.9,
            examples=["Firm handshake with eye contact", "Brief handshake with smile"],
            violations=["Refusing to shake hands", "Too weak or too strong grip"],
            related_norms=[]
        )
        
        assert norm.norm_id is not None
        assert norm.name == "Handshake Greeting"
        assert norm.norm_type == NormType.SOCIAL
        assert norm.context == CulturalContext.NATIONAL
        assert norm.region == "Western"
        assert norm.importance == 0.8
        assert norm.prevalence == 0.9
        assert len(norm.examples) == 2
        assert len(norm.violations) == 2
    
    def test_get_norm(self, engine):
        """Test getting a norm by ID."""
        norm = engine.add_cultural_norm(
            name="Test Norm",
            description="Test",
            norm_type=NormType.BEHAVIORAL,
            context=CulturalContext.ORGANIZATIONAL
        )
        
        retrieved = engine.get_norm(norm.norm_id)
        assert retrieved is not None
        assert retrieved.norm_id == norm.norm_id
        assert retrieved.name == "Test Norm"
    
    def test_get_nonexistent_norm(self, engine):
        """Test getting a nonexistent norm."""
        result = engine.get_norm("nonexistent_id")
        assert result is None
    
    def test_get_norms_by_type(self, engine):
        """Test getting norms by type."""
        # Add norms of different types
        engine.add_cultural_norm(
            name="Social Norm 1",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL
        )
        engine.add_cultural_norm(
            name="Social Norm 2",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL
        )
        engine.add_cultural_norm(
            name="Communication Norm",
            description="Test",
            norm_type=NormType.COMMUNICATION,
            context=CulturalContext.NATIONAL
        )
        
        # Get social norms
        social_norms = engine.get_norms_by_type(NormType.SOCIAL)
        assert len(social_norms) == 2
        assert all(n.norm_type == NormType.SOCIAL for n in social_norms)
        
        # Get communication norms
        comm_norms = engine.get_norms_by_type(NormType.COMMUNICATION)
        assert len(comm_norms) == 1
        assert comm_norms[0].norm_type == NormType.COMMUNICATION
    
    def test_get_norms_by_context(self, engine):
        """Test getting norms by context."""
        # Add norms in different contexts
        engine.add_cultural_norm(
            name="National Norm",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL
        )
        engine.add_cultural_norm(
            name="Organizational Norm 1",
            description="Test",
            norm_type=NormType.PROFESSIONAL,
            context=CulturalContext.ORGANIZATIONAL
        )
        engine.add_cultural_norm(
            name="Organizational Norm 2",
            description="Test",
            norm_type=NormType.PROFESSIONAL,
            context=CulturalContext.ORGANIZATIONAL
        )
        
        # Get national norms
        national = engine.get_norms_by_context(CulturalContext.NATIONAL)
        assert len(national) == 1
        assert national[0].context == CulturalContext.NATIONAL
        
        # Get organizational norms
        org = engine.get_norms_by_context(CulturalContext.ORGANIZATIONAL)
        assert len(org) == 2
        assert all(n.context == CulturalContext.ORGANIZATIONAL for n in org)
    
    def test_get_norms_by_region(self, engine):
        """Test getting norms by region."""
        # Add norms for different regions
        engine.add_cultural_norm(
            name="Japanese Norm 1",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL,
            region="Japan"
        )
        engine.add_cultural_norm(
            name="Japanese Norm 2",
            description="Test",
            norm_type=NormType.ETIQUETTE,
            context=CulturalContext.NATIONAL,
            region="Japan"
        )
        engine.add_cultural_norm(
            name="American Norm",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL,
            region="USA"
        )
        
        # Get Japanese norms
        japanese = engine.get_norms_by_region("Japan")
        assert len(japanese) == 2
        assert all(n.region == "Japan" for n in japanese)
        
        # Get American norms
        american = engine.get_norms_by_region("USA")
        assert len(american) == 1
        assert american[0].region == "USA"
    
    def test_record_observed_behavior(self, engine):
        """Test recording observed behavior."""
        observation = engine.record_observed_behavior(
            agent_id="person_123",
            behavior_type="greeting",
            description="Person bowed when meeting someone",
            context="Formal business meeting",
            outcome="Positive reception",
            social_response="Others bowed in return",
            cultural_norm_id=None
        )
        
        assert observation.observation_id is not None
        assert observation.agent_id == "person_123"
        assert observation.behavior_type == "greeting"
        assert observation.description == "Person bowed when meeting someone"
        assert observation.context == "Formal business meeting"
        assert observation.outcome == "Positive reception"
        assert observation.social_response == "Others bowed in return"
    
    def test_get_observations_by_agent(self, engine):
        """Test getting observations by agent."""
        # Add observations for different agents
        engine.record_observed_behavior(
            agent_id="agent_1",
            behavior_type="greeting",
            description="Test 1"
        )
        engine.record_observed_behavior(
            agent_id="agent_1",
            behavior_type="farewell",
            description="Test 2"
        )
        engine.record_observed_behavior(
            agent_id="agent_2",
            behavior_type="greeting",
            description="Test 3"
        )
        
        # Get observations for agent_1
        agent1_obs = engine.get_observations_by_agent("agent_1")
        assert len(agent1_obs) == 2
        assert all(o.agent_id == "agent_1" for o in agent1_obs)
        
        # Get observations for agent_2
        agent2_obs = engine.get_observations_by_agent("agent_2")
        assert len(agent2_obs) == 1
        assert agent2_obs[0].agent_id == "agent_2"
    
    def test_get_observations_by_type(self, engine):
        """Test getting observations by behavior type."""
        # Add observations of different types
        engine.record_observed_behavior(
            agent_id="agent_1",
            behavior_type="greeting",
            description="Test 1"
        )
        engine.record_observed_behavior(
            agent_id="agent_2",
            behavior_type="greeting",
            description="Test 2"
        )
        engine.record_observed_behavior(
            agent_id="agent_3",
            behavior_type="dining",
            description="Test 3"
        )
        
        # Get greeting observations
        greetings = engine.get_observations_by_type("greeting")
        assert len(greetings) == 2
        assert all(o.behavior_type == "greeting" for o in greetings)
        
        # Get dining observations
        dining = engine.get_observations_by_type("dining")
        assert len(dining) == 1
        assert dining[0].behavior_type == "dining"
    
    def test_add_cultural_practice(self, engine):
        """Test adding a cultural practice."""
        practice = engine.add_cultural_practice(
            name="Japanese Tea Ceremony",
            description="Traditional Japanese tea preparation ritual",
            context=CulturalContext.NATIONAL,
            region="Japan",
            category="ritual",
            steps=[
                "Prepare tea room",
                "Purify utensils",
                "Prepare matcha tea",
                "Serve to guests",
                "Clean utensils"
            ],
            participants=["host", "guests"],
            materials=["tea bowl", "whisk", "matcha powder", "hot water"],
            occasions=["formal gatherings", "cultural events"],
            variations=["formal ceremony", "informal gathering"],
            related_norms=[]
        )
        
        assert practice.practice_id is not None
        assert practice.name == "Japanese Tea Ceremony"
        assert practice.context == CulturalContext.NATIONAL
        assert practice.region == "Japan"
        assert practice.category == "ritual"
        assert len(practice.steps) == 5
        assert len(practice.participants) == 2
        assert len(practice.materials) == 4
        assert len(practice.occasions) == 2
        assert len(practice.variations) == 2
    
    def test_get_practice(self, engine):
        """Test getting a practice by ID."""
        practice = engine.add_cultural_practice(
            name="Test Practice",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="test"
        )
        
        retrieved = engine.get_practice(practice.practice_id)
        assert retrieved is not None
        assert retrieved.practice_id == practice.practice_id
        assert retrieved.name == "Test Practice"
    
    def test_get_nonexistent_practice(self, engine):
        """Test getting a nonexistent practice."""
        result = engine.get_practice("nonexistent_id")
        assert result is None
    
    def test_get_practices_by_category(self, engine):
        """Test getting practices by category."""
        # Add practices of different categories
        engine.add_cultural_practice(
            name="Handshake",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="greeting"
        )
        engine.add_cultural_practice(
            name="Bow",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="greeting"
        )
        engine.add_cultural_practice(
            name="Tea Ceremony",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="ritual"
        )
        
        # Get greeting practices
        greetings = engine.get_practices_by_category("greeting")
        assert len(greetings) == 2
        assert all(p.category == "greeting" for p in greetings)
        
        # Get ritual practices
        rituals = engine.get_practices_by_category("ritual")
        assert len(rituals) == 1
        assert rituals[0].category == "ritual"
    
    def test_get_practices_by_context(self, engine):
        """Test getting practices by context."""
        # Add practices in different contexts
        engine.add_cultural_practice(
            name="National Practice",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="test"
        )
        engine.add_cultural_practice(
            name="Professional Practice 1",
            description="Test",
            context=CulturalContext.PROFESSIONAL,
            category="test"
        )
        engine.add_cultural_practice(
            name="Professional Practice 2",
            description="Test",
            context=CulturalContext.PROFESSIONAL,
            category="test"
        )
        
        # Get national practices
        national = engine.get_practices_by_context(CulturalContext.NATIONAL)
        assert len(national) == 1
        assert national[0].context == CulturalContext.NATIONAL
        
        # Get professional practices
        professional = engine.get_practices_by_context(CulturalContext.PROFESSIONAL)
        assert len(professional) == 2
        assert all(p.context == CulturalContext.PROFESSIONAL for p in professional)
    
    def test_attempt_imitation(self, engine):
        """Test recording an imitation attempt."""
        attempt = engine.attempt_imitation(
            description="Attempted to bow like observed person",
            mechanism=LearningMechanism.IMITATION,
            observation_id=None,
            practice_id=None,
            success=True,
            feedback="Others responded positively",
            adjustments=["Adjusted depth of bow", "Maintained eye contact"]
        )
        
        assert attempt.attempt_id is not None
        assert attempt.description == "Attempted to bow like observed person"
        assert attempt.mechanism == LearningMechanism.IMITATION
        assert attempt.success is True
        assert attempt.feedback == "Others responded positively"
        assert len(attempt.adjustments) == 2
    
    def test_get_imitation_attempts(self, engine):
        """Test getting imitation attempts."""
        # Add multiple attempts
        engine.attempt_imitation(
            description="Attempt 1",
            mechanism=LearningMechanism.IMITATION,
            success=True
        )
        engine.attempt_imitation(
            description="Attempt 2",
            mechanism=LearningMechanism.OBSERVATION,
            success=False
        )
        engine.attempt_imitation(
            description="Attempt 3",
            mechanism=LearningMechanism.PARTICIPATION,
            success=True
        )
        
        # Get all attempts
        attempts = engine.get_imitation_attempts(limit=10)
        assert len(attempts) == 3
        
        # Get limited attempts
        limited = engine.get_imitation_attempts(limit=2)
        assert len(limited) == 2
    
    def test_get_or_create_profile(self, engine):
        """Test getting or creating a profile."""
        # Create new profile
        profile1 = engine.get_or_create_profile("agent_123")
        assert profile1 is not None
        assert profile1.agent_id == "agent_123"
        assert profile1.observations_count == 0
        assert profile1.imitations_count == 0
        
        # Get existing profile
        profile2 = engine.get_or_create_profile("agent_123")
        assert profile2.profile_id == profile1.profile_id
    
    def test_update_profile_norms(self, engine):
        """Test updating profile norms."""
        # Create profile
        profile = engine.get_or_create_profile("agent_123")
        
        # Add norms
        norm1 = engine.add_cultural_norm(
            name="Norm 1",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL
        )
        norm2 = engine.add_cultural_norm(
            name="Norm 2",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL
        )
        
        # Update profile
        updated = engine.update_profile_norms("agent_123", [norm1.norm_id, norm2.norm_id])
        
        assert len(updated.known_norms) == 2
        assert norm1.norm_id in updated.known_norms
        assert norm2.norm_id in updated.known_norms
        
        # Update again (should not duplicate)
        updated2 = engine.update_profile_norms("agent_123", [norm1.norm_id])
        assert len(updated2.known_norms) == 2  # Still 2, no duplicates
    
    def test_update_profile_practices(self, engine):
        """Test updating profile practices."""
        # Create profile
        profile = engine.get_or_create_profile("agent_123")
        
        # Add practices
        practice1 = engine.add_cultural_practice(
            name="Practice 1",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="test"
        )
        practice2 = engine.add_cultural_practice(
            name="Practice 2",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="test"
        )
        
        # Update profile
        updated = engine.update_profile_practices("agent_123", [practice1.practice_id, practice2.practice_id])
        
        assert len(updated.known_practices) == 2
        assert practice1.practice_id in updated.known_practices
        assert practice2.practice_id in updated.known_practices
        
        # Update again (should not duplicate)
        updated2 = engine.update_profile_practices("agent_123", [practice1.practice_id])
        assert len(updated2.known_practices) == 2  # Still 2, no duplicates
    
    def test_cultural_competence_calculation(self, engine):
        """Test cultural competence calculation."""
        # Create profile for "self" (the agent doing the learning)
        profile = engine.get_or_create_profile("self")
        initial_competence = profile.cultural_competence
        
        # Add successful imitations
        for i in range(5):
            engine.attempt_imitation(
                description=f"Attempt {i+1}",
                mechanism=LearningMechanism.IMITATION,
                success=True
            )
        
        # Get updated profile
        updated = engine.get_or_create_profile("self")
        
        # Competence should have increased
        assert updated.cultural_competence > initial_competence
        assert updated.imitations_count == 5
        assert updated.successful_imitations == 5
    
    def test_get_cultural_summary(self, engine):
        """Test getting cultural summary."""
        # Add some data
        engine.add_cultural_norm(
            name="Norm 1",
            description="Test",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL
        )
        engine.add_cultural_norm(
            name="Norm 2",
            description="Test",
            norm_type=NormType.COMMUNICATION,
            context=CulturalContext.NATIONAL
        )
        
        engine.record_observed_behavior(
            agent_id="agent_1",
            behavior_type="greeting",
            description="Test"
        )
        engine.record_observed_behavior(
            agent_id="agent_2",
            behavior_type="greeting",
            description="Test"
        )
        
        engine.add_cultural_practice(
            name="Practice 1",
            description="Test",
            context=CulturalContext.NATIONAL,
            category="greeting"
        )
        
        engine.attempt_imitation(
            description="Attempt 1",
            mechanism=LearningMechanism.IMITATION,
            success=True
        )
        engine.attempt_imitation(
            description="Attempt 2",
            mechanism=LearningMechanism.IMITATION,
            success=False
        )
        
        # Get summary
        summary = engine.get_cultural_summary()
        
        assert summary["total_norms"] == 2
        assert summary["norms_by_type"]["social"] == 1
        assert summary["norms_by_type"]["communication"] == 1
        assert summary["total_observations"] == 2
        assert summary["observations_by_type"]["greeting"] == 2
        assert summary["total_practices"] == 1
        assert summary["practices_by_category"]["greeting"] == 1
        assert summary["total_imitations"] == 2
        assert summary["successful_imitations"] == 1
        assert summary["imitation_success_rate"] == 0.5
        assert summary["total_profiles"] >= 1
    
    def test_cultural_norm_serialization(self):
        """Test cultural norm serialization."""
        norm = CulturalNorm(
            norm_id="norm123",
            name="Test Norm",
            description="Test description",
            norm_type=NormType.SOCIAL,
            context=CulturalContext.NATIONAL,
            region="Test Region",
            importance=0.8,
            prevalence=0.9,
            examples=["Example 1", "Example 2"],
            violations=["Violation 1"],
            related_norms=["norm456"]
        )
        
        # Serialize
        norm_dict = norm.to_dict()
        
        # Deserialize
        restored = CulturalNorm.from_dict(norm_dict)
        
        assert restored.norm_id == norm.norm_id
        assert restored.name == norm.name
        assert restored.description == norm.description
        assert restored.norm_type == norm.norm_type
        assert restored.context == norm.context
        assert restored.region == norm.region
        assert restored.importance == norm.importance
        assert restored.prevalence == norm.prevalence
        assert restored.examples == norm.examples
        assert restored.violations == norm.violations
        assert restored.related_norms == norm.related_norms
    
    def test_observed_behavior_serialization(self):
        """Test observed behavior serialization."""
        observation = ObservedBehavior(
            observation_id="obs123",
            agent_id="agent_123",
            behavior_type="greeting",
            description="Test description",
            context="Test context",
            outcome="Test outcome",
            social_response="Test response",
            cultural_norm_id="norm123",
            frequency=5
        )
        
        # Serialize
        obs_dict = observation.to_dict()
        
        # Deserialize
        restored = ObservedBehavior.from_dict(obs_dict)
        
        assert restored.observation_id == observation.observation_id
        assert restored.agent_id == observation.agent_id
        assert restored.behavior_type == observation.behavior_type
        assert restored.description == observation.description
        assert restored.context == observation.context
        assert restored.outcome == observation.outcome
        assert restored.social_response == observation.social_response
        assert restored.cultural_norm_id == observation.cultural_norm_id
        assert restored.frequency == observation.frequency
    
    def test_cultural_practice_serialization(self):
        """Test cultural practice serialization."""
        practice = CulturalPractice(
            practice_id="practice123",
            name="Test Practice",
            description="Test description",
            context=CulturalContext.NATIONAL,
            region="Test Region",
            category="greeting",
            steps=["Step 1", "Step 2", "Step 3"],
            participants=["host", "guest"],
            materials=["material1", "material2"],
            occasions=["occasion1"],
            variations=["variation1"],
            related_norms=["norm123"]
        )
        
        # Serialize
        practice_dict = practice.to_dict()
        
        # Deserialize
        restored = CulturalPractice.from_dict(practice_dict)
        
        assert restored.practice_id == practice.practice_id
        assert restored.name == practice.name
        assert restored.description == practice.description
        assert restored.context == practice.context
        assert restored.region == practice.region
        assert restored.category == practice.category
        assert restored.steps == practice.steps
        assert restored.participants == practice.participants
        assert restored.materials == practice.materials
        assert restored.occasions == practice.occasions
        assert restored.variations == practice.variations
        assert restored.related_norms == practice.related_norms
    
    def test_imitation_attempt_serialization(self):
        """Test imitation attempt serialization."""
        attempt = ImitationAttempt(
            attempt_id="attempt123",
            observation_id="obs123",
            practice_id="practice123",
            mechanism=LearningMechanism.IMITATION,
            description="Test description",
            success=True,
            feedback="Test feedback",
            adjustments=["adjustment1", "adjustment2"]
        )
        
        # Serialize
        attempt_dict = attempt.to_dict()
        
        # Deserialize
        restored = ImitationAttempt.from_dict(attempt_dict)
        
        assert restored.attempt_id == attempt.attempt_id
        assert restored.observation_id == attempt.observation_id
        assert restored.practice_id == attempt.practice_id
        assert restored.mechanism == attempt.mechanism
        assert restored.description == attempt.description
        assert restored.success == attempt.success
        assert restored.feedback == attempt.feedback
        assert restored.adjustments == attempt.adjustments
    
    def test_cultural_profile_serialization(self):
        """Test cultural profile serialization."""
        profile = CulturalProfile(
            profile_id="profile123",
            agent_id="agent_123",
            primary_context=CulturalContext.NATIONAL,
            primary_region="Test Region",
            known_norms=["norm1", "norm2"],
            known_practices=["practice1", "practice2"],
            adaptation_level=0.7,
            cultural_competence=0.8,
            observations_count=10,
            imitations_count=5,
            successful_imitations=4
        )
        
        # Serialize
        profile_dict = profile.to_dict()
        
        # Deserialize
        restored = CulturalProfile.from_dict(profile_dict)
        
        assert restored.profile_id == profile.profile_id
        assert restored.agent_id == profile.agent_id
        assert restored.primary_context == profile.primary_context
        assert restored.primary_region == profile.primary_region
        assert restored.known_norms == profile.known_norms
        assert restored.known_practices == profile.known_practices
        assert restored.adaptation_level == profile.adaptation_level
        assert restored.cultural_competence == profile.cultural_competence
        assert restored.observations_count == profile.observations_count
        assert restored.imitations_count == profile.imitations_count
        assert restored.successful_imitations == profile.successful_imitations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
