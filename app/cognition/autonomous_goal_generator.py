"""
Phase 7: Autonomous Goal Generation

This module enables the agent to generate its own goals without explicit user input,
based on:
1. Environmental observations and anomalies
2. Information gaps and curiosity
3. Competence improvement opportunities
4. User behavior patterns
5. System optimization needs

This is a key step toward AGI - agents that can self-direct and pursue meaningful
objectives autonomously.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoalSource(str, Enum):
    """Source of goal generation."""
    ENVIRONMENT_ANOMALY = "environment_anomaly"  # Detected unusual state
    INFORMATION_GAP = "information_gap"  # Missing knowledge
    COMPETENCE_IMPROVEMENT = "competence_improvement"  # Skill enhancement
    USER_PATTERN = "user_pattern"  # Recurring user behavior
    SYSTEM_OPTIMIZATION = "system_optimization"  # Performance improvement
    CURIOSITY = "curiosity"  # Exploratory drive
    MAINTENANCE = "maintenance"  # Routine upkeep


class GoalPriority(str, Enum):
    """Goal priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class GoalStatus(str, Enum):
    """Goal lifecycle status.

    APPROVED means "approved for PLANNING + enqueued" — it does NOT authorize any
    action. Each action produced during execution is authorized independently by
    ActionGate → PolicyEvaluator (see GoalApproval and approve_goal). Level-3
    actions always require owner approval regardless of goal status.
    """
    PROPOSED = "proposed"  # Generated but not yet evaluated
    EVALUATED = "evaluated"  # Assessed for feasibility and value
    APPROVED = "approved"  # Approved for planning (execution still gated per-action)
    IN_PROGRESS = "in_progress"  # Currently being pursued
    COMPLETED = "completed"  # Successfully achieved
    FAILED = "failed"  # Failed to achieve
    DEFERRED = "deferred"  # Postponed for later
    WAITING_APPROVAL = "waiting_approval"  # Plan hit a Level-3 action; awaiting owner
    REJECTED = "rejected"  # Rejected during evaluation


@dataclass
class GoalApproval:
    """Explicit separation of goal approval from action authorization (P0 fix).

    Approving a *goal* authorizes only *goal selection and planning*. It does NOT
    authorize the actions the goal will take — those are authorized individually
    by ActionGate inside `CognitiveRuntime.process_cognitive_cycle()`:

        Goal approved (planning)  ≠  Actions approved

    - `max_action_level`: the highest safety level the goal may auto-execute.
      Levels are the manifest's safety levels (0 read / 1 draft / 2 reversible /
      3 sensitive). The default is 2, so any Level-3 action the goal's plan
      touches will still surface for explicit owner approval.
    - `requires_owner_approval`: set True when the goal is expected to involve
      Level-3 actions; the executor then records such steps as WAITING_APPROVAL
      rather than completing them.
    - `policy_snapshot`: a record of the policy boundary in effect at approval time.
    """
    goal_id: str
    planning_allowed: bool = True   # the goal may be planned + enqueued
    execution_allowed: bool = False  # reserved for full autonomous execution (not used)
    max_action_level: int = 2        # highest auto-executable safety level
    requires_owner_approval: bool = False
    policy_snapshot: str = "Level 3 actions always require owner approval"


class IntrinsicMotivation(str, Enum):
    """Intrinsic motivation types that drive goal generation."""
    CURIOSITY = "curiosity"  # Desire to learn and explore
    COMPETENCE = "competence"  # Desire to improve skills
    AUTONOMY = "autonomy"  # Desire for self-direction
    MASTERY = "mastery"  # Desire to perfect abilities
    HELPFULNESS = "helpfulness"  # Desire to assist users


@dataclass
class AutonomousGoal:
    """A self-generated goal."""
    goal_id: str = field(default_factory=lambda: f"goal_{uuid4().hex[:12]}")
    title: str = ""
    description: str = ""
    source: GoalSource = GoalSource.CURIOSITY
    motivation: IntrinsicMotivation = IntrinsicMotivation.CURIOSITY
    priority: GoalPriority = GoalPriority.NORMAL
    status: GoalStatus = GoalStatus.PROPOSED
    
    # Goal content
    target_state: str = ""  # What we want to achieve
    current_state: str = ""  # Current situation
    success_criteria: List[str] = field(default_factory=list)
    
    # Execution context
    estimated_effort: str = "unknown"  # low, medium, high
    dependencies: List[str] = field(default_factory=list)  # Other goal IDs
    related_goals: List[str] = field(default_factory=list)
    
    # Evaluation metrics
    feasibility_score: float = 0.0  # 0-1, how achievable
    value_score: float = 0.0  # 0-1, how valuable
    urgency_score: float = 0.0  # 0-1, how time-sensitive
    overall_score: float = 0.0  # Combined score
    
    # Approval boundary (P0: goal approval ≠ action authorization)
    max_action_level: int = 2  # highest auto-executable safety level (≥3 → owner)
    requires_owner_approval: bool = False  # set when planning expects Level-3 actions
    
    # Tracking
    created_at: str = field(default_factory=_now)
    evaluated_at: Optional[str] = None
    approved_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Metadata
    trigger_observation: Optional[str] = None  # What triggered this goal
    user_benefit: Optional[str] = None  # How this helps the user
    system_benefit: Optional[str] = None  # How this helps the system
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "source": self.source.value,
            "motivation": self.motivation.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "target_state": self.target_state,
            "current_state": self.current_state,
            "success_criteria": self.success_criteria,
            "estimated_effort": self.estimated_effort,
            "dependencies": self.dependencies,
            "related_goals": self.related_goals,
            "feasibility_score": self.feasibility_score,
            "value_score": self.value_score,
            "urgency_score": self.urgency_score,
            "overall_score": self.overall_score,
            "max_action_level": self.max_action_level,
            "requires_owner_approval": self.requires_owner_approval,
            "created_at": self.created_at,
            "evaluated_at": self.evaluated_at,
            "approved_at": self.approved_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "trigger_observation": self.trigger_observation,
            "user_benefit": self.user_benefit,
            "system_benefit": self.system_benefit,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AutonomousGoal':
        """Create from dictionary."""
        return cls(
            goal_id=data.get("goal_id", f"goal_{uuid4().hex[:12]}"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            source=GoalSource(data.get("source", "curiosity")),
            motivation=IntrinsicMotivation(data.get("motivation", "curiosity")),
            priority=GoalPriority(data.get("priority", "normal")),
            status=GoalStatus(data.get("status", "proposed")),
            target_state=data.get("target_state", ""),
            current_state=data.get("current_state", ""),
            success_criteria=data.get("success_criteria", []),
            estimated_effort=data.get("estimated_effort", "unknown"),
            dependencies=data.get("dependencies", []),
            related_goals=data.get("related_goals", []),
            feasibility_score=data.get("feasibility_score", 0.0),
            value_score=data.get("value_score", 0.0),
            urgency_score=data.get("urgency_score", 0.0),
            overall_score=data.get("overall_score", 0.0),
            max_action_level=data.get("max_action_level", 2),
            requires_owner_approval=data.get("requires_owner_approval", False),
            created_at=data.get("created_at", _now()),
            evaluated_at=data.get("evaluated_at"),
            approved_at=data.get("approved_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            trigger_observation=data.get("trigger_observation"),
            user_benefit=data.get("user_benefit"),
            system_benefit=data.get("system_benefit"),
        )


class AutonomousGoalGenerator:
    """
    Generates autonomous goals based on environmental observations and intrinsic motivations.
    
    This is a key AGI capability - the ability to self-direct and pursue meaningful
    objectives without explicit user instruction.
    """
    
    def __init__(self, db_path: str = "data/autonomous_goals.db"):
        """Initialize the autonomous goal generator."""
        self.db_path = db_path
        self._ensure_db()
        
        # Initialize ethical reasoning system
        from app.cognition.ethical_reasoning import EthicalReasoningSystem
        self.ethical_system = EthicalReasoningSystem(db_path=db_path)
        
        app_logger.info("Autonomous Goal Generator initialized with ethical reasoning")
    
    def _ensure_db(self):
        """Ensure the database exists and has the right schema."""
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_goals (
                    goal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source TEXT NOT NULL,
                    motivation TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_state TEXT,
                    current_state TEXT,
                    success_criteria TEXT,
                    estimated_effort TEXT,
                    dependencies TEXT,
                    related_goals TEXT,
                    feasibility_score REAL,
                    value_score REAL,
                    urgency_score REAL,
                    overall_score REAL,
                    created_at TEXT NOT NULL,
                    evaluated_at TEXT,
                    approved_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    trigger_observation TEXT,
                    user_benefit TEXT,
                    system_benefit TEXT
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON autonomous_goals(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON autonomous_goals(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON autonomous_goals(priority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_overall_score ON autonomous_goals(overall_score)")
            
            # Migration: add the approval-boundary columns if missing (older DBs).
            cols = {r[1] for r in conn.execute("PRAGMA table_info(autonomous_goals)").fetchall()}
            if "max_action_level" not in cols:
                conn.execute("ALTER TABLE autonomous_goals ADD COLUMN max_action_level INTEGER DEFAULT 2")
            if "requires_owner_approval" not in cols:
                conn.execute("ALTER TABLE autonomous_goals ADD COLUMN requires_owner_approval INTEGER DEFAULT 0")
            
            conn.commit()
    
    def generate_goals_from_observation(
        self,
        observation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[AutonomousGoal]:
        """
        Generate goals based on an environmental observation.
        
        Args:
            observation: What was observed
            context: Additional context about the observation
            
        Returns:
            List of generated goals
        """
        generated_goals = []
        context = context or {}
        
        # Detect anomalies and opportunities
        observation_lower = observation.lower()
        
        # Information gap detection
        if any(word in observation_lower for word in ["unknown", "missing", "unclear", "uncertain"]):
            goal = self._create_information_gap_goal(observation, context)
            if goal:
                generated_goals.append(goal)
        
        # System optimization detection
        if any(word in observation_lower for word in ["slow", "error", "failed", "inefficient"]):
            goal = self._create_optimization_goal(observation, context)
            if goal:
                generated_goals.append(goal)
        
        # Maintenance detection
        if any(word in observation_lower for word in ["old", "outdated", "expired", "stale"]):
            goal = self._create_maintenance_goal(observation, context)
            if goal:
                generated_goals.append(goal)
        
        # Pattern detection (user behavior)
        if "user" in observation_lower and any(word in observation_lower for word in ["frequently", "often", "repeatedly"]):
            goal = self._create_user_pattern_goal(observation, context)
            if goal:
                generated_goals.append(goal)
        
        # Curiosity-driven exploration
        if any(word in observation_lower for word in ["new", "unfamiliar", "interesting"]):
            goal = self._create_curiosity_goal(observation, context)
            if goal:
                generated_goals.append(goal)
        
        # Save generated goals
        for goal in generated_goals:
            self.add_goal(goal)
            app_logger.info(f"Generated autonomous goal: {goal.title} (source: {goal.source.value})")
        
        return generated_goals
    
    def _create_information_gap_goal(self, observation: str, context: Dict[str, Any]) -> Optional[AutonomousGoal]:
        """Create a goal to fill an information gap."""
        return AutonomousGoal(
            title="Investigate information gap",
            description=f"Explore and understand: {observation}",
            source=GoalSource.INFORMATION_GAP,
            motivation=IntrinsicMotivation.CURIOSITY,
            priority=GoalPriority.NORMAL,
            target_state="Information gap filled with verified knowledge",
            current_state=observation,
            success_criteria=[
                "Information gathered from reliable sources",
                "Knowledge integrated into belief system",
                "Confidence level above 0.7"
            ],
            estimated_effort="medium",
            feasibility_score=0.8,
            value_score=0.7,
            urgency_score=0.5,
            overall_score=0.67,
            trigger_observation=observation,
            user_benefit="Better understanding leads to more accurate responses",
            system_benefit="Expanded knowledge base"
        )
    
    def _create_optimization_goal(self, observation: str, context: Dict[str, Any]) -> Optional[AutonomousGoal]:
        """Create a goal to optimize system performance."""
        return AutonomousGoal(
            title="Optimize system performance",
            description=f"Address performance issue: {observation}",
            source=GoalSource.SYSTEM_OPTIMIZATION,
            motivation=IntrinsicMotivation.COMPETENCE,
            priority=GoalPriority.HIGH,
            target_state="System operates efficiently without errors",
            current_state=observation,
            success_criteria=[
                "Root cause identified",
                "Solution implemented",
                "Performance metrics improved"
            ],
            estimated_effort="high",
            feasibility_score=0.7,
            value_score=0.9,
            urgency_score=0.8,
            overall_score=0.8,
            trigger_observation=observation,
            user_benefit="Faster, more reliable service",
            system_benefit="Improved efficiency and stability"
        )
    
    def _create_maintenance_goal(self, observation: str, context: Dict[str, Any]) -> Optional[AutonomousGoal]:
        """Create a goal for system maintenance."""
        return AutonomousGoal(
            title="Perform system maintenance",
            description=f"Address maintenance need: {observation}",
            source=GoalSource.MAINTENANCE,
            motivation=IntrinsicMotivation.COMPETENCE,
            priority=GoalPriority.NORMAL,
            target_state="System components up to date and healthy",
            current_state=observation,
            success_criteria=[
                "Outdated components identified",
                "Updates or replacements applied",
                "System health verified"
            ],
            estimated_effort="medium",
            feasibility_score=0.9,
            value_score=0.6,
            urgency_score=0.4,
            overall_score=0.63,
            trigger_observation=observation,
            user_benefit="Continued reliable operation",
            system_benefit="Prevention of degradation"
        )
    
    def _create_user_pattern_goal(self, observation: str, context: Dict[str, Any]) -> Optional[AutonomousGoal]:
        """Create a goal based on user behavior patterns."""
        return AutonomousGoal(
            title="Adapt to user pattern",
            description=f"Optimize for recurring user behavior: {observation}",
            source=GoalSource.USER_PATTERN,
            motivation=IntrinsicMotivation.HELPFULNESS,
            priority=GoalPriority.NORMAL,
            target_state="System optimized for user's common tasks",
            current_state=observation,
            success_criteria=[
                "Pattern confirmed through multiple observations",
                "Optimization strategy developed",
                "User experience improved"
            ],
            estimated_effort="medium",
            feasibility_score=0.8,
            value_score=0.8,
            urgency_score=0.5,
            overall_score=0.7,
            trigger_observation=observation,
            user_benefit="More personalized and efficient service",
            system_benefit="Better user satisfaction"
        )
    
    def _create_curiosity_goal(self, observation: str, context: Dict[str, Any]) -> Optional[AutonomousGoal]:
        """Create an exploratory goal driven by curiosity."""
        return AutonomousGoal(
            title="Explore new opportunity",
            description=f"Investigate interesting observation: {observation}",
            source=GoalSource.CURIOSITY,
            motivation=IntrinsicMotivation.CURIOSITY,
            priority=GoalPriority.LOW,
            target_state="New knowledge or capability acquired",
            current_state=observation,
            success_criteria=[
                "Observation thoroughly investigated",
                "Potential applications identified",
                "Findings documented"
            ],
            estimated_effort="low",
            feasibility_score=0.9,
            value_score=0.5,
            urgency_score=0.2,
            overall_score=0.53,
            trigger_observation=observation,
            user_benefit="Expanded capabilities",
            system_benefit="Continuous learning and growth"
        )
    
    def evaluate_goal(self, goal: AutonomousGoal) -> AutonomousGoal:
        """
        Evaluate a goal for feasibility, value, and urgency.
        
        Args:
            goal: The goal to evaluate
            
        Returns:
            The goal with updated evaluation scores
        """
        # Simple heuristic evaluation (could be enhanced with ML)
        
        # Feasibility: based on estimated effort and dependencies
        effort_scores = {"low": 0.9, "medium": 0.7, "high": 0.5, "unknown": 0.5}
        base_feasibility = effort_scores.get(goal.estimated_effort, 0.5)
        dependency_penalty = len(goal.dependencies) * 0.1
        goal.feasibility_score = max(0.0, base_feasibility - dependency_penalty)
        
        # Value: based on source and motivation
        source_values = {
            GoalSource.SYSTEM_OPTIMIZATION: 0.9,
            GoalSource.USER_PATTERN: 0.8,
            GoalSource.INFORMATION_GAP: 0.7,
            GoalSource.ENVIRONMENT_ANOMALY: 0.7,
            GoalSource.COMPETENCE_IMPROVEMENT: 0.6,
            GoalSource.MAINTENANCE: 0.6,
            GoalSource.CURIOSITY: 0.5,
        }
        goal.value_score = source_values.get(goal.source, 0.5)
        
        # Urgency: based on priority
        priority_urgency = {
            GoalPriority.CRITICAL: 1.0,
            GoalPriority.HIGH: 0.8,
            GoalPriority.NORMAL: 0.5,
            GoalPriority.LOW: 0.2,
        }
        goal.urgency_score = priority_urgency.get(goal.priority, 0.5)
        
        # Overall score: weighted combination
        goal.overall_score = (
            goal.feasibility_score * 0.3 +
            goal.value_score * 0.4 +
            goal.urgency_score * 0.3
        )
        
        goal.evaluated_at = _now()
        goal.status = GoalStatus.EVALUATED
        
        # Update in database
        self.update_goal(goal)
        
        return goal
    
    def approve_goal(self, goal_id: str, auto_approve_threshold: float = 0.7) -> bool:
        """
        Approve a goal for execution.
        
        INVARIANT (P0): approving a *goal* only authorizes *goal selection* — it
        does NOT authorize the actions the goal will eventually take. Every action
        produced during execution still passes through ActionGate → PolicyEvaluator
        inside `CognitiveRuntime.process_cognitive_cycle()`:

            Goal approved  ≠  Actions approved

        Level 0/1/2 actions may run autonomously; Level 3 actions (delete, shell,
        messaging, trades, installs) still require explicit owner approval, and the
        autonomous executor records those steps as WAITING_APPROVAL — never COMPLETED
        — so a goal can't silently authorize a sensitive action by proxy.
        
        Args:
            goal_id: The goal ID to approve
            auto_approve_threshold: Minimum overall score for auto-approval
            
        Returns:
            True if approved, False otherwise
        """
        goal = self.get_goal(goal_id)
        if not goal:
            return False
        
        # Check ethical assessment first
        ethical_assessment = self.ethical_system.assess_goal(goal)
        
        # Reject if ethically problematic
        from app.cognition.ethical_reasoning import EthicalVerdict
        if ethical_assessment.verdict == EthicalVerdict.REJECTED:
            app_logger.warning(
                f"Goal rejected for ethical reasons: {goal.title} - {ethical_assessment.reasoning}"
            )
            goal.status = GoalStatus.REJECTED
            self.update_goal(goal)
            return False
        
        # Require human review for high-risk goals
        if ethical_assessment.verdict == EthicalVerdict.REQUIRES_REVIEW:
            app_logger.info(
                f"Goal requires human review: {goal.title} - {ethical_assessment.reasoning}"
            )
            # Don't auto-approve, leave as EVALUATED
            return False
        
        # Check overall score threshold
        if goal.overall_score >= auto_approve_threshold:
            # For conditional approval, log the conditions
            if ethical_assessment.verdict == EthicalVerdict.CONDITIONAL:
                app_logger.info(
                    f"Auto-approved goal with conditions: {goal.title} "
                    f"(score: {goal.overall_score:.2f}, conditions: {ethical_assessment.conditions})"
                )
            else:
                app_logger.info(f"Auto-approved goal for planning: {goal.title} (score: {goal.overall_score:.2f})")
            
            # P0 fix: record the approval BOUNDARY. Approving a goal authorizes
            # planning only — Level-3 actions still need owner approval at
            # execution time (ActionGate). This makes the separation explicit and
            # persistable rather than implicit.
            approval = self.build_goal_approval(goal)
            goal.max_action_level = approval.max_action_level
            goal.requires_owner_approval = approval.requires_owner_approval
            goal.status = GoalStatus.APPROVED
            goal.approved_at = _now()
            self.update_goal(goal)
            return True
        else:
            app_logger.info(f"Goal requires manual approval: {goal.title} (score: {goal.overall_score:.2f})")
            return False

    def build_goal_approval(self, goal: AutonomousGoal) -> GoalApproval:
        """Build the explicit approval boundary for a goal.

        The default `max_action_level` is 2: Level 0/1/2 actions may run
        autonomously during execution; any Level 3 action (delete, shell,
        messaging, trades, installs, system config) will surface for owner
        approval regardless of the goal's score. Subclasses/policies may lower
        this bound further; it never raises it above 2 automatically.
        """
        # The goal is approved for planning; execution of sensitive actions is
        # deferred to ActionGate at execution time.
        return GoalApproval(
            goal_id=goal.goal_id,
            planning_allowed=True,
            execution_allowed=False,
            max_action_level=2,
            requires_owner_approval=True,  # execution may hit Level-3 → owner approval
            policy_snapshot="Level 3 actions always require owner approval (ActionGate)",
        )
    
    def get_next_goal(self) -> Optional[AutonomousGoal]:
        """
        Get the highest-priority approved goal that's ready for execution.
        
        Returns:
            The next goal to execute, or None if no goals are ready
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM autonomous_goals
                WHERE status = ?
                ORDER BY overall_score DESC, created_at ASC
                LIMIT 1
            """, (GoalStatus.APPROVED.value,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_goal(row)
            return None
    
    def add_goal(self, goal: AutonomousGoal) -> bool:
        """Add a goal to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO autonomous_goals
                    (goal_id, title, description, source, motivation, priority, status,
                     target_state, current_state, success_criteria, estimated_effort,
                     dependencies, related_goals, feasibility_score, value_score,
                     urgency_score, overall_score, max_action_level, requires_owner_approval,
                     created_at, evaluated_at, approved_at, started_at, completed_at,
                     trigger_observation, user_benefit, system_benefit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    goal.goal_id,
                    goal.title,
                    goal.description,
                    goal.source.value,
                    goal.motivation.value,
                    goal.priority.value,
                    goal.status.value,
                    goal.target_state,
                    goal.current_state,
                    json.dumps(goal.success_criteria),
                    goal.estimated_effort,
                    json.dumps(goal.dependencies),
                    json.dumps(goal.related_goals),
                    goal.feasibility_score,
                    goal.value_score,
                    goal.urgency_score,
                    goal.overall_score,
                    goal.max_action_level,
                    1 if goal.requires_owner_approval else 0,
                    goal.created_at,
                    goal.evaluated_at,
                    goal.approved_at,
                    goal.started_at,
                    goal.completed_at,
                    goal.trigger_observation,
                    goal.user_benefit,
                    goal.system_benefit,
                ))
                conn.commit()
                return True
        except Exception as e:
            app_logger.error(f"Error adding goal: {e}")
            return False
    
    def update_goal(self, goal: AutonomousGoal) -> bool:
        """Update a goal in the database."""
        return self.add_goal(goal)  # INSERT OR REPLACE handles updates
    
    def get_goal(self, goal_id: str) -> Optional[AutonomousGoal]:
        """Get a goal by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM autonomous_goals WHERE goal_id = ?", (goal_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_goal(row)
            return None
    
    def list_goals(
        self,
        status: Optional[GoalStatus] = None,
        source: Optional[GoalSource] = None,
        limit: int = 50
    ) -> List[AutonomousGoal]:
        """List goals with optional filters."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM autonomous_goals WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            if source:
                query += " AND source = ?"
                params.append(source.value)
            
            query += " ORDER BY overall_score DESC, created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_goal(row) for row in cursor.fetchall()]
    
    def count_goals(self, status: Optional[GoalStatus] = None) -> int:
        """Count goals, optionally by status."""
        with sqlite3.connect(self.db_path) as conn:
            if status:
                cursor = conn.execute("SELECT COUNT(*) FROM autonomous_goals WHERE status = ?", (status.value,))
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM autonomous_goals")
            return cursor.fetchone()[0]
    
    def _row_to_goal(self, row) -> AutonomousGoal:
        """Convert a database row (sqlite3.Row, name-accessible) to an AutonomousGoal."""
        def _g(name, default=None):
            # sqlite3.Row supports both `row["name"]` and `row[index]`; guard
            # against missing columns for robustness across schema versions.
            try:
                return row[name]
            except (IndexError, KeyError):
                return default

        return AutonomousGoal(
            goal_id=_g("goal_id"),
            title=_g("title", ""),
            description=_g("description", ""),
            source=GoalSource(_g("source", "curiosity")),
            motivation=IntrinsicMotivation(_g("motivation", "curiosity")),
            priority=GoalPriority(_g("priority", "normal")),
            status=GoalStatus(_g("status", "proposed")),
            target_state=_g("target_state", ""),
            current_state=_g("current_state", ""),
            success_criteria=json.loads(_g("success_criteria") or "[]"),
            estimated_effort=_g("estimated_effort", "unknown"),
            dependencies=json.loads(_g("dependencies") or "[]"),
            related_goals=json.loads(_g("related_goals") or "[]"),
            feasibility_score=_g("feasibility_score", 0.0),
            value_score=_g("value_score", 0.0),
            urgency_score=_g("urgency_score", 0.0),
            overall_score=_g("overall_score", 0.0),
            max_action_level=_g("max_action_level", 2),
            requires_owner_approval=bool(_g("requires_owner_approval", False)),
            created_at=_g("created_at", _now()),
            evaluated_at=_g("evaluated_at"),
            approved_at=_g("approved_at"),
            started_at=_g("started_at"),
            completed_at=_g("completed_at"),
            trigger_observation=_g("trigger_observation"),
            user_benefit=_g("user_benefit"),
            system_benefit=_g("system_benefit"),
        )
