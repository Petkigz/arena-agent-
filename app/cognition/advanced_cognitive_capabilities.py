"""
Phase 14: Advanced Cognitive Capabilities

This phase implements four critical subsystems that bridge strategic planning (Phase 13)
and cross-domain transfer (Phase 15):

1. Resource Management & Optimization
   - Computational resource allocation
   - Energy consumption optimization
   - Priority-based scheduling
   - Load balancing

2. Multi-Agent Coordination
   - Coordination protocols
   - Task delegation
   - Conflict resolution
   - Consensus mechanisms

3. Knowledge Synthesis
   - Multi-source integration
   - Contradiction resolution
   - Knowledge graph construction
   - Semantic reasoning

4. Uncertainty Quantification
   - Probabilistic reasoning
   - Confidence calibration
   - Bayesian inference
   - Monte Carlo simulation

This phase enables the agent to manage complex real-world scenarios with multiple
constraints, agents, knowledge sources, and uncertainties.
"""

from __future__ import annotations

import sqlite3
import json
import math
import random
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from collections import defaultdict, deque
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# SUBSYSTEM 1: RESOURCE MANAGEMENT & OPTIMIZATION
# ============================================================================

class ResourceType(Enum):
    """Types of computational resources."""
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    STORAGE = "storage"
    NETWORK = "network"
    ENERGY = "energy"


class Priority(Enum):
    """Task priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"


@dataclass
class ResourceAllocation:
    """Allocation of resources to a task."""
    allocation_id: str = field(default_factory=lambda: f"alloc_{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    resources: Dict[str, float] = field(default_factory=dict)  # resource_type -> amount
    priority: Priority = Priority.MEDIUM
    status: str = "allocated"  # allocated, active, completed, failed
    allocated_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'allocation_id': self.allocation_id,
            'task_id': self.task_id,
            'resources': self.resources,
            'priority': self.priority.value,
            'status': self.status,
            'allocated_at': self.allocated_at,
            'completed_at': self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceAllocation':
        return cls(
            allocation_id=data['allocation_id'],
            task_id=data['task_id'],
            resources=data.get('resources', {}),
            priority=Priority(data.get('priority', 'medium')),
            status=data.get('status', 'allocated'),
            allocated_at=data.get('allocated_at', _now()),
            completed_at=data.get('completed_at')
        )


@dataclass
class ResourceBudget:
    """Budget constraints for resource usage."""
    budget_id: str = field(default_factory=lambda: f"budget_{uuid.uuid4().hex[:8]}")
    name: str = ""
    limits: Dict[str, float] = field(default_factory=dict)  # resource_type -> max_amount
    current_usage: Dict[str, float] = field(default_factory=dict)
    period_hours: float = 24.0
    reset_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'budget_id': self.budget_id,
            'name': self.name,
            'limits': self.limits,
            'current_usage': self.current_usage,
            'period_hours': self.period_hours,
            'reset_at': self.reset_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceBudget':
        return cls(
            budget_id=data['budget_id'],
            name=data.get('name', ''),
            limits=data.get('limits', {}),
            current_usage=data.get('current_usage', {}),
            period_hours=data.get('period_hours', 24.0),
            reset_at=data.get('reset_at', _now())
        )


class ResourceManager:
    """
    Manages computational resource allocation and optimization.
    
    Features:
    - Priority-based scheduling
    - Resource budgeting and limits
    - Load balancing
    - Energy optimization
    """
    
    def __init__(self, db_path: str = "data/phase14_resources.db"):
        self.db_path = db_path
        self._ensure_db()
        self.budgets: Dict[str, ResourceBudget] = {}
        self.allocations: Dict[str, ResourceAllocation] = {}
        app_logger.info("ResourceManager initialized")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_allocations (
                    allocation_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    resources TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    allocated_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_budgets (
                    budget_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    limits TEXT NOT NULL,
                    current_usage TEXT NOT NULL,
                    period_hours REAL NOT NULL,
                    reset_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_metrics (
                    metric_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    usage REAL NOT NULL,
                    capacity REAL NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def create_budget(
        self,
        name: str,
        limits: Dict[str, float],
        period_hours: float = 24.0
    ) -> ResourceBudget:
        """Create a resource budget with limits."""
        budget = ResourceBudget(
            name=name,
            limits=limits,
            period_hours=period_hours
        )
        
        self.budgets[budget.budget_id] = budget
        self._save_budget(budget)
        
        app_logger.info(f"Created budget '{name}' with limits: {limits}")
        
        return budget
    
    def allocate_resources(
        self,
        task_id: str,
        requested: Dict[str, float],
        priority: Priority = Priority.MEDIUM
    ) -> Optional[ResourceAllocation]:
        """
        Allocate resources to a task if within budget.
        
        Returns None if allocation would exceed budget limits.
        """
        # Check budget constraints
        for budget in self.budgets.values():
            for resource_type, amount in requested.items():
                current = budget.current_usage.get(resource_type, 0.0)
                limit = budget.limits.get(resource_type, float('inf'))
                
                if current + amount > limit:
                    app_logger.warning(
                        f"Allocation rejected: {resource_type} would exceed budget "
                        f"({current} + {amount} > {limit})"
                    )
                    return None
        
        # Create allocation
        allocation = ResourceAllocation(
            task_id=task_id,
            resources=requested,
            priority=priority
        )
        
        # Update budget usage
        for budget in self.budgets.values():
            for resource_type, amount in requested.items():
                budget.current_usage[resource_type] = (
                    budget.current_usage.get(resource_type, 0.0) + amount
                )
            self._save_budget(budget)
        
        self.allocations[allocation.allocation_id] = allocation
        self._save_allocation(allocation)
        
        app_logger.info(
            f"Allocated resources to task {task_id}: {requested} "
            f"(priority: {priority.value})"
        )
        
        return allocation
    
    def release_resources(self, allocation_id: str) -> bool:
        """Release resources from a completed allocation."""
        if allocation_id not in self.allocations:
            return False
        
        allocation = self.allocations[allocation_id]
        allocation.status = "completed"
        allocation.completed_at = _now()
        
        # Update budget usage
        for budget in self.budgets.values():
            for resource_type, amount in allocation.resources.items():
                budget.current_usage[resource_type] = max(
                    0.0,
                    budget.current_usage.get(resource_type, 0.0) - amount
                )
            self._save_budget(budget)
        
        self._save_allocation(allocation)
        
        app_logger.info(f"Released resources from allocation {allocation_id}")
        
        return True
    
    def optimize_allocation(
        self,
        tasks: List[Dict[str, Any]]
    ) -> List[ResourceAllocation]:
        """
        Optimize resource allocation across multiple tasks.
        
        Uses priority-based scheduling with load balancing.
        """
        # Sort by priority (critical first)
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
            Priority.BACKGROUND: 4
        }
        
        sorted_tasks = sorted(
            tasks,
            key=lambda t: priority_order.get(
                Priority(t.get('priority', 'medium')),
                2
            )
        )
        
        allocations = []
        for task in sorted_tasks:
            allocation = self.allocate_resources(
                task_id=task['task_id'],
                requested=task['resources'],
                priority=Priority(task.get('priority', 'medium'))
            )
            
            if allocation:
                allocations.append(allocation)
        
        app_logger.info(
            f"Optimized allocation: {len(allocations)}/{len(tasks)} tasks allocated"
        )
        
        return allocations
    
    def get_usage_report(self) -> Dict[str, Any]:
        """Get current resource usage report."""
        report = {
            'budgets': {},
            'allocations': {
                'total': len(self.allocations),
                'active': sum(1 for a in self.allocations.values() if a.status == 'active'),
                'completed': sum(1 for a in self.allocations.values() if a.status == 'completed')
            }
        }
        
        for budget in self.budgets.values():
            report['budgets'][budget.name] = {
                'limits': budget.limits,
                'current_usage': budget.current_usage,
                'utilization': {
                    resource: (usage / budget.limits.get(resource, 1.0) * 100)
                    for resource, usage in budget.current_usage.items()
                }
            }
        
        return report
    
    def _save_allocation(self, allocation: ResourceAllocation) -> None:
        """Save allocation to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO resource_allocations
                (allocation_id, task_id, resources, priority, status, allocated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                allocation.allocation_id,
                allocation.task_id,
                json.dumps(allocation.resources),
                allocation.priority.value,
                allocation.status,
                allocation.allocated_at,
                allocation.completed_at
            ))
            conn.commit()
    
    def _save_budget(self, budget: ResourceBudget) -> None:
        """Save budget to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO resource_budgets
                (budget_id, name, limits, current_usage, period_hours, reset_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                budget.budget_id,
                budget.name,
                json.dumps(budget.limits),
                json.dumps(budget.current_usage),
                budget.period_hours,
                budget.reset_at
            ))
            conn.commit()


# ============================================================================
# SUBSYSTEM 2: MULTI-AGENT COORDINATION
# ============================================================================

class AgentRole(Enum):
    """Roles in multi-agent coordination."""
    COORDINATOR = "coordinator"
    WORKER = "worker"
    SPECIALIST = "specialist"
    OBSERVER = "observer"


class CoordinationProtocol(Enum):
    """Coordination protocols."""
    CENTRALIZED = "centralized"  # Single coordinator
    DISTRIBUTED = "distributed"  # Peer-to-peer
    HIERARCHICAL = "hierarchical"  # Tree structure
    CONSENSUS = "consensus"  # Voting-based


@dataclass
class Agent:
    """An agent in the multi-agent system."""
    agent_id: str = field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    name: str = ""
    role: AgentRole = AgentRole.WORKER
    capabilities: List[str] = field(default_factory=list)
    status: str = "idle"  # idle, busy, offline
    current_task: Optional[str] = None
    load: float = 0.0  # 0.0 to 1.0
    reliability: float = 1.0  # 0.0 to 1.0
    last_seen: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'name': self.name,
            'role': self.role.value,
            'capabilities': self.capabilities,
            'status': self.status,
            'current_task': self.current_task,
            'load': self.load,
            'reliability': self.reliability,
            'last_seen': self.last_seen
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Agent':
        return cls(
            agent_id=data['agent_id'],
            name=data.get('name', ''),
            role=AgentRole(data.get('role', 'worker')),
            capabilities=data.get('capabilities', []),
            status=data.get('status', 'idle'),
            current_task=data.get('current_task'),
            load=data.get('load', 0.0),
            reliability=data.get('reliability', 1.0),
            last_seen=data.get('last_seen', _now())
        )


@dataclass
class CoordinationTask:
    """A task to be coordinated across agents."""
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    description: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    assigned_agents: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, assigned, in_progress, completed, failed
    dependencies: List[str] = field(default_factory=list)  # task_ids
    priority: Priority = Priority.MEDIUM
    created_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'description': self.description,
            'required_capabilities': self.required_capabilities,
            'assigned_agents': self.assigned_agents,
            'status': self.status,
            'dependencies': self.dependencies,
            'priority': self.priority.value,
            'created_at': self.created_at,
            'completed_at': self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CoordinationTask':
        return cls(
            task_id=data['task_id'],
            description=data.get('description', ''),
            required_capabilities=data.get('required_capabilities', []),
            assigned_agents=data.get('assigned_agents', []),
            status=data.get('status', 'pending'),
            dependencies=data.get('dependencies', []),
            priority=Priority(data.get('priority', 'medium')),
            created_at=data.get('created_at', _now()),
            completed_at=data.get('completed_at')
        )


class MultiAgentCoordinator:
    """
    Coordinates multiple agents for complex tasks.
    
    Features:
    - Task delegation based on capabilities
    - Load balancing across agents
    - Conflict resolution
    - Consensus mechanisms
    """
    
    def __init__(
        self,
        protocol: CoordinationProtocol = CoordinationProtocol.CENTRALIZED,
        db_path: str = "data/phase14_coordination.db"
    ):
        self.protocol = protocol
        self.db_path = db_path
        self._ensure_db()
        self.agents: Dict[str, Agent] = {}
        self.tasks: Dict[str, CoordinationTask] = {}
        app_logger.info(f"MultiAgentCoordinator initialized (protocol: {protocol.value})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    capabilities TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_task TEXT,
                    load REAL NOT NULL,
                    reliability REAL NOT NULL,
                    last_seen TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS coordination_tasks (
                    task_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    required_capabilities TEXT NOT NULL,
                    assigned_agents TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dependencies TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_messages (
                    message_id TEXT PRIMARY KEY,
                    from_agent TEXT NOT NULL,
                    to_agent TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def register_agent(self, agent: Agent) -> str:
        """Register an agent in the system."""
        self.agents[agent.agent_id] = agent
        self._save_agent(agent)
        
        app_logger.info(f"Registered agent: {agent.name} ({agent.agent_id})")
        
        return agent.agent_id
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the system."""
        if agent_id not in self.agents:
            return False
        
        del self.agents[agent_id]
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
            conn.commit()
        
        app_logger.info(f"Unregistered agent: {agent_id}")
        
        return True
    
    def submit_task(self, task: CoordinationTask) -> str:
        """Submit a task for coordination."""
        self.tasks[task.task_id] = task
        self._save_task(task)
        
        app_logger.info(f"Submitted task: {task.description} ({task.task_id})")
        
        return task.task_id
    
    def assign_task(self, task_id: str) -> bool:
        """
        Assign a task to suitable agents.
        
        Uses capability matching and load balancing.
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # Check dependencies
        for dep_id in task.dependencies:
            if dep_id in self.tasks:
                dep_task = self.tasks[dep_id]
                if dep_task.status not in ('completed', 'failed'):
                    app_logger.warning(
                        f"Task {task_id} has unmet dependency: {dep_id}"
                    )
                    return False
        
        # Find suitable agents
        suitable_agents = []
        for agent in self.agents.values():
            if agent.status == 'offline':
                continue
            
            # Check capabilities
            if not all(cap in agent.capabilities for cap in task.required_capabilities):
                continue
            
            suitable_agents.append(agent)
        
        if not suitable_agents:
            app_logger.warning(f"No suitable agents for task {task_id}")
            return False
        
        # Sort by load (prefer less loaded agents) and reliability
        suitable_agents.sort(key=lambda a: (a.load, -a.reliability))
        
        # Assign to best agent(s)
        assigned = []
        for agent in suitable_agents[:3]:  # Assign to up to 3 agents
            if agent.load < 0.8:  # Don't overload
                assigned.append(agent.agent_id)
                agent.current_task = task_id
                agent.status = 'busy'
                agent.load = min(1.0, agent.load + 0.3)
                self._save_agent(agent)
        
        if not assigned:
            app_logger.warning(f"All suitable agents are overloaded for task {task_id}")
            return False
        
        task.assigned_agents = assigned
        task.status = 'assigned'
        self._save_task(task)
        
        app_logger.info(
            f"Assigned task {task_id} to agents: {assigned}"
        )
        
        return True
    
    def complete_task(self, task_id: str, success: bool = True) -> bool:
        """Mark a task as completed."""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.status = 'completed' if success else 'failed'
        task.completed_at = _now()
        
        # Release agents
        for agent_id in task.assigned_agents:
            if agent_id in self.agents:
                agent = self.agents[agent_id]
                agent.current_task = None
                agent.status = 'idle'
                agent.load = max(0.0, agent.load - 0.3)
                self._save_agent(agent)
        
        self._save_task(task)
        
        app_logger.info(
            f"Task {task_id} completed (success: {success})"
        )
        
        return True
    
    def resolve_conflict(
        self,
        task_id: str,
        conflicting_agents: List[str]
    ) -> Optional[str]:
        """
        Resolve conflicts between agents working on the same task.
        
        Returns the winning agent_id or None if unresolved.
        """
        if task_id not in self.tasks:
            return None
        
        task = self.tasks[task_id]
        
        # Get agent reliabilities
        agent_scores = {}
        for agent_id in conflicting_agents:
            if agent_id in self.agents:
                agent = self.agents[agent_id]
                # Score based on reliability and current load
                score = agent.reliability * (1.0 - agent.load)
                agent_scores[agent_id] = score
        
        if not agent_scores:
            return None
        
        # Select agent with highest score
        winner = max(agent_scores.items(), key=lambda x: x[1])[0]
        
        # Update task assignment
        task.assigned_agents = [winner]
        self._save_task(task)
        
        # Release other agents
        for agent_id in conflicting_agents:
            if agent_id != winner and agent_id in self.agents:
                agent = self.agents[agent_id]
                agent.current_task = None
                agent.status = 'idle'
                agent.load = max(0.0, agent.load - 0.3)
                self._save_agent(agent)
        
        app_logger.info(
            f"Resolved conflict for task {task_id}: winner = {winner}"
        )
        
        return winner
    
    def reach_consensus(
        self,
        proposals: Dict[str, Any],
        voters: List[str],
        threshold: float = 0.6
    ) -> Optional[Any]:
        """
        Reach consensus among multiple agents.
        
        Returns the consensus value or None if no consensus reached.
        """
        if not proposals or not voters:
            return None
        
        # Count votes for each proposal
        vote_counts = defaultdict(int)
        for voter_id in voters:
            if voter_id in proposals:
                proposal = proposals[voter_id]
                # Use JSON serialization for comparison
                proposal_key = json.dumps(proposal, sort_keys=True)
                vote_counts[proposal_key] += 1
        
        if not vote_counts:
            return None
        
        # Find proposal with most votes
        total_votes = sum(vote_counts.values())
        best_proposal_key, best_votes = max(vote_counts.items(), key=lambda x: x[1])
        
        # Check if threshold met
        if best_votes / total_votes >= threshold:
            consensus = json.loads(best_proposal_key)
            
            app_logger.info(
                f"Consensus reached: {best_votes}/{total_votes} votes "
                f"({best_votes/total_votes*100:.1f}%)"
            )
            
            return consensus
        else:
            app_logger.warning(
                f"No consensus: best proposal has {best_votes}/{total_votes} votes "
                f"({best_votes/total_votes*100:.1f}% < {threshold*100:.1f}%)"
            )
            return None
    
    def get_coordination_report(self) -> Dict[str, Any]:
        """Get current coordination status report."""
        report = {
            'agents': {
                'total': len(self.agents),
                'idle': sum(1 for a in self.agents.values() if a.status == 'idle'),
                'busy': sum(1 for a in self.agents.values() if a.status == 'busy'),
                'offline': sum(1 for a in self.agents.values() if a.status == 'offline'),
                'avg_load': sum(a.load for a in self.agents.values()) / len(self.agents) if self.agents else 0.0,
                'avg_reliability': sum(a.reliability for a in self.agents.values()) / len(self.agents) if self.agents else 0.0
            },
            'tasks': {
                'total': len(self.tasks),
                'pending': sum(1 for t in self.tasks.values() if t.status == 'pending'),
                'assigned': sum(1 for t in self.tasks.values() if t.status == 'assigned'),
                'in_progress': sum(1 for t in self.tasks.values() if t.status == 'in_progress'),
                'completed': sum(1 for t in self.tasks.values() if t.status == 'completed'),
                'failed': sum(1 for t in self.tasks.values() if t.status == 'failed')
            }
        }
        
        return report
    
    def _save_agent(self, agent: Agent) -> None:
        """Save agent to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO agents
                (agent_id, name, role, capabilities, status, current_task, load, reliability, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent.agent_id,
                agent.name,
                agent.role.value,
                json.dumps(agent.capabilities),
                agent.status,
                agent.current_task,
                agent.load,
                agent.reliability,
                agent.last_seen
            ))
            conn.commit()
    
    def _save_task(self, task: CoordinationTask) -> None:
        """Save task to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO coordination_tasks
                (task_id, description, required_capabilities, assigned_agents, status, dependencies, priority, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id,
                task.description,
                json.dumps(task.required_capabilities),
                json.dumps(task.assigned_agents),
                task.status,
                json.dumps(task.dependencies),
                task.priority.value,
                task.created_at,
                task.completed_at
            ))
            conn.commit()


# ============================================================================
# SUBSYSTEM 3: KNOWLEDGE SYNTHESIS
# ============================================================================

class KnowledgeSourceType(Enum):
    """Types of knowledge sources."""
    OBSERVATION = "observation"
    INFERENCE = "inference"
    TESTIMONY = "testimony"
    DOCUMENT = "document"
    SENSOR = "sensor"


class ContradictionType(Enum):
    """Types of contradictions."""
    DIRECT = "direct"  # A and not-A
    IMPLICIT = "implicit"  # A implies B, but not-B
    TEMPORAL = "temporal"  # A at t1, not-A at t2
    CONTEXTUAL = "contextual"  # A in context1, not-A in context2


@dataclass
class KnowledgeClaim:
    """A claim from a knowledge source."""
    claim_id: str = field(default_factory=lambda: f"claim_{uuid.uuid4().hex[:8]}")
    source_type: KnowledgeSourceType = KnowledgeSourceType.OBSERVATION
    source_id: str = ""
    subject: str = ""
    predicate: str = ""
    value: Any = None
    confidence: float = 0.5
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'claim_id': self.claim_id,
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'subject': self.subject,
            'predicate': self.predicate,
            'value': self.value,
            'confidence': self.confidence,
            'context': self.context,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeClaim':
        return cls(
            claim_id=data['claim_id'],
            source_type=KnowledgeSourceType(data.get('source_type', 'observation')),
            source_id=data.get('source_id', ''),
            subject=data.get('subject', ''),
            predicate=data.get('predicate', ''),
            value=data.get('value'),
            confidence=data.get('confidence', 0.5),
            context=data.get('context', {}),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class SynthesizedKnowledge:
    """Synthesized knowledge from multiple sources."""
    knowledge_id: str = field(default_factory=lambda: f"knowledge_{uuid.uuid4().hex[:8]}")
    subject: str = ""
    predicate: str = ""
    value: Any = None
    confidence: float = 0.5
    source_claims: List[str] = field(default_factory=list)  # claim_ids
    synthesis_method: str = ""  # weighted_average, majority_vote, etc.
    contradictions_resolved: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'knowledge_id': self.knowledge_id,
            'subject': self.subject,
            'predicate': self.predicate,
            'value': self.value,
            'confidence': self.confidence,
            'source_claims': self.source_claims,
            'synthesis_method': self.synthesis_method,
            'contradictions_resolved': self.contradictions_resolved,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SynthesizedKnowledge':
        return cls(
            knowledge_id=data['knowledge_id'],
            subject=data.get('subject', ''),
            predicate=data.get('predicate', ''),
            value=data.get('value'),
            confidence=data.get('confidence', 0.5),
            source_claims=data.get('source_claims', []),
            synthesis_method=data.get('synthesis_method', ''),
            contradictions_resolved=data.get('contradictions_resolved', []),
            timestamp=data.get('timestamp', _now())
        )


class KnowledgeSynthesizer:
    """
    Synthesizes knowledge from multiple sources.
    
    Features:
    - Multi-source integration
    - Contradiction detection and resolution
    - Confidence-weighted synthesis
    - Knowledge graph construction
    """
    
    def __init__(self, db_path: str = "data/phase14_knowledge.db"):
        self.db_path = db_path
        self._ensure_db()
        self.claims: Dict[str, KnowledgeClaim] = {}
        self.synthesized: Dict[str, SynthesizedKnowledge] = {}
        app_logger.info("KnowledgeSynthesizer initialized")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_claims (
                    claim_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    context TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS synthesized_knowledge (
                    knowledge_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_claims TEXT NOT NULL,
                    synthesis_method TEXT NOT NULL,
                    contradictions_resolved TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    edge_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def add_claim(self, claim: KnowledgeClaim) -> str:
        """Add a knowledge claim."""
        self.claims[claim.claim_id] = claim
        self._save_claim(claim)
        
        app_logger.info(
            f"Added claim: {claim.subject} {claim.predicate} = {claim.value} "
            f"(confidence: {claim.confidence:.2f})"
        )
        
        return claim.claim_id
    
    def detect_contradictions(
        self,
        subject: str,
        predicate: str
    ) -> List[Dict[str, Any]]:
        """
        Detect contradictions among claims about the same subject/predicate.
        
        Returns list of contradiction descriptions.
        """
        relevant_claims = [
            claim for claim in self.claims.values()
            if claim.subject == subject and claim.predicate == predicate
        ]
        
        if len(relevant_claims) < 2:
            return []
        
        contradictions = []
        
        # Check for direct contradictions (different values)
        values = {}
        for claim in relevant_claims:
            value_key = json.dumps(claim.value, sort_keys=True)
            if value_key not in values:
                values[value_key] = []
            values[value_key].append(claim)
        
        if len(values) > 1:
            # Multiple different values = contradiction
            contradiction = {
                'type': ContradictionType.DIRECT.value,
                'subject': subject,
                'predicate': predicate,
                'values': [json.loads(k) for k in values.keys()],
                'claims': [c.claim_id for claims in values.values() for c in claims]
            }
            contradictions.append(contradiction)
        
        return contradictions
    
    def synthesize_weighted_average(
        self,
        subject: str,
        predicate: str
    ) -> Optional[SynthesizedKnowledge]:
        """
        Synthesize knowledge using weighted average.
        
        Weights are based on claim confidence.
        """
        relevant_claims = [
            claim for claim in self.claims.values()
            if claim.subject == subject and claim.predicate == predicate
        ]
        
        if not relevant_claims:
            return None
        
        # Check if values are numeric
        numeric_claims = []
        for claim in relevant_claims:
            if isinstance(claim.value, (int, float)):
                numeric_claims.append(claim)
        
        if not numeric_claims:
            app_logger.warning(
                f"Cannot use weighted average: values are not numeric"
            )
            return None
        
        # Calculate weighted average
        total_weight = sum(claim.confidence for claim in numeric_claims)
        if total_weight == 0:
            return None
        
        weighted_sum = sum(
            claim.value * claim.confidence for claim in numeric_claims
        )
        synthesized_value = weighted_sum / total_weight
        
        # Calculate synthesized confidence (average of source confidences)
        synthesized_confidence = total_weight / len(numeric_claims)
        
        # Detect and resolve contradictions
        contradictions = self.detect_contradictions(subject, predicate)
        resolved = []
        if contradictions:
            resolved = [c['type'] for c in contradictions]
            app_logger.info(
                f"Resolved {len(contradictions)} contradiction(s) for "
                f"{subject} {predicate}"
            )
        
        # Create synthesized knowledge
        synthesized = SynthesizedKnowledge(
            subject=subject,
            predicate=predicate,
            value=synthesized_value,
            confidence=synthesized_confidence,
            source_claims=[c.claim_id for c in numeric_claims],
            synthesis_method="weighted_average",
            contradictions_resolved=resolved
        )
        
        self.synthesized[synthesized.knowledge_id] = synthesized
        self._save_synthesized(synthesized)
        
        app_logger.info(
            f"Synthesized knowledge: {subject} {predicate} = {synthesized_value} "
            f"(confidence: {synthesized_confidence:.2f}, "
            f"from {len(numeric_claims)} claims)"
        )
        
        return synthesized
    
    def synthesize_majority_vote(
        self,
        subject: str,
        predicate: str
    ) -> Optional[SynthesizedKnowledge]:
        """
        Synthesize knowledge using majority vote.
        
        Selects the value with highest total confidence.
        """
        relevant_claims = [
            claim for claim in self.claims.values()
            if claim.subject == subject and claim.predicate == predicate
        ]
        
        if not relevant_claims:
            return None
        
        # Group by value
        value_groups = defaultdict(list)
        for claim in relevant_claims:
            value_key = json.dumps(claim.value, sort_keys=True)
            value_groups[value_key].append(claim)
        
        # Find value with highest total confidence
        best_value_key = None
        best_confidence = 0.0
        best_claims = []
        
        for value_key, claims in value_groups.items():
            total_confidence = sum(c.confidence for c in claims)
            if total_confidence > best_confidence:
                best_confidence = total_confidence
                best_value_key = value_key
                best_claims = claims
        
        if best_value_key is None:
            return None
        
        synthesized_value = json.loads(best_value_key)
        
        # Normalize confidence
        total_possible = sum(c.confidence for c in relevant_claims)
        synthesized_confidence = best_confidence / total_possible if total_possible > 0 else 0.0
        
        # Detect and resolve contradictions
        contradictions = self.detect_contradictions(subject, predicate)
        resolved = []
        if contradictions:
            resolved = [c['type'] for c in contradictions]
            app_logger.info(
                f"Resolved {len(contradictions)} contradiction(s) for "
                f"{subject} {predicate}"
            )
        
        # Create synthesized knowledge
        synthesized = SynthesizedKnowledge(
            subject=subject,
            predicate=predicate,
            value=synthesized_value,
            confidence=synthesized_confidence,
            source_claims=[c.claim_id for c in best_claims],
            synthesis_method="majority_vote",
            contradictions_resolved=resolved
        )
        
        self.synthesized[synthesized.knowledge_id] = synthesized
        self._save_synthesized(synthesized)
        
        app_logger.info(
            f"Synthesized knowledge: {subject} {predicate} = {synthesized_value} "
            f"(confidence: {synthesized_confidence:.2f}, "
            f"from {len(best_claims)}/{len(relevant_claims)} claims)"
        )
        
        return synthesized
    
    def build_knowledge_graph(self) -> Dict[str, Any]:
        """
        Build a knowledge graph from synthesized knowledge.
        
        Returns graph structure with nodes and edges.
        """
        nodes = set()
        edges = []
        
        for knowledge in self.synthesized.values():
            # Add subject node
            nodes.add(knowledge.subject)
            
            # Add value as object node (if string)
            if isinstance(knowledge.value, str):
                nodes.add(knowledge.value)
                
                # Add edge
                edge = {
                    'subject': knowledge.subject,
                    'predicate': knowledge.predicate,
                    'object': knowledge.value,
                    'confidence': knowledge.confidence
                }
                edges.append(edge)
                
                # Save to database
                self._save_graph_edge(edge)
        
        graph = {
            'nodes': list(nodes),
            'edges': edges,
            'node_count': len(nodes),
            'edge_count': len(edges)
        }
        
        app_logger.info(
            f"Built knowledge graph: {len(nodes)} nodes, {len(edges)} edges"
        )
        
        return graph
    
    def query_knowledge(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None
    ) -> List[SynthesizedKnowledge]:
        """Query synthesized knowledge."""
        results = []
        
        for knowledge in self.synthesized.values():
            if subject and knowledge.subject != subject:
                continue
            if predicate and knowledge.predicate != predicate:
                continue
            results.append(knowledge)
        
        return results
    
    def _save_claim(self, claim: KnowledgeClaim) -> None:
        """Save claim to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO knowledge_claims
                (claim_id, source_type, source_id, subject, predicate, value, confidence, context, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                claim.claim_id,
                claim.source_type.value,
                claim.source_id,
                claim.subject,
                claim.predicate,
                json.dumps(claim.value),
                claim.confidence,
                json.dumps(claim.context),
                claim.timestamp
            ))
            conn.commit()
    
    def _save_synthesized(self, knowledge: SynthesizedKnowledge) -> None:
        """Save synthesized knowledge to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO synthesized_knowledge
                (knowledge_id, subject, predicate, value, confidence, source_claims, synthesis_method, contradictions_resolved, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                knowledge.knowledge_id,
                knowledge.subject,
                knowledge.predicate,
                json.dumps(knowledge.value),
                knowledge.confidence,
                json.dumps(knowledge.source_claims),
                knowledge.synthesis_method,
                json.dumps(knowledge.contradictions_resolved),
                knowledge.timestamp
            ))
            conn.commit()
    
    def _save_graph_edge(self, edge: Dict[str, Any]) -> None:
        """Save knowledge graph edge to database."""
        edge_id = f"edge_{uuid.uuid4().hex[:8]}"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO knowledge_graph
                (edge_id, subject, predicate, object, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                edge_id,
                edge['subject'],
                edge['predicate'],
                edge['object'],
                edge['confidence'],
                _now()
            ))
            conn.commit()


# ============================================================================
# SUBSYSTEM 4: UNCERTAINTY QUANTIFICATION
# ============================================================================

class DistributionType(Enum):
    """Types of probability distributions."""
    NORMAL = "normal"
    UNIFORM = "uniform"
    BERNOULLI = "bernoulli"
    POISSON = "poisson"
    EXPONENTIAL = "exponential"


@dataclass
class ProbabilityDistribution:
    """A probability distribution."""
    dist_id: str = field(default_factory=lambda: f"dist_{uuid.uuid4().hex[:8]}")
    dist_type: DistributionType = DistributionType.NORMAL
    parameters: Dict[str, float] = field(default_factory=dict)
    description: str = ""
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'dist_id': self.dist_id,
            'dist_type': self.dist_type.value,
            'parameters': self.parameters,
            'description': self.description,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProbabilityDistribution':
        return cls(
            dist_id=data['dist_id'],
            dist_type=DistributionType(data.get('dist_type', 'normal')),
            parameters=data.get('parameters', {}),
            description=data.get('description', ''),
            created_at=data.get('created_at', _now())
        )
    
    def sample(self, n: int = 1) -> List[float]:
        """Generate random samples from the distribution."""
        samples = []
        
        if self.dist_type == DistributionType.NORMAL:
            mean = self.parameters.get('mean', 0.0)
            std = self.parameters.get('std', 1.0)
            samples = [random.gauss(mean, std) for _ in range(n)]
        
        elif self.dist_type == DistributionType.UNIFORM:
            low = self.parameters.get('low', 0.0)
            high = self.parameters.get('high', 1.0)
            samples = [random.uniform(low, high) for _ in range(n)]
        
        elif self.dist_type == DistributionType.BERNOULLI:
            p = self.parameters.get('p', 0.5)
            samples = [1.0 if random.random() < p else 0.0 for _ in range(n)]
        
        elif self.dist_type == DistributionType.POISSON:
            lam = self.parameters.get('lambda', 1.0)
            # Simple Poisson sampling
            for _ in range(n):
                L = math.exp(-lam)
                k = 0
                p = 1.0
                while p > L:
                    k += 1
                    p *= random.random()
                samples.append(float(k - 1))
        
        elif self.dist_type == DistributionType.EXPONENTIAL:
            lam = self.parameters.get('lambda', 1.0)
            samples = [random.expovariate(lam) for _ in range(n)]
        
        return samples
    
    def pdf(self, x: float) -> float:
        """Calculate probability density at x."""
        if self.dist_type == DistributionType.NORMAL:
            mean = self.parameters.get('mean', 0.0)
            std = self.parameters.get('std', 1.0)
            return (1.0 / (std * math.sqrt(2 * math.pi))) * \
                   math.exp(-0.5 * ((x - mean) / std) ** 2)
        
        elif self.dist_type == DistributionType.UNIFORM:
            low = self.parameters.get('low', 0.0)
            high = self.parameters.get('high', 1.0)
            if low <= x <= high:
                return 1.0 / (high - low)
            return 0.0
        
        elif self.dist_type == DistributionType.EXPONENTIAL:
            lam = self.parameters.get('lambda', 1.0)
            if x >= 0:
                return lam * math.exp(-lam * x)
            return 0.0
        
        # For discrete distributions, return 0 (not applicable)
        return 0.0


@dataclass
class BayesianUpdate:
    """Result of a Bayesian update."""
    update_id: str = field(default_factory=lambda: f"update_{uuid.uuid4().hex[:8]}")
    prior: ProbabilityDistribution = field(default_factory=ProbabilityDistribution)
    likelihood: str = ""  # Description of likelihood function
    evidence: Dict[str, Any] = field(default_factory=dict)
    posterior: ProbabilityDistribution = field(default_factory=ProbabilityDistribution)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'update_id': self.update_id,
            'prior': self.prior.to_dict(),
            'likelihood': self.likelihood,
            'evidence': self.evidence,
            'posterior': self.posterior.to_dict(),
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BayesianUpdate':
        return cls(
            update_id=data['update_id'],
            prior=ProbabilityDistribution.from_dict(data.get('prior', {})),
            likelihood=data.get('likelihood', ''),
            evidence=data.get('evidence', {}),
            posterior=ProbabilityDistribution.from_dict(data.get('posterior', {})),
            timestamp=data.get('timestamp', _now())
        )


class UncertaintyQuantifier:
    """
    Quantifies uncertainty using probabilistic reasoning.
    
    Features:
    - Probability distributions
    - Bayesian inference
    - Monte Carlo simulation
    - Confidence calibration
    """
    
    def __init__(self, db_path: str = "data/phase14_uncertainty.db"):
        self.db_path = db_path
        self._ensure_db()
        self.distributions: Dict[str, ProbabilityDistribution] = {}
        self.updates: Dict[str, BayesianUpdate] = {}
        app_logger.info("UncertaintyQuantifier initialized")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS probability_distributions (
                    dist_id TEXT PRIMARY KEY,
                    dist_type TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_updates (
                    update_id TEXT PRIMARY KEY,
                    prior TEXT NOT NULL,
                    likelihood TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    posterior TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monte_carlo_results (
                    result_id TEXT PRIMARY KEY,
                    distribution TEXT NOT NULL,
                    samples TEXT NOT NULL,
                    statistics TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def create_distribution(
        self,
        dist_type: DistributionType,
        parameters: Dict[str, float],
        description: str = ""
    ) -> ProbabilityDistribution:
        """Create a probability distribution."""
        dist = ProbabilityDistribution(
            dist_type=dist_type,
            parameters=parameters,
            description=description
        )
        
        self.distributions[dist.dist_id] = dist
        self._save_distribution(dist)
        
        app_logger.info(
            f"Created distribution: {dist_type.value} with parameters {parameters}"
        )
        
        return dist
    
    def monte_carlo_simulation(
        self,
        dist: ProbabilityDistribution,
        n_samples: int = 10000
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation.
        
        Returns statistics about the samples.
        """
        samples = dist.sample(n_samples)
        
        # Calculate statistics
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std = math.sqrt(variance)
        
        # Calculate percentiles
        sorted_samples = sorted(samples)
        p5 = sorted_samples[int(0.05 * len(samples))]
        p25 = sorted_samples[int(0.25 * len(samples))]
        p50 = sorted_samples[int(0.50 * len(samples))]
        p75 = sorted_samples[int(0.75 * len(samples))]
        p95 = sorted_samples[int(0.95 * len(samples))]
        
        statistics = {
            'mean': mean,
            'std': std,
            'variance': variance,
            'min': min(samples),
            'max': max(samples),
            'percentiles': {
                'p5': p5,
                'p25': p25,
                'p50': p50,
                'p75': p75,
                'p95': p95
            }
        }
        
        # Save to database
        result_id = f"mc_{uuid.uuid4().hex[:8]}"
        self._save_monte_carlo_result(result_id, dist, samples, statistics)
        
        app_logger.info(
            f"Monte Carlo simulation: {n_samples} samples, "
            f"mean={mean:.3f}, std={std:.3f}"
        )
        
        return statistics
    
    def bayesian_update_normal(
        self,
        prior: ProbabilityDistribution,
        observation: float,
        observation_noise: float
    ) -> BayesianUpdate:
        """
        Perform Bayesian update for normal distribution.
        
        Assumes normal prior and normal likelihood.
        """
        if prior.dist_type != DistributionType.NORMAL:
            raise ValueError("Prior must be normal distribution")
        
        # Extract prior parameters
        prior_mean = prior.parameters.get('mean', 0.0)
        prior_var = prior.parameters.get('std', 1.0) ** 2
        
        # Likelihood parameters
        likelihood_var = observation_noise ** 2
        
        # Calculate posterior parameters (conjugate update)
        posterior_precision = 1.0 / prior_var + 1.0 / likelihood_var
        posterior_var = 1.0 / posterior_precision
        posterior_mean = posterior_var * (
            prior_mean / prior_var + observation / likelihood_var
        )
        posterior_std = math.sqrt(posterior_var)
        
        # Create posterior distribution
        posterior = ProbabilityDistribution(
            dist_type=DistributionType.NORMAL,
            parameters={
                'mean': posterior_mean,
                'std': posterior_std
            },
            description=f"Posterior after observing {observation}"
        )
        
        # Create update record
        update = BayesianUpdate(
            prior=prior,
            likelihood=f"Normal({observation}, {observation_noise})",
            evidence={'observation': observation, 'noise': observation_noise},
            posterior=posterior
        )
        
        self.updates[update.update_id] = update
        self.distributions[posterior.dist_id] = posterior
        self._save_distribution(posterior)
        self._save_update(update)
        
        app_logger.info(
            f"Bayesian update: prior N({prior_mean:.2f}, {math.sqrt(prior_var):.2f}) → "
            f"posterior N({posterior_mean:.2f}, {posterior_std:.2f})"
        )
        
        return update
    
    def calculate_credible_interval(
        self,
        dist: ProbabilityDistribution,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate credible interval for a distribution.
        
        Returns (lower, upper) bounds.
        """
        # Use Monte Carlo to estimate interval
        n_samples = 10000
        samples = dist.sample(n_samples)
        sorted_samples = sorted(samples)
        
        alpha = 1.0 - confidence
        lower_idx = int(alpha / 2 * n_samples)
        upper_idx = int((1 - alpha / 2) * n_samples)
        
        lower = sorted_samples[lower_idx]
        upper = sorted_samples[upper_idx]
        
        app_logger.info(
            f"{confidence*100:.0f}% credible interval: [{lower:.3f}, {upper:.3f}]"
        )
        
        return (lower, upper)
    
    def calibrate_confidence(
        self,
        predictions: List[float],
        actual: List[float],
        n_bins: int = 10
    ) -> Dict[str, Any]:
        """
        Calibrate confidence scores.
        
        Compares predicted confidence to actual accuracy.
        """
        if len(predictions) != len(actual):
            raise ValueError("predictions and actual must have same length")
        
        # Bin predictions by confidence
        bins = [[] for _ in range(n_bins)]
        for pred, act in zip(predictions, actual):
            bin_idx = min(int(pred * n_bins), n_bins - 1)
            bins[bin_idx].append((pred, act))
        
        # Calculate calibration metrics
        calibration = []
        for i, bin_data in enumerate(bins):
            if not bin_data:
                continue
            
            avg_confidence = sum(p for p, a in bin_data) / len(bin_data)
            accuracy = sum(1 for p, a in bin_data if abs(p - a) < 0.1) / len(bin_data)
            
            calibration.append({
                'bin': i,
                'confidence': avg_confidence,
                'accuracy': accuracy,
                'count': len(bin_data)
            })
        
        # Calculate Expected Calibration Error (ECE)
        ece = sum(
            abs(c['confidence'] - c['accuracy']) * c['count'] / len(predictions)
            for c in calibration
        )
        
        result = {
            'calibration': calibration,
            'expected_calibration_error': ece,
            'n_samples': len(predictions)
        }
        
        app_logger.info(
            f"Confidence calibration: ECE = {ece:.3f} "
            f"(lower is better, 0 = perfect calibration)"
        )
        
        return result
    
    def _save_distribution(self, dist: ProbabilityDistribution) -> None:
        """Save distribution to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO probability_distributions
                (dist_id, dist_type, parameters, description, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                dist.dist_id,
                dist.dist_type.value,
                json.dumps(dist.parameters),
                dist.description,
                dist.created_at
            ))
            conn.commit()
    
    def _save_update(self, update: BayesianUpdate) -> None:
        """Save Bayesian update to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO bayesian_updates
                (update_id, prior, likelihood, evidence, posterior, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                update.update_id,
                json.dumps(update.prior.to_dict()),
                update.likelihood,
                json.dumps(update.evidence),
                json.dumps(update.posterior.to_dict()),
                update.timestamp
            ))
            conn.commit()
    
    def _save_monte_carlo_result(
        self,
        result_id: str,
        dist: ProbabilityDistribution,
        samples: List[float],
        statistics: Dict[str, Any]
    ) -> None:
        """Save Monte Carlo result to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO monte_carlo_results
                (result_id, distribution, samples, statistics, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                result_id,
                json.dumps(dist.to_dict()),
                json.dumps(samples[:100]),  # Save first 100 samples
                json.dumps(statistics),
                _now()
            ))
            conn.commit()


# ============================================================================
# MAIN PHASE 14 CLASS
# ============================================================================

class Phase14AdvancedCognitiveCapabilities:
    """
    Phase 14: Advanced Cognitive Capabilities
    
    Integrates four subsystems:
    1. Resource Management & Optimization
    2. Multi-Agent Coordination
    3. Knowledge Synthesis
    4. Uncertainty Quantification
    """
    
    def __init__(self, db_path: str = "data/phase14.db"):
        self.db_path = db_path
        self.resource_manager = ResourceManager(db_path)
        self.coordinator = MultiAgentCoordinator(db_path=db_path)
        self.knowledge_synthesizer = KnowledgeSynthesizer(db_path)
        self.uncertainty_quantifier = UncertaintyQuantifier(db_path)
        
        app_logger.info("Phase 14: Advanced Cognitive Capabilities initialized")
    
    def get_phase14_report(self) -> Dict[str, Any]:
        """Get comprehensive Phase 14 status report."""
        return {
            'resource_management': self.resource_manager.get_usage_report(),
            'multi_agent_coordination': self.coordinator.get_coordination_report(),
            'knowledge_synthesis': {
                'total_claims': len(self.knowledge_synthesizer.claims),
                'total_synthesized': len(self.knowledge_synthesizer.synthesized)
            },
            'uncertainty_quantification': {
                'total_distributions': len(self.uncertainty_quantifier.distributions),
                'total_updates': len(self.uncertainty_quantifier.updates)
            }
        }
