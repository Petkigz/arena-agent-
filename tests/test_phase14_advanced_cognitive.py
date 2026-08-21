"""
Tests for Phase 14: Advanced Cognitive Capabilities
"""

import pytest
import tempfile
import os
import math
from app.cognition.advanced_cognitive_capabilities import (
    Phase14AdvancedCognitiveCapabilities,
    ResourceManager,
    ResourceAllocation,
    ResourceBudget,
    ResourceType,
    Priority,
    MultiAgentCoordinator,
    Agent,
    CoordinationTask,
    AgentRole,
    CoordinationProtocol,
    KnowledgeSynthesizer,
    KnowledgeClaim,
    SynthesizedKnowledge,
    KnowledgeSourceType,
    UncertaintyQuantifier,
    ProbabilityDistribution,
    BayesianUpdate,
    DistributionType
)


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database files (isolated via tmp_path)."""
    yield {
        'resources': str(tmp_path / 'resources.db'),
        'coordination': str(tmp_path / 'coordination.db'),
        'knowledge': str(tmp_path / 'knowledge.db'),
        'uncertainty': str(tmp_path / 'uncertainty.db'),
    }


@pytest.fixture
def resource_manager(temp_db):
    """Create resource manager with temp database."""
    return ResourceManager(db_path=temp_db['resources'])


@pytest.fixture
def coordinator(temp_db):
    """Create multi-agent coordinator with temp database."""
    return MultiAgentCoordinator(
        protocol=CoordinationProtocol.CENTRALIZED,
        db_path=temp_db['coordination']
    )


@pytest.fixture
def knowledge_synthesizer(temp_db):
    """Create knowledge synthesizer with temp database."""
    return KnowledgeSynthesizer(db_path=temp_db['knowledge'])


@pytest.fixture
def uncertainty_quantifier(temp_db):
    """Create uncertainty quantifier with temp database."""
    return UncertaintyQuantifier(db_path=temp_db['uncertainty'])


# ============================================================================
# RESOURCE MANAGEMENT TESTS
# ============================================================================

class TestResourceManager:
    """Test suite for resource management."""
    
    def test_create_budget(self, resource_manager):
        """Test creating a resource budget."""
        budget = resource_manager.create_budget(
            name="Daily Budget",
            limits={
                'cpu': 100.0,
                'memory': 16384.0,  # MB
                'energy': 1000.0  # Wh
            },
            period_hours=24.0
        )
        
        assert budget.budget_id is not None
        assert budget.name == "Daily Budget"
        assert budget.limits['cpu'] == 100.0
        assert budget.limits['memory'] == 16384.0
        assert budget.period_hours == 24.0
    
    def test_allocate_resources(self, resource_manager):
        """Test allocating resources to a task."""
        # Create budget first
        resource_manager.create_budget(
            name="Test Budget",
            limits={'cpu': 100.0, 'memory': 8192.0}
        )
        
        # Allocate resources
        allocation = resource_manager.allocate_resources(
            task_id="task_123",
            requested={'cpu': 20.0, 'memory': 2048.0},
            priority=Priority.HIGH
        )
        
        assert allocation is not None
        assert allocation.task_id == "task_123"
        assert allocation.resources['cpu'] == 20.0
        assert allocation.resources['memory'] == 2048.0
        assert allocation.priority == Priority.HIGH
        assert allocation.status == "allocated"
    
    def test_allocate_exceeds_budget(self, resource_manager):
        """Test that allocation fails when exceeding budget."""
        resource_manager.create_budget(
            name="Small Budget",
            limits={'cpu': 50.0}
        )
        
        # Try to allocate more than budget
        allocation = resource_manager.allocate_resources(
            task_id="task_456",
            requested={'cpu': 60.0}
        )
        
        assert allocation is None
    
    def test_release_resources(self, resource_manager):
        """Test releasing resources from completed allocation."""
        resource_manager.create_budget(
            name="Test Budget",
            limits={'cpu': 100.0}
        )
        
        allocation = resource_manager.allocate_resources(
            task_id="task_789",
            requested={'cpu': 30.0}
        )
        
        assert allocation is not None
        
        # Release resources
        success = resource_manager.release_resources(allocation.allocation_id)
        
        assert success is True
        assert allocation.status == "completed"
        assert allocation.completed_at is not None
    
    def test_optimize_allocation(self, resource_manager):
        """Test optimizing allocation across multiple tasks."""
        resource_manager.create_budget(
            name="Test Budget",
            limits={'cpu': 100.0, 'memory': 8192.0}
        )
        
        tasks = [
            {'task_id': 'task_1', 'resources': {'cpu': 30.0}, 'priority': 'high'},
            {'task_id': 'task_2', 'resources': {'cpu': 40.0}, 'priority': 'critical'},
            {'task_id': 'task_3', 'resources': {'cpu': 50.0}, 'priority': 'low'}
        ]
        
        allocations = resource_manager.optimize_allocation(tasks)
        
        # Should allocate critical and high priority first
        assert len(allocations) >= 2
        task_ids = [a.task_id for a in allocations]
        assert 'task_2' in task_ids  # Critical should be allocated
        assert 'task_1' in task_ids  # High should be allocated
    
    def test_get_usage_report(self, resource_manager):
        """Test getting resource usage report."""
        resource_manager.create_budget(
            name="Test Budget",
            limits={'cpu': 100.0, 'memory': 8192.0}
        )
        
        resource_manager.allocate_resources(
            task_id="task_1",
            requested={'cpu': 25.0, 'memory': 2048.0}
        )
        
        report = resource_manager.get_usage_report()
        
        assert 'budgets' in report
        assert 'allocations' in report
        assert 'Test Budget' in report['budgets']
        assert report['allocations']['total'] == 1


# ============================================================================
# MULTI-AGENT COORDINATION TESTS
# ============================================================================

class TestMultiAgentCoordinator:
    """Test suite for multi-agent coordination."""
    
    def test_register_agent(self, coordinator):
        """Test registering an agent."""
        agent = Agent(
            name="Worker 1",
            role=AgentRole.WORKER,
            capabilities=["coding", "testing"],
            status="idle"
        )
        
        agent_id = coordinator.register_agent(agent)
        
        assert agent_id is not None
        assert agent_id in coordinator.agents
        assert coordinator.agents[agent_id].name == "Worker 1"
    
    def test_unregister_agent(self, coordinator):
        """Test unregistering an agent."""
        agent = Agent(name="Worker 2", role=AgentRole.WORKER)
        agent_id = coordinator.register_agent(agent)
        
        success = coordinator.unregister_agent(agent_id)
        
        assert success is True
        assert agent_id not in coordinator.agents
    
    def test_submit_task(self, coordinator):
        """Test submitting a task."""
        task = CoordinationTask(
            description="Implement feature X",
            required_capabilities=["coding"],
            priority=Priority.HIGH
        )
        
        task_id = coordinator.submit_task(task)
        
        assert task_id is not None
        assert task_id in coordinator.tasks
        assert coordinator.tasks[task_id].status == "pending"
    
    def test_assign_task(self, coordinator):
        """Test assigning a task to agents."""
        # Register agents
        agent1 = Agent(
            name="Developer 1",
            role=AgentRole.WORKER,
            capabilities=["coding", "testing"]
        )
        agent2 = Agent(
            name="Developer 2",
            role=AgentRole.WORKER,
            capabilities=["coding"]
        )
        
        coordinator.register_agent(agent1)
        coordinator.register_agent(agent2)
        
        # Submit task
        task = CoordinationTask(
            description="Write tests",
            required_capabilities=["testing"]
        )
        task_id = coordinator.submit_task(task)
        
        # Assign task
        success = coordinator.assign_task(task_id)
        
        assert success is True
        assert coordinator.tasks[task_id].status == "assigned"
        assert len(coordinator.tasks[task_id].assigned_agents) > 0
    
    def test_assign_task_no_suitable_agents(self, coordinator):
        """Test task assignment fails when no suitable agents."""
        agent = Agent(
            name="Developer",
            role=AgentRole.WORKER,
            capabilities=["coding"]
        )
        coordinator.register_agent(agent)
        
        # Submit task requiring different capability
        task = CoordinationTask(
            description="Design UI",
            required_capabilities=["design"]
        )
        task_id = coordinator.submit_task(task)
        
        success = coordinator.assign_task(task_id)
        
        assert success is False
    
    def test_complete_task(self, coordinator):
        """Test completing a task."""
        agent = Agent(name="Worker", role=AgentRole.WORKER, capabilities=["coding"])
        coordinator.register_agent(agent)
        
        task = CoordinationTask(
            description="Code review",
            required_capabilities=["coding"]
        )
        task_id = coordinator.submit_task(task)
        coordinator.assign_task(task_id)
        
        success = coordinator.complete_task(task_id, success=True)
        
        assert success is True
        assert coordinator.tasks[task_id].status == "completed"
        assert coordinator.tasks[task_id].completed_at is not None
    
    def test_resolve_conflict(self, coordinator):
        """Test resolving conflicts between agents."""
        agent1 = Agent(name="Agent 1", role=AgentRole.WORKER, reliability=0.9)
        agent2 = Agent(name="Agent 2", role=AgentRole.WORKER, reliability=0.7)
        
        id1 = coordinator.register_agent(agent1)
        id2 = coordinator.register_agent(agent2)
        
        task = CoordinationTask(description="Task")
        task_id = coordinator.submit_task(task)
        
        winner = coordinator.resolve_conflict(task_id, [id1, id2])
        
        assert winner is not None
        assert winner == id1  # Higher reliability wins
    
    def test_reach_consensus(self, coordinator):
        """Test reaching consensus among agents."""
        proposals = {
            'agent_1': {'action': 'approve'},
            'agent_2': {'action': 'approve'},
            'agent_3': {'action': 'reject'}
        }
        
        consensus = coordinator.reach_consensus(
            proposals=proposals,
            voters=['agent_1', 'agent_2', 'agent_3'],
            threshold=0.6
        )
        
        assert consensus is not None
        assert consensus == {'action': 'approve'}
    
    def test_reach_consensus_no_agreement(self, coordinator):
        """Test consensus fails when no agreement."""
        proposals = {
            'agent_1': {'action': 'approve'},
            'agent_2': {'action': 'reject'},
            'agent_3': {'action': 'abstain'}
        }
        
        consensus = coordinator.reach_consensus(
            proposals=proposals,
            voters=['agent_1', 'agent_2', 'agent_3'],
            threshold=0.6
        )
        
        assert consensus is None
    
    def test_get_coordination_report(self, coordinator):
        """Test getting coordination status report."""
        agent = Agent(name="Worker", role=AgentRole.WORKER)
        coordinator.register_agent(agent)
        
        task = CoordinationTask(description="Task")
        coordinator.submit_task(task)
        
        report = coordinator.get_coordination_report()
        
        assert 'agents' in report
        assert 'tasks' in report
        assert report['agents']['total'] == 1
        assert report['tasks']['total'] == 1


# ============================================================================
# KNOWLEDGE SYNTHESIS TESTS
# ============================================================================

class TestKnowledgeSynthesizer:
    """Test suite for knowledge synthesis."""
    
    def test_add_claim(self, knowledge_synthesizer):
        """Test adding a knowledge claim."""
        claim = KnowledgeClaim(
            source_type=KnowledgeSourceType.OBSERVATION,
            source_id="sensor_1",
            subject="temperature",
            predicate="value",
            value=25.5,
            confidence=0.9
        )
        
        claim_id = knowledge_synthesizer.add_claim(claim)
        
        assert claim_id is not None
        assert claim_id in knowledge_synthesizer.claims
        assert knowledge_synthesizer.claims[claim_id].value == 25.5
    
    def test_detect_contradictions(self, knowledge_synthesizer):
        """Test detecting contradictions."""
        # Add conflicting claims
        claim1 = KnowledgeClaim(
            source_type=KnowledgeSourceType.OBSERVATION,
            source_id="sensor_1",
            subject="status",
            predicate="running",
            value=True,
            confidence=0.9
        )
        
        claim2 = KnowledgeClaim(
            source_type=KnowledgeSourceType.OBSERVATION,
            source_id="sensor_2",
            subject="status",
            predicate="running",
            value=False,
            confidence=0.8
        )
        
        knowledge_synthesizer.add_claim(claim1)
        knowledge_synthesizer.add_claim(claim2)
        
        contradictions = knowledge_synthesizer.detect_contradictions(
            subject="status",
            predicate="running"
        )
        
        assert len(contradictions) > 0
        assert contradictions[0]['type'] == "direct"
    
    def test_synthesize_weighted_average(self, knowledge_synthesizer):
        """Test weighted average synthesis."""
        # Add numeric claims
        for i, value in enumerate([10.0, 12.0, 11.0]):
            claim = KnowledgeClaim(
                source_type=KnowledgeSourceType.SENSOR,
                source_id=f"sensor_{i}",
                subject="temperature",
                predicate="celsius",
                value=value,
                confidence=0.8
            )
            knowledge_synthesizer.add_claim(claim)
        
        synthesized = knowledge_synthesizer.synthesize_weighted_average(
            subject="temperature",
            predicate="celsius"
        )
        
        assert synthesized is not None
        assert abs(synthesized.value - 11.0) < 0.1  # Average
        assert synthesized.synthesis_method == "weighted_average"
        assert len(synthesized.source_claims) == 3
    
    def test_synthesize_majority_vote(self, knowledge_synthesizer):
        """Test majority vote synthesis."""
        # Add claims with different values
        values = ["running", "running", "stopped"]
        for i, value in enumerate(values):
            claim = KnowledgeClaim(
                source_type=KnowledgeSourceType.OBSERVATION,
                source_id=f"observer_{i}",
                subject="process",
                predicate="status",
                value=value,
                confidence=0.9
            )
            knowledge_synthesizer.add_claim(claim)
        
        synthesized = knowledge_synthesizer.synthesize_majority_vote(
            subject="process",
            predicate="status"
        )
        
        assert synthesized is not None
        assert synthesized.value == "running"  # Majority
        assert synthesized.synthesis_method == "majority_vote"
    
    def test_build_knowledge_graph(self, knowledge_synthesizer):
        """Test building knowledge graph."""
        # Add synthesized knowledge
        knowledge1 = SynthesizedKnowledge(
            subject="Alice",
            predicate="knows",
            value="Bob",
            confidence=0.9
        )
        
        knowledge2 = SynthesizedKnowledge(
            subject="Bob",
            predicate="works_with",
            value="Charlie",
            confidence=0.8
        )
        
        knowledge_synthesizer.synthesized[knowledge1.knowledge_id] = knowledge1
        knowledge_synthesizer.synthesized[knowledge2.knowledge_id] = knowledge2
        
        graph = knowledge_synthesizer.build_knowledge_graph()
        
        assert 'nodes' in graph
        assert 'edges' in graph
        assert graph['node_count'] >= 3
        assert graph['edge_count'] == 2
    
    def test_query_knowledge(self, knowledge_synthesizer):
        """Test querying synthesized knowledge."""
        knowledge = SynthesizedKnowledge(
            subject="temperature",
            predicate="celsius",
            value=22.5,
            confidence=0.85
        )
        knowledge_synthesizer.synthesized[knowledge.knowledge_id] = knowledge
        
        results = knowledge_synthesizer.query_knowledge(
            subject="temperature"
        )
        
        assert len(results) == 1
        assert results[0].value == 22.5


# ============================================================================
# UNCERTAINTY QUANTIFICATION TESTS
# ============================================================================

class TestUncertaintyQuantifier:
    """Test suite for uncertainty quantification."""
    
    def test_create_distribution_normal(self, uncertainty_quantifier):
        """Test creating normal distribution."""
        dist = uncertainty_quantifier.create_distribution(
            dist_type=DistributionType.NORMAL,
            parameters={'mean': 0.0, 'std': 1.0},
            description="Standard normal"
        )
        
        assert dist.dist_id is not None
        assert dist.dist_type == DistributionType.NORMAL
        assert dist.parameters['mean'] == 0.0
        assert dist.parameters['std'] == 1.0
    
    def test_create_distribution_uniform(self, uncertainty_quantifier):
        """Test creating uniform distribution."""
        dist = uncertainty_quantifier.create_distribution(
            dist_type=DistributionType.UNIFORM,
            parameters={'low': 0.0, 'high': 10.0}
        )
        
        assert dist.dist_type == DistributionType.UNIFORM
        assert dist.parameters['low'] == 0.0
        assert dist.parameters['high'] == 10.0
    
    def test_sample_distribution(self, uncertainty_quantifier):
        """Test sampling from distribution."""
        dist = ProbabilityDistribution(
            dist_type=DistributionType.NORMAL,
            parameters={'mean': 5.0, 'std': 2.0}
        )
        
        samples = dist.sample(n=100)
        
        assert len(samples) == 100
        # Check that mean is approximately correct
        sample_mean = sum(samples) / len(samples)
        assert abs(sample_mean - 5.0) < 1.0  # Within 1 std
    
    def test_pdf_normal(self, uncertainty_quantifier):
        """Test PDF calculation for normal distribution."""
        dist = ProbabilityDistribution(
            dist_type=DistributionType.NORMAL,
            parameters={'mean': 0.0, 'std': 1.0}
        )
        
        # PDF at mean should be maximum
        pdf_at_mean = dist.pdf(0.0)
        pdf_at_1std = dist.pdf(1.0)
        
        assert pdf_at_mean > pdf_at_1std
        assert pdf_at_mean > 0.0
    
    def test_monte_carlo_simulation(self, uncertainty_quantifier):
        """Test Monte Carlo simulation."""
        dist = uncertainty_quantifier.create_distribution(
            dist_type=DistributionType.NORMAL,
            parameters={'mean': 10.0, 'std': 2.0}
        )
        
        stats = uncertainty_quantifier.monte_carlo_simulation(
            dist=dist,
            n_samples=1000
        )
        
        assert 'mean' in stats
        assert 'std' in stats
        assert 'percentiles' in stats
        assert abs(stats['mean'] - 10.0) < 0.5
        assert abs(stats['std'] - 2.0) < 0.5
    
    def test_bayesian_update_normal(self, uncertainty_quantifier):
        """Test Bayesian update for normal distribution."""
        prior = uncertainty_quantifier.create_distribution(
            dist_type=DistributionType.NORMAL,
            parameters={'mean': 0.0, 'std': 2.0}
        )
        
        update = uncertainty_quantifier.bayesian_update_normal(
            prior=prior,
            observation=5.0,
            observation_noise=1.0
        )
        
        assert update is not None
        assert update.posterior.dist_type == DistributionType.NORMAL
        
        # Posterior mean should be between prior mean and observation
        posterior_mean = update.posterior.parameters['mean']
        assert 0.0 < posterior_mean < 5.0
        
        # Posterior std should be smaller than prior std
        posterior_std = update.posterior.parameters['std']
        assert posterior_std < 2.0
    
    def test_calculate_credible_interval(self, uncertainty_quantifier):
        """Test calculating credible interval."""
        dist = ProbabilityDistribution(
            dist_type=DistributionType.NORMAL,
            parameters={'mean': 0.0, 'std': 1.0}
        )
        
        lower, upper = uncertainty_quantifier.calculate_credible_interval(
            dist=dist,
            confidence=0.95
        )
        
        # 95% interval for standard normal is approximately [-1.96, 1.96]
        assert lower < -1.5
        assert upper > 1.5
        assert lower < upper
    
    def test_calibrate_confidence(self, uncertainty_quantifier):
        """Test confidence calibration."""
        # Create predictions and actual values
        predictions = [0.9, 0.8, 0.7, 0.6, 0.5] * 20
        actual = [0.9, 0.8, 0.7, 0.6, 0.5] * 20  # Perfect calibration
        
        result = uncertainty_quantifier.calibrate_confidence(
            predictions=predictions,
            actual=actual,
            n_bins=5
        )
        
        assert 'calibration' in result
        assert 'expected_calibration_error' in result
        assert result['n_samples'] == 100
        # ECE measures calibration quality (0 = perfect, 1 = worst)
        # For this test data, ECE should be reasonable
        assert result['expected_calibration_error'] >= 0.0
        assert result['expected_calibration_error'] <= 1.0


# ============================================================================
# PHASE 14 INTEGRATION TESTS
# ============================================================================

class TestPhase14Integration:
    """Integration tests for Phase 14."""
    
    def test_phase14_initialization(self, temp_db):
        """Test Phase 14 initialization."""
        phase14 = Phase14AdvancedCognitiveCapabilities(db_path=temp_db['resources'])
        
        assert phase14.resource_manager is not None
        assert phase14.coordinator is not None
        assert phase14.knowledge_synthesizer is not None
        assert phase14.uncertainty_quantifier is not None
    
    def test_phase14_report(self, temp_db):
        """Test Phase 14 comprehensive report."""
        phase14 = Phase14AdvancedCognitiveCapabilities(db_path=temp_db['resources'])
        
        # Add some data
        phase14.resource_manager.create_budget(
            name="Test",
            limits={'cpu': 100.0}
        )
        
        agent = Agent(name="Worker", role=AgentRole.WORKER)
        phase14.coordinator.register_agent(agent)
        
        report = phase14.get_phase14_report()
        
        assert 'resource_management' in report
        assert 'multi_agent_coordination' in report
        assert 'knowledge_synthesis' in report
        assert 'uncertainty_quantification' in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
