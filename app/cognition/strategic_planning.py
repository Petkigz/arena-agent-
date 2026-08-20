"""
Phase 13: Long-Term Strategic Planning

Enables the agent to:
1. Plan goals over extended time horizons (months/years)
2. Coordinate multi-step objectives
3. Optimize for long-term outcomes
4. Balance short-term vs long-term tradeoffs
5. Track milestones and progress
6. Adapt strategies based on changing conditions

This is critical for human-level AGI - the ability to think and plan strategically over time.
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class TimeHorizon(Enum):
    """Time horizon for planning."""
    IMMEDIATE = "immediate"  # Minutes to hours
    SHORT_TERM = "short_term"  # Days to weeks
    MEDIUM_TERM = "medium_term"  # Weeks to months
    LONG_TERM = "long_term"  # Months to years
    VERY_LONG_TERM = "very_long_term"  # Years to decades


class PlanStatus(Enum):
    """Status of a strategic plan."""
    DRAFT = "draft"  # Being created
    ACTIVE = "active"  # Currently executing
    PAUSED = "paused"  # Temporarily suspended
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Failed to complete
    CANCELLED = "cancelled"  # Abandoned
    SUPERSEDED = "superseded"  # Replaced by better plan


class MilestoneStatus(Enum):
    """Status of a milestone."""
    PENDING = "pending"  # Not started
    IN_PROGRESS = "in_progress"  # Currently working on
    COMPLETED = "completed"  # Successfully achieved
    FAILED = "failed"  # Failed to achieve
    SKIPPED = "skipped"  # Deliberately skipped


@dataclass
class Milestone:
    """A significant checkpoint in a strategic plan."""
    milestone_id: str = field(default_factory=lambda: f"milestone_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    target_date: str = ""  # ISO format datetime
    actual_date: Optional[str] = None
    status: MilestoneStatus = MilestoneStatus.PENDING
    success_criteria: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Other milestone IDs
    progress: float = 0.0  # 0.0 to 1.0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'milestone_id': self.milestone_id,
            'name': self.name,
            'description': self.description,
            'target_date': self.target_date,
            'actual_date': self.actual_date,
            'status': self.status.value,
            'success_criteria': self.success_criteria,
            'dependencies': self.dependencies,
            'progress': self.progress,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Milestone':
        """Create from dictionary."""
        return cls(
            milestone_id=data['milestone_id'],
            name=data['name'],
            description=data['description'],
            target_date=data['target_date'],
            actual_date=data.get('actual_date'),
            status=MilestoneStatus(data['status']),
            success_criteria=data.get('success_criteria', []),
            dependencies=data.get('dependencies', []),
            progress=data.get('progress', 0.0),
            created_at=data.get('created_at', _now()),
            updated_at=data.get('updated_at', _now())
        )


@dataclass
class StrategicPlan:
    """A long-term strategic plan."""
    plan_id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    name: str = ""
    description: str = ""
    vision: str = ""  # Long-term vision this plan supports
    time_horizon: TimeHorizon = TimeHorizon.LONG_TERM
    start_date: str = field(default_factory=_now)
    target_end_date: str = ""
    actual_end_date: Optional[str] = None
    status: PlanStatus = PlanStatus.DRAFT
    
    # Strategic elements
    objectives: List[str] = field(default_factory=list)  # High-level objectives
    key_results: List[str] = field(default_factory=list)  # Measurable outcomes
    milestones: List[Milestone] = field(default_factory=list)
    
    # Resource allocation
    estimated_effort: str = "high"  # low, medium, high, very_high
    required_resources: List[str] = field(default_factory=list)
    allocated_resources: Dict[str, Any] = field(default_factory=dict)
    
    # Progress tracking
    overall_progress: float = 0.0  # 0.0 to 1.0
    milestones_completed: int = 0
    milestones_total: int = 0
    
    # Strategic analysis
    swot_analysis: Dict[str, List[str]] = field(default_factory=lambda: {
        'strengths': [],
        'weaknesses': [],
        'opportunities': [],
        'threats': []
    })
    risks: List[Dict[str, Any]] = field(default_factory=list)
    contingencies: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    priority: float = 0.5  # 0.0 to 1.0
    alignment_score: float = 0.0  # How well this aligns with overall vision
    expected_value: float = 0.0  # Expected value/benefit
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'plan_id': self.plan_id,
            'name': self.name,
            'description': self.description,
            'vision': self.vision,
            'time_horizon': self.time_horizon.value,
            'start_date': self.start_date,
            'target_end_date': self.target_end_date,
            'actual_end_date': self.actual_end_date,
            'status': self.status.value,
            'objectives': self.objectives,
            'key_results': self.key_results,
            'milestones': [m.to_dict() for m in self.milestones],
            'estimated_effort': self.estimated_effort,
            'required_resources': self.required_resources,
            'allocated_resources': self.allocated_resources,
            'overall_progress': self.overall_progress,
            'milestones_completed': self.milestones_completed,
            'milestones_total': self.milestones_total,
            'swot_analysis': self.swot_analysis,
            'risks': self.risks,
            'contingencies': self.contingencies,
            'priority': self.priority,
            'alignment_score': self.alignment_score,
            'expected_value': self.expected_value,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategicPlan':
        """Create from dictionary."""
        return cls(
            plan_id=data['plan_id'],
            name=data['name'],
            description=data['description'],
            vision=data.get('vision', ''),
            time_horizon=TimeHorizon(data['time_horizon']),
            start_date=data['start_date'],
            target_end_date=data['target_end_date'],
            actual_end_date=data.get('actual_end_date'),
            status=PlanStatus(data['status']),
            objectives=data.get('objectives', []),
            key_results=data.get('key_results', []),
            milestones=[Milestone.from_dict(m) for m in data.get('milestones', [])],
            estimated_effort=data.get('estimated_effort', 'high'),
            required_resources=data.get('required_resources', []),
            allocated_resources=data.get('allocated_resources', {}),
            overall_progress=data.get('overall_progress', 0.0),
            milestones_completed=data.get('milestones_completed', 0),
            milestones_total=data.get('milestones_total', 0),
            swot_analysis=data.get('swot_analysis', {
                'strengths': [],
                'weaknesses': [],
                'opportunities': [],
                'threats': []
            }),
            risks=data.get('risks', []),
            contingencies=data.get('contingencies', []),
            priority=data.get('priority', 0.5),
            alignment_score=data.get('alignment_score', 0.0),
            expected_value=data.get('expected_value', 0.0),
            created_at=data.get('created_at', _now()),
            updated_at=data.get('updated_at', _now())
        )


class StrategicPlanningEngine:
    """
    Engine for long-term strategic planning and execution.
    
    Provides methods for:
    - Creating strategic plans with milestones
    - Tracking progress over time
    - Balancing short-term vs long-term goals
    - Adapting strategies based on conditions
    - Resource allocation over time
    """
    
    def __init__(self, db_path: str = "data/strategic_planning.db"):
        """Initialize the strategic planning engine."""
        self.db_path = db_path
        self._ensure_db()
        app_logger.info(f"Strategic Planning Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategic_plans (
                    plan_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    plan_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_plans_status
                ON strategic_plans(json_extract(plan_data, '$.status'))
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_plans_horizon
                ON strategic_plans(json_extract(plan_data, '$.time_horizon'))
            """)
            
            conn.commit()
    
    def create_strategic_plan(
        self,
        name: str,
        description: str,
        vision: str,
        time_horizon: TimeHorizon,
        target_end_date: str,
        objectives: List[str],
        key_results: List[str],
        estimated_effort: str = "high"
    ) -> StrategicPlan:
        """
        Create a new strategic plan.
        
        Args:
            name: Plan name
            description: Plan description
            vision: Long-term vision this supports
            time_horizon: Time horizon for the plan
            target_end_date: Target completion date (ISO format)
            objectives: High-level objectives
            key_results: Measurable outcomes
            estimated_effort: Estimated effort level
        
        Returns:
            Created StrategicPlan
        """
        plan = StrategicPlan(
            name=name,
            description=description,
            vision=vision,
            time_horizon=time_horizon,
            target_end_date=target_end_date,
            objectives=objectives,
            key_results=key_results,
            estimated_effort=estimated_effort,
            milestones_total=0,
            milestones_completed=0
        )
        
        # Save to database
        self._save_plan(plan)
        
        app_logger.info(f"Created strategic plan: {name} (horizon: {time_horizon.value})")
        
        return plan
    
    def add_milestone(
        self,
        plan_id: str,
        name: str,
        description: str,
        target_date: str,
        success_criteria: List[str],
        dependencies: List[str] = None
    ) -> Optional[Milestone]:
        """
        Add a milestone to a strategic plan.
        
        Args:
            plan_id: Plan ID
            name: Milestone name
            description: Milestone description
            target_date: Target completion date (ISO format)
            success_criteria: List of success criteria
            dependencies: List of dependent milestone IDs
        
        Returns:
            Created Milestone or None if plan not found
        """
        plan = self.get_plan(plan_id)
        if not plan:
            app_logger.error(f"Plan {plan_id} not found")
            return None
        
        milestone = Milestone(
            name=name,
            description=description,
            target_date=target_date,
            success_criteria=success_criteria,
            dependencies=dependencies or []
        )
        
        plan.milestones.append(milestone)
        plan.milestones_total = len(plan.milestones)
        plan.updated_at = _now()
        
        # Save updated plan
        self._save_plan(plan)
        
        app_logger.info(f"Added milestone '{name}' to plan '{plan.name}'")
        
        return milestone
    
    def update_milestone_status(
        self,
        plan_id: str,
        milestone_id: str,
        status: MilestoneStatus,
        progress: float = None
    ) -> bool:
        """
        Update milestone status and progress.
        
        Args:
            plan_id: Plan ID
            milestone_id: Milestone ID
            status: New status
            progress: Progress (0.0 to 1.0)
        
        Returns:
            True if successful, False otherwise
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return False
        
        # Find milestone
        milestone = None
        for m in plan.milestones:
            if m.milestone_id == milestone_id:
                milestone = m
                break
        
        if not milestone:
            app_logger.error(f"Milestone {milestone_id} not found in plan {plan_id}")
            return False
        
        # Update status
        milestone.status = status
        milestone.updated_at = _now()
        
        if progress is not None:
            milestone.progress = progress
        
        if status == MilestoneStatus.COMPLETED:
            milestone.actual_date = _now()
            milestone.progress = 1.0
            plan.milestones_completed += 1
        elif status == MilestoneStatus.FAILED:
            milestone.actual_date = _now()
        
        # Update overall progress
        if plan.milestones_total > 0:
            total_progress = sum(m.progress for m in plan.milestones)
            plan.overall_progress = total_progress / plan.milestones_total
        
        plan.updated_at = _now()
        
        # Save updated plan
        self._save_plan(plan)
        
        app_logger.info(f"Updated milestone '{milestone.name}' status to {status.value}")
        
        return True
    
    def get_plan(self, plan_id: str) -> Optional[StrategicPlan]:
        """
        Get a strategic plan by ID.
        
        Args:
            plan_id: Plan ID
        
        Returns:
            StrategicPlan or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT plan_data FROM strategic_plans WHERE plan_id = ?",
                (plan_id,)
            )
            row = cursor.fetchone()
            
            if row:
                plan_data = json.loads(row[0])
                return StrategicPlan.from_dict(plan_data)
            
            return None
    
    def list_plans(
        self,
        status: Optional[PlanStatus] = None,
        time_horizon: Optional[TimeHorizon] = None,
        limit: int = 100
    ) -> List[StrategicPlan]:
        """
        List strategic plans with optional filters.
        
        Args:
            status: Filter by status
            time_horizon: Filter by time horizon
            limit: Maximum number of plans to return
        
        Returns:
            List of StrategicPlan objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT plan_data FROM strategic_plans WHERE 1=1"
            params = []
            
            if status:
                query += " AND json_extract(plan_data, '$.status') = ?"
                params.append(status.value)
            
            if time_horizon:
                query += " AND json_extract(plan_data, '$.time_horizon') = ?"
                params.append(time_horizon.value)
            
            query += " ORDER BY json_extract(plan_data, '$.priority') DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            plans = []
            for row in cursor.fetchall():
                plan_data = json.loads(row[0])
                plans.append(StrategicPlan.from_dict(plan_data))
            
            return plans
    
    def get_active_plans(self) -> List[StrategicPlan]:
        """Get all active strategic plans."""
        return self.list_plans(status=PlanStatus.ACTIVE)
    
    def get_next_milestone(self, plan_id: str) -> Optional[Milestone]:
        """
        Get the next pending milestone for a plan.
        
        Args:
            plan_id: Plan ID
        
        Returns:
            Next Milestone or None if no pending milestones
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        
        # Find pending milestones with all dependencies met
        for milestone in plan.milestones:
            if milestone.status == MilestoneStatus.PENDING:
                # Check if all dependencies are completed
                deps_met = True
                for dep_id in milestone.dependencies:
                    dep_milestone = next((m for m in plan.milestones if m.milestone_id == dep_id), None)
                    if not dep_milestone or dep_milestone.status != MilestoneStatus.COMPLETED:
                        deps_met = False
                        break
                
                if deps_met:
                    return milestone
        
        return None
    
    def balance_short_term_vs_long_term(
        self,
        short_term_goals: List[Dict[str, Any]],
        long_term_plans: List[StrategicPlan]
    ) -> Dict[str, Any]:
        """
        Balance short-term goals against long-term strategic plans.
        
        Args:
            short_term_goals: List of short-term goals with priorities
            long_term_plans: List of active long-term plans
        
        Returns:
            Recommendation dict with prioritized actions
        """
        recommendations = []
        
        # Calculate total resource allocation
        total_resources = 100.0  # Percentage
        long_term_allocation = sum(p.allocated_resources.get('percentage', 0) for p in long_term_plans)
        short_term_allocation = total_resources - long_term_allocation
        
        # Analyze each short-term goal
        for goal in short_term_goals:
            goal_priority = goal.get('priority', 0.5)
            goal_effort = goal.get('estimated_effort', 'medium')
            
            # Check if goal supports any long-term plan
            supports_long_term = False
            for plan in long_term_plans:
                # Check for keyword overlap between goal and plan objectives
                goal_desc = goal.get('description', '').lower()
                goal_words = set(goal_desc.split())
                
                for obj in plan.objectives:
                    obj_words = set(obj.lower().split())
                    # If there's significant keyword overlap (at least one meaningful word)
                    overlap = goal_words & obj_words
                    # Filter out common words
                    meaningful_overlap = overlap - {'the', 'a', 'an', 'for', 'to', 'in', 'of', 'and', 'or'}
                    if meaningful_overlap:
                        supports_long_term = True
                        break
                
                if supports_long_term:
                    break
            
            # Prioritize goals that support long-term plans
            if supports_long_term:
                adjusted_priority = min(1.0, goal_priority + 0.2)
                recommendations.append({
                    'goal': goal,
                    'adjusted_priority': adjusted_priority,
                    'reason': 'Supports long-term strategic plan',
                    'recommended': True
                })
            elif goal_priority > 0.8:
                # High priority short-term goals still get done
                recommendations.append({
                    'goal': goal,
                    'adjusted_priority': goal_priority,
                    'reason': 'High priority immediate need',
                    'recommended': True
                })
            else:
                # Lower priority short-term goals may be deferred
                recommendations.append({
                    'goal': goal,
                    'adjusted_priority': goal_priority,
                    'reason': 'Consider deferring to focus on strategic plans',
                    'recommended': short_term_allocation > 30  # Only if we have spare capacity
                })
        
        # Sort by adjusted priority
        recommendations.sort(key=lambda r: r['adjusted_priority'], reverse=True)
        
        return {
            'recommendations': recommendations,
            'long_term_allocation': long_term_allocation,
            'short_term_allocation': short_term_allocation,
            'balance_score': self._calculate_balance_score(long_term_allocation, short_term_allocation)
        }
    
    def _calculate_balance_score(self, long_term: float, short_term: float) -> float:
        """
        Calculate how well balanced the allocation is.
        
        Ideal is around 60-70% long-term, 30-40% short-term.
        """
        # Ideal range: 60-70% long-term
        if 60 <= long_term <= 70:
            return 1.0
        elif 50 <= long_term < 60 or 70 < long_term <= 80:
            return 0.8
        elif 40 <= long_term < 50 or 80 < long_term <= 90:
            return 0.6
        else:
            return 0.4
    
    def adapt_strategy(
        self,
        plan_id: str,
        reason: str,
        changes: Dict[str, Any]
    ) -> bool:
        """
        Adapt a strategic plan based on changing conditions.
        
        Args:
            plan_id: Plan ID
            reason: Reason for adaptation
            changes: Dictionary of changes to apply
        
        Returns:
            True if successful, False otherwise
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return False
        
        # Apply changes
        if 'target_end_date' in changes:
            plan.target_end_date = changes['target_end_date']
        
        if 'objectives' in changes:
            plan.objectives = changes['objectives']
        
        if 'priority' in changes:
            plan.priority = changes['priority']
        
        if 'status' in changes:
            plan.status = PlanStatus(changes['status'])
        
        plan.updated_at = _now()
        
        # Log adaptation
        app_logger.info(f"Adapted plan '{plan.name}': {reason}")
        
        # Save updated plan
        self._save_plan(plan)
        
        return True
    
    def _save_plan(self, plan: StrategicPlan) -> None:
        """Save a strategic plan to database."""
        plan_data = json.dumps(plan.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO strategic_plans
                (plan_id, name, plan_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                plan.plan_id,
                plan.name,
                plan_data,
                plan.created_at,
                plan.updated_at
            ))
            conn.commit()
    
    def get_plan_summary(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a summary of a strategic plan.
        
        Args:
            plan_id: Plan ID
        
        Returns:
            Summary dict or None if plan not found
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        
        return {
            'plan_id': plan.plan_id,
            'name': plan.name,
            'status': plan.status.value,
            'time_horizon': plan.time_horizon.value,
            'overall_progress': plan.overall_progress,
            'milestones_completed': plan.milestones_completed,
            'milestones_total': plan.milestones_total,
            'target_end_date': plan.target_end_date,
            'priority': plan.priority,
            'next_milestone': self.get_next_milestone(plan_id)
        }
    
    def get_strategic_overview(self) -> Dict[str, Any]:
        """
        Get an overview of all strategic plans.
        
        Returns:
            Overview dict with statistics and active plans
        """
        all_plans = self.list_plans()
        active_plans = [p for p in all_plans if p.status == PlanStatus.ACTIVE]
        
        # Calculate statistics
        total_milestones = sum(p.milestones_total for p in all_plans)
        completed_milestones = sum(p.milestones_completed for p in all_plans)
        
        # Group by time horizon
        by_horizon = {}
        for horizon in TimeHorizon:
            by_horizon[horizon.value] = len([p for p in all_plans if p.time_horizon == horizon])
        
        return {
            'total_plans': len(all_plans),
            'active_plans': len(active_plans),
            'total_milestones': total_milestones,
            'completed_milestones': completed_milestones,
            'completion_rate': completed_milestones / total_milestones if total_milestones > 0 else 0.0,
            'plans_by_horizon': by_horizon,
            'active_plan_names': [p.name for p in active_plans]
        }
