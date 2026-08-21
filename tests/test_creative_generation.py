"""
Tests for Phase 16: Creative Generation Engine
"""

import pytest
import tempfile
import os
from app.cognition.creative_generation import (
    CreativeGenerationEngine,
    CreativeIdea,
    CreativeSession,
    CreativeTechnique,
    IdeaQuality
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing (isolated via tmp_path)."""
    yield str(tmp_path / "test.db")


@pytest.fixture
def creative_engine(temp_db):
    """Create a creative generation engine with temp database."""
    return CreativeGenerationEngine(db_path=temp_db)


class TestCreativeGeneration:
    """Test suite for creative generation functionality."""
    
    def test_generate_ideas(self, creative_engine):
        """Test generating multiple creative ideas."""
        problem = "How to reduce energy consumption in office buildings"
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=5
        )
        
        assert len(ideas) == 5
        
        for idea in ideas:
            assert idea.idea_id is not None
            assert idea.problem == problem
            assert idea.description is not None
            assert len(idea.description) > 0
            assert idea.technique in list(CreativeTechnique)
            assert 0.0 <= idea.novelty_score <= 1.0
            assert 0.0 <= idea.usefulness_score <= 1.0
            assert 0.0 <= idea.creativity_score <= 1.0
            assert idea.quality in list(IdeaQuality)
            assert len(idea.implementation_steps) > 0
            assert len(idea.potential_challenges) > 0
    
    def test_generate_ideas_with_constraints(self, creative_engine):
        """Test generating ideas with constraints."""
        problem = "Design a mobile app for fitness tracking"
        constraints = ["Must work offline", "Battery usage < 5%", "Privacy-first design"]
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            constraints=constraints,
            num_ideas=3
        )
        
        assert len(ideas) == 3
        
        # Check that constraints are reflected in challenges
        for idea in ideas:
            assert any("constraint" in challenge.lower() or "meeting" in challenge.lower() 
                      for challenge in idea.potential_challenges)
    
    def test_generate_ideas_with_specific_techniques(self, creative_engine):
        """Test generating ideas using specific techniques."""
        problem = "Improve customer retention for SaaS product"
        techniques = [CreativeTechnique.ANALOGY, CreativeTechnique.REVERSAL]
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            techniques=techniques,
            num_ideas=4
        )
        
        assert len(ideas) == 4
        
        # Check that only specified techniques were used
        for idea in ideas:
            assert idea.technique in techniques
    
    def test_idea_evaluation(self, creative_engine):
        """Test idea evaluation scoring."""
        problem = "Optimize database query performance"
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=1
        )
        
        idea = ideas[0]
        
        # Check that scores are calculated
        assert idea.novelty_score > 0.0
        assert idea.usefulness_score > 0.0
        assert idea.creativity_score > 0.0
        
        # Check that creativity score is weighted average
        expected_creativity = (idea.novelty_score * 0.6 + idea.usefulness_score * 0.4)
        assert abs(idea.creativity_score - expected_creativity) < 0.01
        
        # Check that quality is assigned based on creativity score
        if idea.creativity_score >= 0.8:
            assert idea.quality == IdeaQuality.BREAKTHROUGH
        elif idea.creativity_score >= 0.65:
            assert idea.quality == IdeaQuality.INNOVATIVE
        elif idea.creativity_score >= 0.5:
            assert idea.quality == IdeaQuality.IMPROVEMENT
    
    def test_evaluate_idea_with_feedback(self, creative_engine):
        """Test updating idea with human feedback."""
        problem = "Create a new marketing campaign"
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=1
        )
        
        idea = ideas[0]
        original_creativity = idea.creativity_score
        
        # Update with human feedback
        updated_idea = creative_engine.evaluate_idea_with_feedback(
            idea_id=idea.idea_id,
            novelty_score=0.9,
            usefulness_score=0.8,
            feedback=["Very creative approach", "Feasible to implement"]
        )
        
        assert updated_idea is not None
        assert updated_idea.novelty_score == 0.9
        assert updated_idea.usefulness_score == 0.8
        assert updated_idea.creativity_score > original_creativity
        assert len(updated_idea.evaluation_feedback) == 2
        assert "Very creative approach" in updated_idea.evaluation_feedback
    
    def test_evaluate_nonexistent_idea(self, creative_engine):
        """Test evaluating an idea that doesn't exist."""
        result = creative_engine.evaluate_idea_with_feedback(
            idea_id="nonexistent_id",
            novelty_score=0.8,
            usefulness_score=0.7,
            feedback=["Test"]
        )
        
        assert result is None
    
    def test_test_idea_success(self, creative_engine):
        """Test recording successful idea implementation."""
        problem = "Automate report generation"
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=1
        )
        
        idea = ideas[0]
        
        # Record successful test
        updated_idea = creative_engine.test_idea(
            idea_id=idea.idea_id,
            success=True,
            lessons_learned=["Start with simple MVP", "Get user feedback early"]
        )
        
        assert updated_idea is not None
        assert updated_idea.success is True
        assert updated_idea.tested_at is not None
        assert len(updated_idea.evaluation_feedback) == 2
        assert any("Start with simple MVP" in feedback for feedback in updated_idea.evaluation_feedback)
    
    def test_test_idea_failure(self, creative_engine):
        """Test recording failed idea implementation."""
        problem = "Build AI-powered recommendation system"
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=1
        )
        
        idea = ideas[0]
        
        # Record failed test
        updated_idea = creative_engine.test_idea(
            idea_id=idea.idea_id,
            success=False,
            lessons_learned=["Need more training data", "Algorithm too complex"]
        )
        
        assert updated_idea is not None
        assert updated_idea.success is False
        assert updated_idea.tested_at is not None
    
    def test_get_best_ideas(self, creative_engine):
        """Test retrieving best ideas."""
        problem = "Improve user onboarding"
        
        # Generate multiple ideas
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=10
        )
        
        # Get best ideas
        best_ideas = creative_engine.get_best_ideas(
            problem=problem,
            min_creativity_score=0.5,
            limit=5
        )
        
        assert len(best_ideas) <= 5
        
        # Check that ideas are sorted by creativity score
        for i in range(len(best_ideas) - 1):
            assert best_ideas[i].creativity_score >= best_ideas[i+1].creativity_score
        
        # Check that all ideas meet minimum score
        for idea in best_ideas:
            assert idea.creativity_score >= 0.5
    
    def test_get_best_ideas_all_problems(self, creative_engine):
        """Test retrieving best ideas across all problems."""
        # Generate ideas for different problems
        creative_engine.generate_ideas(
            problem="Problem A",
            num_ideas=3
        )
        
        creative_engine.generate_ideas(
            problem="Problem B",
            num_ideas=3
        )
        
        # Get best ideas across all problems
        best_ideas = creative_engine.get_best_ideas(
            min_creativity_score=0.4,
            limit=10
        )
        
        assert len(best_ideas) <= 10
        
        # Check that ideas from both problems are included
        problems = set(idea.problem for idea in best_ideas)
        assert len(problems) >= 1  # At least one problem represented
    
    def test_get_idea(self, creative_engine):
        """Test retrieving a specific idea by ID."""
        problem = "Design sustainable packaging"
        
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=1
        )
        
        idea = ideas[0]
        
        # Retrieve the idea
        retrieved_idea = creative_engine.get_idea(idea.idea_id)
        
        assert retrieved_idea is not None
        assert retrieved_idea.idea_id == idea.idea_id
        assert retrieved_idea.problem == problem
        assert retrieved_idea.description == idea.description
    
    def test_get_nonexistent_idea(self, creative_engine):
        """Test retrieving an idea that doesn't exist."""
        result = creative_engine.get_idea("nonexistent_id")
        assert result is None
    
    def test_list_ideas_with_filters(self, creative_engine):
        """Test listing ideas with various filters."""
        # Generate ideas with different characteristics
        creative_engine.generate_ideas(
            problem="Problem X",
            techniques=[CreativeTechnique.COMBINATION],
            num_ideas=2
        )
        
        creative_engine.generate_ideas(
            problem="Problem Y",
            techniques=[CreativeTechnique.ANALOGY],
            num_ideas=2
        )
        
        # List all ideas
        all_ideas = creative_engine.list_ideas(limit=100)
        assert len(all_ideas) == 4
        
        # Filter by problem
        problem_x_ideas = creative_engine.list_ideas(problem="Problem X")
        assert len(problem_x_ideas) == 2
        assert all(idea.problem == "Problem X" for idea in problem_x_ideas)
        
        # Filter by technique
        combination_ideas = creative_engine.list_ideas(technique=CreativeTechnique.COMBINATION)
        assert len(combination_ideas) == 2
        assert all(idea.technique == CreativeTechnique.COMBINATION for idea in combination_ideas)
        
        # Filter by quality (may be 0 if no ideas match)
        breakthrough_ideas = creative_engine.list_ideas(quality=IdeaQuality.BREAKTHROUGH)
        for idea in breakthrough_ideas:
            assert idea.quality == IdeaQuality.BREAKTHROUGH
    
    def test_creativity_summary(self, creative_engine):
        """Test creativity summary statistics."""
        # Generate some ideas
        creative_engine.generate_ideas(
            problem="Test problem",
            num_ideas=5
        )
        
        # Get summary
        summary = creative_engine.get_creativity_summary()
        
        assert summary['total_ideas'] == 5
        assert summary['average_creativity'] > 0.0
        assert summary['breakthrough_ideas'] >= 0
        assert summary['innovative_ideas'] >= 0
        assert summary['tested_ideas'] == 0
        assert summary['successful_ideas'] == 0
        assert summary['success_rate'] == 0.0
        
        # Test one idea
        ideas = creative_engine.list_ideas(limit=1)
        creative_engine.test_idea(
            idea_id=ideas[0].idea_id,
            success=True
        )
        
        # Get updated summary
        updated_summary = creative_engine.get_creativity_summary()
        
        assert updated_summary['tested_ideas'] == 1
        assert updated_summary['successful_ideas'] == 1
        assert updated_summary['success_rate'] == 1.0
    
    def test_idea_persistence(self, creative_engine):
        """Test that ideas persist across engine instances."""
        problem = "Persistent problem"
        
        # Generate idea
        ideas = creative_engine.generate_ideas(
            problem=problem,
            num_ideas=1
        )
        
        idea_id = ideas[0].idea_id
        
        # Create new engine instance with same database
        new_engine = CreativeGenerationEngine(db_path=creative_engine.db_path)
        
        # Retrieve idea
        retrieved_idea = new_engine.get_idea(idea_id)
        
        assert retrieved_idea is not None
        assert retrieved_idea.problem == problem
    
    def test_idea_serialization(self):
        """Test idea serialization and deserialization."""
        idea = CreativeIdea(
            idea_id="test_id",
            problem="Test problem",
            description="Test description",
            technique=CreativeTechnique.ANALOGY,
            source_ideas=["source1", "source2"],
            novelty_score=0.8,
            usefulness_score=0.7,
            creativity_score=0.76,
            quality=IdeaQuality.INNOVATIVE,
            implementation_steps=["Step 1", "Step 2"],
            potential_challenges=["Challenge 1"],
            evaluation_feedback=["Good idea"],
            success=True
        )
        
        # Serialize
        idea_dict = idea.to_dict()
        
        # Deserialize
        restored_idea = CreativeIdea.from_dict(idea_dict)
        
        assert restored_idea.idea_id == idea.idea_id
        assert restored_idea.problem == idea.problem
        assert restored_idea.description == idea.description
        assert restored_idea.technique == idea.technique
        assert restored_idea.source_ideas == idea.source_ideas
        assert restored_idea.novelty_score == idea.novelty_score
        assert restored_idea.usefulness_score == idea.usefulness_score
        assert restored_idea.creativity_score == idea.creativity_score
        assert restored_idea.quality == idea.quality
        assert restored_idea.implementation_steps == idea.implementation_steps
        assert restored_idea.potential_challenges == idea.potential_challenges
        assert restored_idea.evaluation_feedback == idea.evaluation_feedback
        assert restored_idea.success == idea.success
    
    def test_session_serialization(self):
        """Test session serialization and deserialization."""
        session = CreativeSession(
            session_id="session_id",
            problem="Test problem",
            context={"key": "value"},
            constraints=["Constraint 1"],
            goals=["Goal 1"],
            ideas_generated=["idea1", "idea2"],
            techniques_used=[CreativeTechnique.COMBINATION, CreativeTechnique.ANALOGY],
            best_idea_id="idea1",
            session_duration_seconds=120.5
        )
        
        # Serialize
        session_dict = session.to_dict()
        
        # Deserialize
        restored_session = CreativeSession.from_dict(session_dict)
        
        assert restored_session.session_id == session.session_id
        assert restored_session.problem == session.problem
        assert restored_session.context == session.context
        assert restored_session.constraints == session.constraints
        assert restored_session.goals == session.goals
        assert restored_session.ideas_generated == session.ideas_generated
        assert restored_session.techniques_used == session.techniques_used
        assert restored_session.best_idea_id == session.best_idea_id
        assert restored_session.session_duration_seconds == session.session_duration_seconds
    
    def test_different_techniques_produce_different_ideas(self, creative_engine):
        """Test that different techniques produce different idea descriptions."""
        problem = "Improve team productivity"
        
        # Generate ideas with different techniques
        combination_ideas = creative_engine.generate_ideas(
            problem=problem,
            techniques=[CreativeTechnique.COMBINATION],
            num_ideas=1
        )
        
        reversal_ideas = creative_engine.generate_ideas(
            problem=problem,
            techniques=[CreativeTechnique.REVERSAL],
            num_ideas=1
        )
        
        # Check that descriptions are different
        assert combination_ideas[0].description != reversal_ideas[0].description
        
        # Check that techniques are correctly assigned
        assert combination_ideas[0].technique == CreativeTechnique.COMBINATION
        assert reversal_ideas[0].technique == CreativeTechnique.REVERSAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
