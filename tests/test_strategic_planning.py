"""
Tests for Phase 13: Long-Term Strategic Planning
"""

import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from app.cognition.strategic_planning import (
    StrategicPlanningEngine,
    StrategicPlan,
    Milestone,
    PlanStatus,
    MilestoneStatus,
    TimeHorizon
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
def planning_engine(temp_db):
    """Create a strategic planning engine with temp database."""
    return StrategicPlanningEngine(db_path=temp_db)


class TestStrategicPlanning:
    """Test suite for strategic planning functionality."""
    
    def test_create_strategic_plan(self, planning_engine):
        """Test creating a strategic plan."""
        plan = planning_engine.create_strategic_plan(
            name="Master Python Programming",
            description="Become proficient in Python over 6 months",
            vision="Expert-level Python developer capable of building complex systems",
            time_horizon=TimeHorizon.MEDIUM_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=180)).isoformat(),
            objectives=[
                "Learn Python fundamentals",
                "Master object-oriented programming",
                "Build 5 real-world projects",
                "Contribute to open source"
            ],
            key_results=[
                "Complete Python course with 90%+ score",
                "Build and deploy 5 applications",
                "Get 3 pull requests merged in popular repos"
            ],
            estimated_effort="high"
        )
        
        assert plan.plan_id is not None
        assert plan.name == "Master Python Programming"
        assert plan.status == PlanStatus.DRAFT
        assert len(plan.objectives) == 4
        assert len(plan.key_results) == 3
        
        # Verify it was saved
        retrieved = planning_engine.get_plan(plan.plan_id)
        assert retrieved is not None
        assert retrieved.name == plan.name
    
    def test_add_milestone(self, planning_engine):
        """Test adding milestones to a plan."""
        plan = planning_engine.create_strategic_plan(
            name="Learn Machine Learning",
            description="Master ML fundamentals",
            vision="ML Engineer",
            time_horizon=TimeHorizon.LONG_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            objectives=["Learn ML theory", "Build models", "Deploy to production"],
            key_results=["Complete 3 courses", "Build 5 models", "Deploy 2 models"]
        )
        
        # Add milestones
        m1 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Complete Linear Regression Module",
            description="Finish the linear regression course module",
            target_date=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            success_criteria=[
                "Complete all exercises",
                "Score 90%+ on quiz",
                "Build prediction model"
            ]
        )
        
        assert m1 is not None
        assert m1.milestone_id is not None
        assert m1.status == MilestoneStatus.PENDING
        
        # Add dependent milestone
        m2 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Complete Logistic Regression Module",
            description="Finish logistic regression after linear regression",
            target_date=(datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            success_criteria=["Complete exercises", "Build classifier"],
            dependencies=[m1.milestone_id]
        )
        
        assert m2 is not None
        assert m1.milestone_id in m2.dependencies
        
        # Verify plan was updated
        updated_plan = planning_engine.get_plan(plan.plan_id)
        assert updated_plan.milestones_total == 2
    
    def test_update_milestone_status(self, planning_engine):
        """Test updating milestone status and progress."""
        plan = planning_engine.create_strategic_plan(
            name="Fitness Goal",
            description="Get in shape",
            vision="Healthy lifestyle",
            time_horizon=TimeHorizon.SHORT_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
            objectives=["Exercise regularly", "Eat healthy"],
            key_results=["Lose 10kg", "Run 5km"]
        )
        
        milestone = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="First 5kg Loss",
            description="Lose first 5 kilograms",
            target_date=(datetime.now(timezone.utc) + timedelta(days=45)).isoformat(),
            success_criteria=["Weight down 5kg", "Maintain for 1 week"]
        )
        
        # Update progress
        success = planning_engine.update_milestone_status(
            plan_id=plan.plan_id,
            milestone_id=milestone.milestone_id,
            status=MilestoneStatus.IN_PROGRESS,
            progress=0.5
        )
        
        assert success
        
        updated_plan = planning_engine.get_plan(plan.plan_id)
        updated_milestone = next(m for m in updated_plan.milestones if m.milestone_id == milestone.milestone_id)
        assert updated_milestone.status == MilestoneStatus.IN_PROGRESS
        assert updated_milestone.progress == 0.5
        
        # Complete the milestone
        success = planning_engine.update_milestone_status(
            plan_id=plan.plan_id,
            milestone_id=milestone.milestone_id,
            status=MilestoneStatus.COMPLETED
        )
        
        assert success
        
        updated_plan = planning_engine.get_plan(plan.plan_id)
        updated_milestone = next(m for m in updated_plan.milestones if m.milestone_id == milestone.milestone_id)
        assert updated_milestone.status == MilestoneStatus.COMPLETED
        assert updated_milestone.progress == 1.0
        assert updated_milestone.actual_date is not None
        assert updated_plan.milestones_completed == 1
    
    def test_get_next_milestone(self, planning_engine):
        """Test getting the next milestone to work on."""
        plan = planning_engine.create_strategic_plan(
            name="Build Web App",
            description="Create a full-stack web application",
            vision="Full-stack developer",
            time_horizon=TimeHorizon.MEDIUM_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=120)).isoformat(),
            objectives=["Learn React", "Learn Node.js", "Deploy app"],
            key_results=["Complete React course", "Build API", "Deploy to cloud"]
        )
        
        m1 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Setup Development Environment",
            description="Install and configure all tools",
            target_date=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            success_criteria=["Node.js installed", "React installed", "IDE configured"]
        )
        
        m2 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Complete React Tutorial",
            description="Finish React course",
            target_date=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            success_criteria=["Complete all modules", "Build sample app"],
            dependencies=[m1.milestone_id]
        )
        
        m3 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Build Backend API",
            description="Create REST API with Node.js",
            target_date=(datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            success_criteria=["API endpoints working", "Database connected"],
            dependencies=[m1.milestone_id]
        )
        
        # First milestone should be next (no dependencies)
        next_milestone = planning_engine.get_next_milestone(plan.plan_id)
        assert next_milestone is not None
        assert next_milestone.milestone_id == m1.milestone_id
        
        # Complete first milestone
        planning_engine.update_milestone_status(
            plan_id=plan.plan_id,
            milestone_id=m1.milestone_id,
            status=MilestoneStatus.COMPLETED
        )
        
        # Now m2 or m3 should be next (both have dependencies met)
        next_milestone = planning_engine.get_next_milestone(plan.plan_id)
        assert next_milestone is not None
        assert next_milestone.milestone_id in [m2.milestone_id, m3.milestone_id]
    
    def test_list_plans_with_filters(self, planning_engine):
        """Test listing plans with various filters."""
        # Create multiple plans
        plan1 = planning_engine.create_strategic_plan(
            name="Short-term Goal",
            description="Quick win",
            vision="Immediate improvement",
            time_horizon=TimeHorizon.SHORT_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            objectives=["Quick objective"],
            key_results=["Quick result"]
        )
        plan1.status = PlanStatus.ACTIVE
        planning_engine._save_plan(plan1)
        
        plan2 = planning_engine.create_strategic_plan(
            name="Long-term Vision",
            description="Major initiative",
            vision="Transformative change",
            time_horizon=TimeHorizon.LONG_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            objectives=["Major objective"],
            key_results=["Major result"]
        )
        plan2.status = PlanStatus.ACTIVE
        planning_engine._save_plan(plan2)
        
        plan3 = planning_engine.create_strategic_plan(
            name="Completed Project",
            description="Already done",
            vision="Past achievement",
            time_horizon=TimeHorizon.MEDIUM_TERM,
            target_end_date=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            objectives=["Done objective"],
            key_results=["Done result"]
        )
        plan3.status = PlanStatus.COMPLETED
        planning_engine._save_plan(plan3)
        
        # Test filter by status
        active_plans = planning_engine.list_plans(status=PlanStatus.ACTIVE)
        assert len(active_plans) == 2
        
        completed_plans = planning_engine.list_plans(status=PlanStatus.COMPLETED)
        assert len(completed_plans) == 1
        
        # Test filter by time horizon
        long_term_plans = planning_engine.list_plans(time_horizon=TimeHorizon.LONG_TERM)
        assert len(long_term_plans) == 1
        assert long_term_plans[0].name == "Long-term Vision"
        
        # Test combined filters
        active_long_term = planning_engine.list_plans(
            status=PlanStatus.ACTIVE,
            time_horizon=TimeHorizon.LONG_TERM
        )
        assert len(active_long_term) == 1
    
    def test_balance_short_term_vs_long_term(self, planning_engine):
        """Test balancing short-term goals against long-term plans."""
        # Create long-term plans
        plan1 = planning_engine.create_strategic_plan(
            name="Learn AI",
            description="Master artificial intelligence",
            vision="AI Expert",
            time_horizon=TimeHorizon.LONG_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            objectives=["Learn ML", "Build AI projects"],
            key_results=["Complete 5 courses", "Build 3 AI apps"]
        )
        plan1.allocated_resources = {'percentage': 40}
        planning_engine._save_plan(plan1)
        
        plan2 = planning_engine.create_strategic_plan(
            name="Career Growth",
            description="Advance career",
            vision="Senior Engineer",
            time_horizon=TimeHorizon.LONG_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=730)).isoformat(),
            objectives=["Get promotion", "Lead projects"],
            key_results=["Promoted to Senior", "Lead 2 projects"]
        )
        plan2.allocated_resources = {'percentage': 30}
        planning_engine._save_plan(plan2)
        
        # Create short-term goals
        short_term_goals = [
            {
                'description': 'Fix critical bug in production',
                'priority': 0.9,
                'estimated_effort': 'medium'
            },
            {
                'description': 'Learn Python for AI development',
                'priority': 0.7,
                'estimated_effort': 'high'
            },
            {
                'description': 'Refactor legacy code',
                'priority': 0.5,
                'estimated_effort': 'high'
            }
        ]
        
        long_term_plans = [plan1, plan2]
        
        result = planning_engine.balance_short_term_vs_long_term(
            short_term_goals,
            long_term_plans
        )
        
        assert 'recommendations' in result
        assert 'long_term_allocation' in result
        assert 'short_term_allocation' in result
        assert 'balance_score' in result
        
        assert result['long_term_allocation'] == 70  # 40 + 30
        assert result['short_term_allocation'] == 30  # 100 - 70
        
        # High priority bug fix should be recommended
        bug_fix_rec = next(r for r in result['recommendations'] if 'bug' in r['goal']['description'].lower())
        assert bug_fix_rec['recommended'] is True
        
        # Python learning supports AI plan, should have boosted priority
        python_rec = next(r for r in result['recommendations'] if 'python' in r['goal']['description'].lower())
        assert python_rec['adjusted_priority'] > python_rec['goal']['priority']
    
    def test_adapt_strategy(self, planning_engine):
        """Test adapting a strategic plan."""
        plan = planning_engine.create_strategic_plan(
            name="Learn Spanish",
            description="Become fluent in Spanish",
            vision="Bilingual communicator",
            time_horizon=TimeHorizon.LONG_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            objectives=["Learn vocabulary", "Practice speaking", "Study grammar"],
            key_results=["Know 2000 words", "Hold 10-minute conversation", "Pass B2 exam"]
        )
        
        # Adapt the plan - extend timeline
        success = planning_engine.adapt_strategy(
            plan_id=plan.plan_id,
            reason="Progress slower than expected, need more time",
            changes={
                'target_end_date': (datetime.now(timezone.utc) + timedelta(days=540)).isoformat(),
                'priority': 0.7
            }
        )
        
        assert success
        
        updated_plan = planning_engine.get_plan(plan.plan_id)
        assert updated_plan.priority == 0.7
        # Target end date should be updated
        assert updated_plan.target_end_date != plan.target_end_date
    
    def test_get_strategic_overview(self, planning_engine):
        """Test getting strategic overview."""
        # Create several plans
        for i in range(3):
            plan = planning_engine.create_strategic_plan(
                name=f"Plan {i+1}",
                description=f"Description {i+1}",
                vision=f"Vision {i+1}",
                time_horizon=TimeHorizon.LONG_TERM if i == 0 else TimeHorizon.SHORT_TERM,
                target_end_date=(datetime.now(timezone.utc) + timedelta(days=100*(i+1))).isoformat(),
                objectives=[f"Objective {i+1}"],
                key_results=[f"Result {i+1}"]
            )
            
            # Set status before adding milestones
            if i < 2:
                plan.status = PlanStatus.ACTIVE
                planning_engine._save_plan(plan)
            
            # Add some milestones
            for j in range(2):
                planning_engine.add_milestone(
                    plan_id=plan.plan_id,
                    name=f"Milestone {i+1}.{j+1}",
                    description=f"Milestone description",
                    target_date=(datetime.now(timezone.utc) + timedelta(days=30*(j+1))).isoformat(),
                    success_criteria=["Criterion 1", "Criterion 2"]
                )
        
        # Complete some milestones
        plans = planning_engine.list_plans()
        planning_engine.update_milestone_status(
            plan_id=plans[0].plan_id,
            milestone_id=plans[0].milestones[0].milestone_id,
            status=MilestoneStatus.COMPLETED
        )
        
        overview = planning_engine.get_strategic_overview()
        
        assert overview['total_plans'] == 3
        assert overview['active_plans'] == 2
        assert overview['total_milestones'] == 6  # 3 plans * 2 milestones each
        assert overview['completed_milestones'] == 1
        assert overview['completion_rate'] == pytest.approx(1/6, rel=1e-2)
        assert 'plans_by_horizon' in overview
        assert len(overview['active_plan_names']) == 2
    
    def test_plan_serialization(self, planning_engine):
        """Test plan serialization and deserialization."""
        plan = planning_engine.create_strategic_plan(
            name="Test Serialization",
            description="Test that plans serialize correctly",
            vision="Test vision",
            time_horizon=TimeHorizon.MEDIUM_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=180)).isoformat(),
            objectives=["Obj 1", "Obj 2"],
            key_results=["KR 1", "KR 2", "KR 3"]
        )
        
        # Add milestones
        planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Milestone 1",
            description="First milestone",
            target_date=(datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            success_criteria=["Criterion A", "Criterion B"]
        )
        
        # Serialize
        plan_dict = plan.to_dict()
        
        # Deserialize
        restored_plan = StrategicPlan.from_dict(plan_dict)
        
        assert restored_plan.plan_id == plan.plan_id
        assert restored_plan.name == plan.name
        assert restored_plan.time_horizon == plan.time_horizon
        assert len(restored_plan.objectives) == len(plan.objectives)
        assert len(restored_plan.milestones) == len(plan.milestones)
    
    def test_milestone_dependencies(self, planning_engine):
        """Test milestone dependency tracking."""
        plan = planning_engine.create_strategic_plan(
            name="Dependency Test",
            description="Test milestone dependencies",
            vision="Test",
            time_horizon=TimeHorizon.SHORT_TERM,
            target_end_date=(datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
            objectives=["Test dependencies"],
            key_results=["All milestones completed in order"]
        )
        
        # Create chain of dependencies: m1 -> m2 -> m3
        m1 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Foundation",
            description="Build foundation",
            target_date=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            success_criteria=["Foundation complete"]
        )
        
        m2 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Structure",
            description="Build structure",
            target_date=(datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            success_criteria=["Structure complete"],
            dependencies=[m1.milestone_id]
        )
        
        m3 = planning_engine.add_milestone(
            plan_id=plan.plan_id,
            name="Finishing",
            description="Add finishing touches",
            target_date=(datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
            success_criteria=["Project complete"],
            dependencies=[m2.milestone_id]
        )
        
        # Initially, only m1 should be available
        next_m = planning_engine.get_next_milestone(plan.plan_id)
        assert next_m.milestone_id == m1.milestone_id
        
        # Complete m1
        planning_engine.update_milestone_status(
            plan_id=plan.plan_id,
            milestone_id=m1.milestone_id,
            status=MilestoneStatus.COMPLETED
        )
        
        # Now m2 should be available
        next_m = planning_engine.get_next_milestone(plan.plan_id)
        assert next_m.milestone_id == m2.milestone_id
        
        # Complete m2
        planning_engine.update_milestone_status(
            plan_id=plan.plan_id,
            milestone_id=m2.milestone_id,
            status=MilestoneStatus.COMPLETED
        )
        
        # Now m3 should be available
        next_m = planning_engine.get_next_milestone(plan.plan_id)
        assert next_m.milestone_id == m3.milestone_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
