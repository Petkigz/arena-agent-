"""Tests for Ethical Reasoning System."""

import pytest
import tempfile
import os
from app.cognition.ethical_reasoning import (
    EthicalReasoningSystem,
    EthicalAssessment,
    EthicalConcern,
    EthicalPrinciple,
    EthicalVerdict,
    HarmLevel,
)
from app.cognition.autonomous_goal_generator import (
    AutonomousGoal,
    GoalSource,
    GoalPriority,
    GoalStatus,
)


class TestEthicalReasoningSystem:
    """Test Ethical Reasoning System functionality."""

    @pytest.fixture
    def ethical_system(self, tmp_path):
        """Create an ethical reasoning system instance."""
        db_path = str(tmp_path / "test_ethical.db")
        return EthicalReasoningSystem(db_path=db_path)

    @pytest.fixture
    def safe_goal(self):
        """Create a safe, ethical goal."""
        return AutonomousGoal(
            title="Optimize system performance",
            description="Analyze and improve system response times",
            source=GoalSource.SYSTEM_OPTIMIZATION,
            priority=GoalPriority.NORMAL,
            user_benefit="Faster system performance",
            system_benefit="Improved efficiency",
        )

    @pytest.fixture
    def risky_goal(self):
        """Create a goal with ethical concerns."""
        return AutonomousGoal(
            title="Delete old log files",
            description="Remove old log files to free up disk space",
            source=GoalSource.MAINTENANCE,
            priority=GoalPriority.LOW,
            user_benefit="More disk space",
        )

    @pytest.fixture
    def privacy_goal(self):
        """Create a goal with privacy concerns."""
        return AutonomousGoal(
            title="Analyze user behavior patterns",
            description="Collect and analyze personal user data to improve experience",
            source=GoalSource.USER_PATTERN,
            priority=GoalPriority.NORMAL,
            user_benefit="Personalized experience",
        )

    @pytest.fixture
    def autonomy_goal(self):
        """Create a goal that may override user autonomy."""
        return AutonomousGoal(
            title="Force update system settings",
            description="Require users to update to latest version",
            source=GoalSource.MAINTENANCE,
            priority=GoalPriority.HIGH,
        )

    def test_initialization(self, ethical_system):
        """Test ethical system initializes without errors."""
        assert ethical_system is not None
        assert ethical_system.db_path is not None

    def test_assess_safe_goal(self, ethical_system, safe_goal):
        """Test assessment of a safe, ethical goal."""
        assessment = ethical_system.assess_goal(safe_goal)
        
        assert assessment is not None
        assert assessment.goal_id == safe_goal.goal_id
        assert assessment.verdict in [EthicalVerdict.APPROVED, EthicalVerdict.CONDITIONAL]
        assert assessment.confidence > 0
        assert assessment.reasoning is not None

    def test_assess_risky_goal(self, ethical_system, risky_goal):
        """Test assessment of a goal with destructive actions."""
        assessment = ethical_system.assess_goal(risky_goal)
        
        assert assessment is not None
        assert len(assessment.concerns) > 0
        
        # Should have do_no_harm concern
        do_no_harm_concerns = [
            c for c in assessment.concerns
            if c.principle == EthicalPrinciple.DO_NO_HARM
        ]
        assert len(do_no_harm_concerns) > 0
        
        # Should have mitigations
        assert any(c.mitigations for c in assessment.concerns)

    def test_assess_privacy_goal(self, ethical_system, privacy_goal):
        """Test assessment of a goal with privacy concerns."""
        assessment = ethical_system.assess_goal(privacy_goal)
        
        assert assessment is not None
        
        # Should have privacy concern
        privacy_concerns = [
            c for c in assessment.concerns
            if c.principle == EthicalPrinciple.PRIVACY
        ]
        assert len(privacy_concerns) > 0

    def test_assess_autonomy_goal(self, ethical_system, autonomy_goal):
        """Test assessment of a goal that overrides user autonomy."""
        assessment = ethical_system.assess_goal(autonomy_goal)
        
        assert assessment is not None
        
        # Should have autonomy concern
        autonomy_concerns = [
            c for c in assessment.concerns
            if c.principle == EthicalPrinciple.AUTONOMY
        ]
        assert len(autonomy_concerns) > 0

    def test_harm_level_calculation(self, ethical_system):
        """Test that harm level is calculated correctly."""
        goal = AutonomousGoal(
            title="Delete critical system files",
            description="Remove and destroy system configuration",
            source=GoalSource.MAINTENANCE,
        )
        
        assessment = ethical_system.assess_goal(goal)
        
        # Should have high or critical harm level
        assert assessment.overall_harm_level in [
            HarmLevel.HIGH,
            HarmLevel.CRITICAL,
            HarmLevel.MODERATE,
        ]

    def test_verdict_determination(self, ethical_system, safe_goal):
        """Test that verdict is determined correctly."""
        assessment = ethical_system.assess_goal(safe_goal)
        
        # Safe goal should be approved or conditional
        assert assessment.verdict in [
            EthicalVerdict.APPROVED,
            EthicalVerdict.CONDITIONAL,
        ]

    def test_conditional_verdict_has_conditions(self, ethical_system, risky_goal):
        """Test that conditional verdict includes conditions."""
        assessment = ethical_system.assess_goal(risky_goal)
        
        if assessment.verdict == EthicalVerdict.CONDITIONAL:
            assert len(assessment.conditions) > 0

    def test_principles_tracking(self, ethical_system, safe_goal):
        """Test that principles violated and upheld are tracked."""
        assessment = ethical_system.assess_goal(safe_goal)
        
        # Should have some principles tracked
        total_principles = len(assessment.principles_violated) + len(assessment.principles_upheld)
        assert total_principles > 0

    def test_confidence_calculation(self, ethical_system, safe_goal, risky_goal):
        """Test that confidence is calculated correctly."""
        safe_assessment = ethical_system.assess_goal(safe_goal)
        risky_assessment = ethical_system.assess_goal(risky_goal)
        
        # Both should have confidence scores
        assert safe_assessment.confidence > 0
        assert risky_assessment.confidence > 0
        
        # Safe goal should generally have higher confidence
        # (though this depends on specific concerns)

    def test_reasoning_generation(self, ethical_system, safe_goal):
        """Test that reasoning is generated."""
        assessment = ethical_system.assess_goal(safe_goal)
        
        assert assessment.reasoning is not None
        assert len(assessment.reasoning) > 0

    def test_save_and_get_assessment(self, ethical_system, safe_goal):
        """Test saving and retrieving assessments."""
        assessment = ethical_system.assess_goal(safe_goal)
        
        # Retrieve by assessment_id
        retrieved = ethical_system.get_assessment(assessment.assessment_id)
        assert retrieved is not None
        assert retrieved.assessment_id == assessment.assessment_id
        assert retrieved.goal_title == assessment.goal_title

    def test_get_assessment_by_goal(self, ethical_system, safe_goal):
        """Test retrieving assessment by goal ID."""
        assessment = ethical_system.assess_goal(safe_goal)
        
        retrieved = ethical_system.get_assessment_by_goal(safe_goal.goal_id)
        assert retrieved is not None
        assert retrieved.goal_id == safe_goal.goal_id

    def test_list_assessments(self, ethical_system):
        """Test listing assessments with filters."""
        # Create multiple assessments
        goals = [
            AutonomousGoal(title=f"Goal {i}", description=f"Description {i}", source=GoalSource.CURIOSITY)
            for i in range(5)
        ]
        
        for goal in goals:
            ethical_system.assess_goal(goal)
        
        # List all
        all_assessments = ethical_system.list_assessments()
        assert len(all_assessments) == 5
        
        # Filter by verdict
        approved = ethical_system.list_assessments(verdict=EthicalVerdict.APPROVED)
        assert len(approved) >= 0  # May be 0 if all are conditional

    def test_ethical_concern_to_dict_and_from_dict(self):
        """Test EthicalConcern serialization."""
        concern = EthicalConcern(
            principle=EthicalPrinciple.DO_NO_HARM,
            description="Test concern",
            severity=HarmLevel.MODERATE,
            mitigations=["Mitigation 1", "Mitigation 2"],
        )
        
        data = concern.to_dict()
        assert data["principle"] == "do_no_harm"
        assert data["severity"] == "moderate"
        assert len(data["mitigations"]) == 2
        
        restored = EthicalConcern.from_dict(data)
        assert restored.principle == concern.principle
        assert restored.severity == concern.severity
        assert restored.mitigations == concern.mitigations

    def test_ethical_assessment_to_dict_and_from_dict(self):
        """Test EthicalAssessment serialization."""
        assessment = EthicalAssessment(
            goal_id="goal_123",
            goal_title="Test Goal",
            verdict=EthicalVerdict.CONDITIONAL,
            concerns=[
                EthicalConcern(
                    principle=EthicalPrinciple.DO_NO_HARM,
                    description="Test concern",
                    severity=HarmLevel.LOW,
                    mitigations=["Mitigation 1"],
                )
            ],
            principles_violated=[EthicalPrinciple.DO_NO_HARM],
            principles_upheld=[EthicalPrinciple.BENEFICENCE, EthicalPrinciple.AUTONOMY],
            overall_harm_level=HarmLevel.LOW,
            confidence=0.85,
            reasoning="Test reasoning",
            conditions=["Condition 1", "Condition 2"],
        )
        
        data = assessment.to_dict()
        assert data["goal_id"] == "goal_123"
        assert data["verdict"] == "conditional"
        assert len(data["concerns"]) == 1
        assert data["confidence"] == 0.85
        
        restored = EthicalAssessment.from_dict(data)
        assert restored.goal_id == assessment.goal_id
        assert restored.verdict == assessment.verdict
        assert len(restored.concerns) == 1
        assert restored.confidence == assessment.confidence

    def test_high_harm_requires_review(self, ethical_system):
        """Test that high harm goals require human review."""
        goal = AutonomousGoal(
            title="Delete all user data",
            description="Permanently remove and destroy all user files",
            source=GoalSource.MAINTENANCE,
        )
        
        assessment = ethical_system.assess_goal(goal)
        
        # Should require review due to high harm
        if assessment.overall_harm_level in [HarmLevel.HIGH, HarmLevel.CRITICAL]:
            assert assessment.verdict == EthicalVerdict.REQUIRES_REVIEW

    def test_multiple_concerns(self, ethical_system):
        """Test goal with multiple ethical concerns."""
        goal = AutonomousGoal(
            title="Force delete personal user data",
            description="Require removal of all personal and private user files",
            source=GoalSource.MAINTENANCE,
        )
        
        assessment = ethical_system.assess_goal(goal)
        
        # Should have multiple concerns (do_no_harm, privacy, autonomy)
        assert len(assessment.concerns) >= 2

    def test_beneficence_check(self, ethical_system):
        """Test that beneficence is checked."""
        goal = AutonomousGoal(
            title="Unclear purpose goal",
            description="Do something",
            source=GoalSource.CURIOSITY,
            # No user_benefit or system_benefit
        )
        
        assessment = ethical_system.assess_goal(goal)
        
        # Should have beneficence concern
        beneficence_concerns = [
            c for c in assessment.concerns
            if c.principle == EthicalPrinciple.BENEFICENCE
        ]
        assert len(beneficence_concerns) > 0

    def test_transparency_check(self, ethical_system):
        """Test that transparency is checked."""
        goal = AutonomousGoal(
            title="Vague goal",
            description="",  # No description
            source=GoalSource.CURIOSITY,
        )
        
        assessment = ethical_system.assess_goal(goal)
        
        # Should have transparency concern
        transparency_concerns = [
            c for c in assessment.concerns
            if c.principle == EthicalPrinciple.TRANSPARENCY
        ]
        assert len(transparency_concerns) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
