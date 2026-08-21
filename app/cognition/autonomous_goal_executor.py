"""
Phase 8: Autonomous Goal Execution

Executes approved autonomous goals by:
1. Breaking goals into executable subtasks
2. Executing tasks through the cognitive pipeline
3. Tracking progress and updating goal status
4. Reporting results and learning from outcomes

This closes the AGI loop: observe → generate goal → execute → learn.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionStatus(str, Enum):
    """Goal execution status.

    Tri-state semantics (mirrors the evidence invariant — execution success is
    NOT the same as goal achievement):

    - COMPLETED        — the cognitive cycle's GoalVerifier confirmed the goal.
    - FAILED           — verification definitively failed, or the action was blocked.
    - UNVERIFIED       — the cycle ran but the environment was not verified (UNKNOWN).
    - WAITING_APPROVAL — the action requires owner approval (Level 3 gate); NOT done.
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Types of executable tasks."""
    INFORMATION_GATHERING = "information_gathering"
    ANALYSIS = "analysis"
    OPTIMIZATION = "optimization"
    MAINTENANCE = "maintenance"
    EXPLORATION = "exploration"
    USER_ASSISTANCE = "user_assistance"


@dataclass
class ExecutionStep:
    """A single step in goal execution."""
    step_id: str = field(default_factory=lambda: f"step_{uuid4().hex[:8]}")
    goal_id: str = ""
    description: str = ""
    task_type: TaskType = TaskType.ANALYSIS
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "goal_id": self.goal_id,
            "description": self.description,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionStep':
        return cls(
            step_id=data.get("step_id", f"step_{uuid4().hex[:8]}"),
            goal_id=data.get("goal_id", ""),
            description=data.get("description", ""),
            task_type=TaskType(data.get("task_type", "analysis")),
            status=ExecutionStatus(data.get("status", "pending")),
            result=data.get("result"),
            error=data.get("error"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class ExecutionPlan:
    """A plan for executing a goal."""
    plan_id: str = field(default_factory=lambda: f"plan_{uuid4().hex[:8]}")
    goal_id: str = ""
    goal_title: str = ""
    steps: List[ExecutionStep] = field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.PENDING
    progress: float = 0.0  # 0.0-1.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    outcome_summary: Optional[str] = None
    lessons_learned: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "goal_title": self.goal_title,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "progress": self.progress,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "outcome_summary": self.outcome_summary,
            "lessons_learned": self.lessons_learned,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionPlan':
        return cls(
            plan_id=data.get("plan_id", f"plan_{uuid4().hex[:8]}"),
            goal_id=data.get("goal_id", ""),
            goal_title=data.get("goal_title", ""),
            steps=[ExecutionStep.from_dict(s) for s in data.get("steps", [])],
            status=ExecutionStatus(data.get("status", "pending")),
            progress=data.get("progress", 0.0),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            outcome_summary=data.get("outcome_summary"),
            lessons_learned=data.get("lessons_learned", []),
        )


class AutonomousGoalExecutor:
    """
    Executes autonomous goals by breaking them into steps and running them
    through the cognitive pipeline.
    """
    
    def __init__(self, db_path: str = "data/goal_execution.db"):
        """Initialize the goal executor."""
        self.db_path = db_path
        self._ensure_db()
        app_logger.info("Autonomous Goal Executor initialized")
    
    def _ensure_db(self):
        """Ensure the database exists."""
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_plans (
                    plan_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    goal_title TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL DEFAULT 0.0,
                    started_at TEXT,
                    completed_at TEXT,
                    outcome_summary TEXT,
                    lessons_learned TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_goal_id ON execution_plans(goal_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON execution_plans(status)")
            conn.commit()
    
    def create_execution_plan(self, goal) -> ExecutionPlan:
        """
        Create an execution plan for a goal.
        
        Args:
            goal: An AutonomousGoal object
            
        Returns:
            An ExecutionPlan with steps to achieve the goal
        """
        plan = ExecutionPlan(
            goal_id=goal.goal_id,
            goal_title=goal.title,
        )
        
        # Generate steps based on goal source and type
        steps = self._generate_steps_for_goal(goal)
        plan.steps = steps
        
        # Save the plan
        self.save_plan(plan)
        
        app_logger.info(f"Created execution plan for goal: {goal.title} ({len(steps)} steps)")
        return plan
    
    def _generate_steps_for_goal(self, goal) -> List[ExecutionStep]:
        """Generate execution steps based on goal type."""
        from app.cognition.autonomous_goal_generator import GoalSource
        
        steps = []
        
        # Common first step: Analyze the current state
        steps.append(ExecutionStep(
            goal_id=goal.goal_id,
            description=f"Analyze current state: {goal.current_state}",
            task_type=TaskType.ANALYSIS,
        ))
        
        # Goal-specific steps
        if goal.source == GoalSource.INFORMATION_GAP:
            steps.extend([
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Gather information from available sources",
                    task_type=TaskType.INFORMATION_GATHERING,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Verify and validate gathered information",
                    task_type=TaskType.ANALYSIS,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Integrate new knowledge into belief system",
                    task_type=TaskType.ANALYSIS,
                ),
            ])
        
        elif goal.source == GoalSource.SYSTEM_OPTIMIZATION:
            steps.extend([
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Identify root cause of performance issue",
                    task_type=TaskType.ANALYSIS,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Design optimization strategy",
                    task_type=TaskType.OPTIMIZATION,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Implement optimization",
                    task_type=TaskType.OPTIMIZATION,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Verify performance improvement",
                    task_type=TaskType.ANALYSIS,
                ),
            ])
        
        elif goal.source == GoalSource.MAINTENANCE:
            steps.extend([
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Identify items requiring maintenance",
                    task_type=TaskType.ANALYSIS,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Perform maintenance actions",
                    task_type=TaskType.MAINTENANCE,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Verify maintenance completed successfully",
                    task_type=TaskType.ANALYSIS,
                ),
            ])
        
        elif goal.source == GoalSource.USER_PATTERN:
            steps.extend([
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Analyze user behavior pattern",
                    task_type=TaskType.ANALYSIS,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Design user experience improvement",
                    task_type=TaskType.OPTIMIZATION,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Implement improvement",
                    task_type=TaskType.USER_ASSISTANCE,
                ),
            ])
        
        elif goal.source == GoalSource.CURIOSITY:
            steps.extend([
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Research and explore the topic",
                    task_type=TaskType.EXPLORATION,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Document findings",
                    task_type=TaskType.ANALYSIS,
                ),
            ])
        
        else:
            # Generic steps for other goal types
            steps.extend([
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Plan approach to achieve goal",
                    task_type=TaskType.ANALYSIS,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Execute plan",
                    task_type=TaskType.ANALYSIS,
                ),
                ExecutionStep(
                    goal_id=goal.goal_id,
                    description="Verify goal achievement",
                    task_type=TaskType.ANALYSIS,
                ),
            ])
        
        # Common last step: Verify success criteria
        steps.append(ExecutionStep(
            goal_id=goal.goal_id,
            description=f"Verify success criteria: {', '.join(goal.success_criteria[:2])}",
            task_type=TaskType.ANALYSIS,
        ))
        
        return steps
    
    def execute_step(self, step: ExecutionStep, cognitive_runtime=None) -> ExecutionStep:
        """
        Execute a single step.
        
        Args:
            step: The step to execute
            cognitive_runtime: Optional CognitiveRuntime instance for execution
            
        Returns:
            The updated step with results
        """
        step.status = ExecutionStatus.IN_PROGRESS
        step.started_at = _now()
        
        try:
            # Use cognitive pipeline to execute the step
            if cognitive_runtime:
                result = cognitive_runtime.process_cognitive_cycle(
                    user_text=step.description,
                    complexity="deep" if step.task_type == TaskType.ANALYSIS else "fast"
                )
                step.result = result.get("assistant_reply", "Completed")
                # P0 fix: the cycle's GoalVerifier verdict is authoritative, NOT
                # "the cycle returned a reply". A step is COMPLETED only when the
                # environment was actually verified to reach the goal.
                verified = result.get("goal_verified")
                requires_approval = bool(result.get("requires_approval"))
                gate_blocked = result.get("gate_blocked")
                lifecycle = result.get("goal_lifecycle_state", "")

                if requires_approval or gate_blocked:
                    # Level-3 action: the owner must approve. Never "completed".
                    step.status = ExecutionStatus.WAITING_APPROVAL
                    step.confidence = 0.0
                    step.error = (
                        f"Action requires owner approval"
                        + (f" ({gate_blocked})" if gate_blocked else "")
                    )
                elif verified is True:
                    step.status = ExecutionStatus.COMPLETED
                    step.confidence = 1.0
                elif verified is False and lifecycle in ("failed", "blocked", "deferred"):
                    step.status = ExecutionStatus.FAILED
                    step.confidence = 0.0
                    step.error = step.result or "Goal verification failed"
                else:
                    # verified False/None but not provably failed → UNKNOWN.
                    step.status = ExecutionStatus.UNVERIFIED
                    step.confidence = 0.5
                    step.error = "Goal could not be verified (no environmental evidence)"
            else:
                # No runtime: execution is simulated, so nothing can be verified.
                step.result = f"Simulated execution: {step.description}"
                step.status = ExecutionStatus.UNVERIFIED
                step.confidence = 0.0
            
            step.completed_at = _now()
            
            app_logger.info(
                f"Step {step.status.value}: {step.description[:50]} (confidence: {step.confidence:.2f})"
            )
            
        except Exception as e:
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            step.completed_at = _now()
            app_logger.error(f"Step failed: {step.description[:50]} - {e}")
        
        return step
    
    def execute_plan(self, plan: ExecutionPlan, cognitive_runtime=None) -> ExecutionPlan:
        """
        Execute an entire plan step by step.
        
        Args:
            plan: The plan to execute
            cognitive_runtime: Optional CognitiveRuntime instance
            
        Returns:
            The updated plan with results
        """
        plan.status = ExecutionStatus.IN_PROGRESS
        plan.started_at = _now()
        
        for step in plan.steps:
            if step.status == ExecutionStatus.PENDING:
                self.execute_step(step, cognitive_runtime)
            # Update progress as steps are processed (any terminal status counts).
            done = sum(
                1 for s in plan.steps
                if s.status not in (ExecutionStatus.PENDING, ExecutionStatus.IN_PROGRESS)
            )
            plan.progress = done / len(plan.steps)
            self.save_plan(plan)
        
        # Determine final status from the tri-state tally. A plan is COMPLETED
        # only when EVERY step was verified (never on unverified/awaiting steps).
        completed = sum(1 for s in plan.steps if s.status == ExecutionStatus.COMPLETED)
        failed = sum(1 for s in plan.steps if s.status == ExecutionStatus.FAILED)
        unverified = sum(1 for s in plan.steps if s.status == ExecutionStatus.UNVERIFIED)
        waiting = sum(1 for s in plan.steps if s.status == ExecutionStatus.WAITING_APPROVAL)
        
        if completed == len(plan.steps):
            plan.status = ExecutionStatus.COMPLETED
            plan.outcome_summary = f"All {completed} steps verified complete"
        elif waiting > 0:
            plan.status = ExecutionStatus.WAITING_APPROVAL
            plan.outcome_summary = f"{waiting} step(s) awaiting owner approval"
        elif failed > 0 and completed == 0:
            plan.status = ExecutionStatus.FAILED
            plan.outcome_summary = f"{failed} steps failed out of {len(plan.steps)}"
        else:
            plan.status = ExecutionStatus.PARTIAL
            plan.outcome_summary = (
                f"{completed} verified, {failed} failed, {unverified} unverified, {waiting} awaiting approval"
            )
        
        plan.completed_at = _now()
        
        # Extract lessons learned
        plan.lessons_learned = self._extract_lessons(plan)
        
        self.save_plan(plan)
        
        app_logger.info(f"Plan {plan.status.value}: {plan.goal_title} - {plan.outcome_summary}")
        return plan
    
    def _extract_lessons(self, plan: ExecutionPlan) -> List[str]:
        """Extract lessons learned from plan execution."""
        lessons = []
        
        # Analyze failed steps
        failed_steps = [s for s in plan.steps if s.status == ExecutionStatus.FAILED]
        if failed_steps:
            lessons.append(f"Failed steps indicate need for better planning: {[s.description[:30] for s in failed_steps[:2]]}")
        
        # Analyze unverified steps (goal couldn't be confirmed in the environment)
        unverified_steps = [s for s in plan.steps if s.status == ExecutionStatus.UNVERIFIED]
        if unverified_steps:
            lessons.append(
                f"{len(unverified_steps)} step(s) could not be verified against the "
                "environment — needs a concrete postcondition probe"
            )
        
        # Analyze steps waiting on owner approval (Level-3 gate)
        waiting_steps = [s for s in plan.steps if s.status == ExecutionStatus.WAITING_APPROVAL]
        if waiting_steps:
            lessons.append(
                f"{len(waiting_steps)} step(s) required owner approval and were not auto-completed"
            )
        
        # Analyze low-confidence steps
        low_conf_steps = [s for s in plan.steps if s.confidence < 0.6 and s.status == ExecutionStatus.COMPLETED]
        if low_conf_steps:
            lessons.append("Low confidence in some results suggests need for verification")
        
        # Analyze execution time
        if plan.started_at and plan.completed_at:
            lessons.append("Execution completed - track timing for future optimization")
        
        return lessons
    
    def execute_next_goal(self, goal_generator, cognitive_runtime=None) -> Optional[ExecutionPlan]:
        """
        Execute the next approved goal.
        
        Args:
            goal_generator: AutonomousGoalGenerator instance
            cognitive_runtime: Optional CognitiveRuntime instance
            
        Returns:
            The execution plan, or None if no goals are ready
        """
        # Get next approved goal
        goal = goal_generator.get_next_goal()
        if not goal:
            app_logger.info("No approved goals ready for execution")
            return None
        
        # Update goal status to in_progress
        from app.cognition.autonomous_goal_generator import GoalStatus
        goal.status = GoalStatus.IN_PROGRESS
        goal.started_at = _now()
        goal_generator.update_goal(goal)
        
        # Create and execute plan
        plan = self.create_execution_plan(goal)
        plan = self.execute_plan(plan, cognitive_runtime)
        
        # Update goal status based on plan outcome
        if plan.status == ExecutionStatus.COMPLETED:
            goal.status = GoalStatus.COMPLETED
            goal.completed_at = _now()
        elif plan.status == ExecutionStatus.FAILED:
            goal.status = GoalStatus.FAILED
        else:
            goal.status = GoalStatus.DEFERRED
        
        goal_generator.update_goal(goal)
        
        return plan
    
    def save_plan(self, plan: ExecutionPlan) -> bool:
        """Save an execution plan to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO execution_plans
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    plan.plan_id,
                    plan.goal_id,
                    plan.goal_title,
                    json.dumps([s.to_dict() for s in plan.steps]),
                    plan.status.value,
                    plan.progress,
                    plan.started_at,
                    plan.completed_at,
                    plan.outcome_summary,
                    json.dumps(plan.lessons_learned),
                ))
                conn.commit()
                return True
        except Exception as e:
            app_logger.error(f"Error saving plan: {e}")
            return False
    
    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get an execution plan by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM execution_plans WHERE plan_id = ?", (plan_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_plan(row)
            return None
    
    def get_plan_by_goal(self, goal_id: str) -> Optional[ExecutionPlan]:
        """Get an execution plan by goal ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM execution_plans WHERE goal_id = ?", (goal_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_plan(row)
            return None
    
    def list_plans(
        self,
        status: Optional[ExecutionStatus] = None,
        limit: int = 50
    ) -> List[ExecutionPlan]:
        """List execution plans with optional status filter."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM execution_plans WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_plan(row) for row in cursor.fetchall()]
    
    def count_plans(self, status: Optional[ExecutionStatus] = None) -> int:
        """Count execution plans, optionally by status."""
        with sqlite3.connect(self.db_path) as conn:
            if status:
                cursor = conn.execute("SELECT COUNT(*) FROM execution_plans WHERE status = ?", (status.value,))
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM execution_plans")
            return cursor.fetchone()[0]
    
    def _row_to_plan(self, row) -> ExecutionPlan:
        """Convert a database row to an ExecutionPlan."""
        return ExecutionPlan(
            plan_id=row[0],
            goal_id=row[1],
            goal_title=row[2],
            steps=[ExecutionStep.from_dict(s) for s in json.loads(row[3])],
            status=ExecutionStatus(row[4]),
            progress=row[5],
            started_at=row[6],
            completed_at=row[7],
            outcome_summary=row[8],
            lessons_learned=json.loads(row[9]) if row[9] else [],
        )
