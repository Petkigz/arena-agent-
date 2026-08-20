"""
Phase 9: Self-Reflection Engine for Autonomous Goals

Analyzes autonomous goal execution outcomes to:
1. Identify patterns in successes and failures
2. Build a self-model of agent capabilities
3. Adjust goal generation strategy based on performance
4. Continuously improve autonomous behavior

This closes the learning loop: execute → reflect → improve.
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


class ReflectionType(str, Enum):
    """Types of self-reflection."""
    SUCCESS_ANALYSIS = "success_analysis"
    FAILURE_ANALYSIS = "failure_analysis"
    PATTERN_RECOGNITION = "pattern_recognition"
    CAPABILITY_ASSESSMENT = "capability_assessment"
    STRATEGY_ADJUSTMENT = "strategy_adjustment"


@dataclass
class ExecutionPattern:
    """A pattern discovered across multiple executions."""
    pattern_id: str = field(default_factory=lambda: f"pattern_{uuid4().hex[:8]}")
    goal_source: str = ""  # e.g., "system_optimization"
    success_rate: float = 0.0  # 0.0-1.0
    average_steps: int = 0
    average_confidence: float = 0.0
    common_failure_reasons: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    sample_size: int = 0
    discovered_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "goal_source": self.goal_source,
            "success_rate": self.success_rate,
            "average_steps": self.average_steps,
            "average_confidence": self.average_confidence,
            "common_failure_reasons": self.common_failure_reasons,
            "recommended_actions": self.recommended_actions,
            "sample_size": self.sample_size,
            "discovered_at": self.discovered_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionPattern':
        return cls(
            pattern_id=data.get("pattern_id", f"pattern_{uuid4().hex[:8]}"),
            goal_source=data.get("goal_source", ""),
            success_rate=data.get("success_rate", 0.0),
            average_steps=data.get("average_steps", 0),
            average_confidence=data.get("average_confidence", 0.0),
            common_failure_reasons=data.get("common_failure_reasons", []),
            recommended_actions=data.get("recommended_actions", []),
            sample_size=data.get("sample_size", 0),
            discovered_at=data.get("discovered_at", _now()),
        )


@dataclass
class SelfReflection:
    """A self-reflection insight."""
    reflection_id: str = field(default_factory=lambda: f"reflect_{uuid4().hex[:8]}")
    reflection_type: ReflectionType = ReflectionType.SUCCESS_ANALYSIS
    insight: str = ""
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    actionable: bool = False
    action_taken: Optional[str] = None
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "reflection_id": self.reflection_id,
            "reflection_type": self.reflection_type.value,
            "insight": self.insight,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "actionable": self.actionable,
            "action_taken": self.action_taken,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SelfReflection':
        return cls(
            reflection_id=data.get("reflection_id", f"reflect_{uuid4().hex[:8]}"),
            reflection_type=ReflectionType(data.get("reflection_type", "success_analysis")),
            insight=data.get("insight", ""),
            evidence=data.get("evidence", []),
            confidence=data.get("confidence", 0.0),
            actionable=data.get("actionable", False),
            action_taken=data.get("action_taken"),
            created_at=data.get("created_at", _now()),
        )


@dataclass
class SelfModel:
    """Agent's model of its own capabilities."""
    strong_areas: List[str] = field(default_factory=list)  # Goal sources with high success
    weak_areas: List[str] = field(default_factory=list)  # Goal sources with low success
    average_success_rate: float = 0.0
    total_goals_executed: int = 0
    total_goals_completed: int = 0
    total_goals_failed: int = 0
    preferred_goal_types: List[str] = field(default_factory=list)
    avoided_goal_types: List[str] = field(default_factory=list)
    last_updated: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strong_areas": self.strong_areas,
            "weak_areas": self.weak_areas,
            "average_success_rate": self.average_success_rate,
            "total_goals_executed": self.total_goals_executed,
            "total_goals_completed": self.total_goals_completed,
            "total_goals_failed": self.total_goals_failed,
            "preferred_goal_types": self.preferred_goal_types,
            "avoided_goal_types": self.avoided_goal_types,
            "last_updated": self.last_updated,
        }


class SelfReflectionEngine:
    """
    Analyzes autonomous goal execution to improve agent behavior over time.
    """
    
    def __init__(self, db_path: str = "data/self_reflection.db"):
        """Initialize the self-reflection engine."""
        self.db_path = db_path
        self._ensure_db()
        self.self_model = SelfModel()
        self._load_self_model()
        app_logger.info("Self-Reflection Engine initialized")
    
    def _ensure_db(self):
        """Ensure the database exists."""
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    goal_source TEXT NOT NULL,
                    success_rate REAL DEFAULT 0.0,
                    average_steps INTEGER DEFAULT 0,
                    average_confidence REAL DEFAULT 0.0,
                    common_failure_reasons TEXT,
                    recommended_actions TEXT,
                    sample_size INTEGER DEFAULT 0,
                    discovered_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS self_reflections (
                    reflection_id TEXT PRIMARY KEY,
                    reflection_type TEXT NOT NULL,
                    insight TEXT NOT NULL,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.0,
                    actionable INTEGER DEFAULT 0,
                    action_taken TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS self_model (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    strong_areas TEXT,
                    weak_areas TEXT,
                    average_success_rate REAL DEFAULT 0.0,
                    total_goals_executed INTEGER DEFAULT 0,
                    total_goals_completed INTEGER DEFAULT 0,
                    total_goals_failed INTEGER DEFAULT 0,
                    preferred_goal_types TEXT,
                    avoided_goal_types TEXT,
                    last_updated TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def _load_self_model(self):
        """Load the self-model from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM self_model WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                self.self_model.strong_areas = json.loads(row[1]) if row[1] else []
                self.self_model.weak_areas = json.loads(row[2]) if row[2] else []
                self.self_model.average_success_rate = row[3]
                self.self_model.total_goals_executed = row[4]
                self.self_model.total_goals_completed = row[5]
                self.self_model.total_goals_failed = row[6]
                self.self_model.preferred_goal_types = json.loads(row[7]) if row[7] else []
                self.self_model.avoided_goal_types = json.loads(row[8]) if row[8] else []
                self.self_model.last_updated = row[9]
    
    def _save_self_model(self):
        """Save the self-model to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO self_model
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                json.dumps(self.self_model.strong_areas),
                json.dumps(self.self_model.weak_areas),
                self.self_model.average_success_rate,
                self.self_model.total_goals_executed,
                self.self_model.total_goals_completed,
                self.self_model.total_goals_failed,
                json.dumps(self.self_model.preferred_goal_types),
                json.dumps(self.self_model.avoided_goal_types),
                _now(),
            ))
            conn.commit()
    
    def reflect_on_execution(self, plan, goal) -> List[SelfReflection]:
        """
        Reflect on a completed execution plan.
        
        Args:
            plan: The completed ExecutionPlan
            goal: The AutonomousGoal that was executed
            
        Returns:
            List of self-reflections generated
        """
        reflections = []
        
        # Update self-model statistics
        self.self_model.total_goals_executed += 1
        
        from app.cognition.autonomous_goal_executor import ExecutionStatus
        if plan.status == ExecutionStatus.COMPLETED:
            self.self_model.total_goals_completed += 1
        elif plan.status == ExecutionStatus.FAILED:
            self.self_model.total_goals_failed += 1
        
        # Recalculate average success rate
        if self.self_model.total_goals_executed > 0:
            self.self_model.average_success_rate = (
                self.self_model.total_goals_completed / self.self_model.total_goals_executed
            )
        
        # Analyze success or failure
        if plan.status == ExecutionStatus.COMPLETED:
            reflection = self._analyze_success(plan, goal)
            if reflection:
                reflections.append(reflection)
        elif plan.status == ExecutionStatus.FAILED:
            reflection = self._analyze_failure(plan, goal)
            if reflection:
                reflections.append(reflection)
        
        # Save reflections
        for reflection in reflections:
            self._save_reflection(reflection)
        
        # Update self-model
        self._update_self_model(goal, plan)
        self._save_self_model()
        
        app_logger.info(f"Generated {len(reflections)} self-reflection(s) for goal: {goal.title}")
        return reflections
    
    def _analyze_success(self, plan, goal) -> Optional[SelfReflection]:
        """Analyze a successful execution."""
        # Calculate average confidence across all steps
        avg_confidence = sum(s.confidence for s in plan.steps if s.confidence > 0) / len(plan.steps)
        
        # Generate insight
        if avg_confidence > 0.8:
            insight = f"High-confidence execution ({avg_confidence:.2f}) for {goal.source.value} goals"
            confidence = 0.9
        elif avg_confidence > 0.6:
            insight = f"Successful execution with moderate confidence ({avg_confidence:.2f})"
            confidence = 0.7
        else:
            insight = f"Completed but with low confidence ({avg_confidence:.2f}) - may need verification"
            confidence = 0.5
        
        evidence = [
            f"Status: {plan.status.value}",
            f"Steps completed: {len(plan.steps)}",
            f"Average confidence: {avg_confidence:.2f}",
            f"Outcome: {plan.outcome_summary}",
        ]
        
        return SelfReflection(
            reflection_type=ReflectionType.SUCCESS_ANALYSIS,
            insight=insight,
            evidence=evidence,
            confidence=confidence,
            actionable=avg_confidence < 0.7,  # Actionable if low confidence
            action_taken=None,
        )
    
    def _analyze_failure(self, plan, goal) -> Optional[SelfReflection]:
        """Analyze a failed execution."""
        # Identify failure reasons
        failed_steps = [s for s in plan.steps if s.error]
        failure_reasons = [s.error for s in failed_steps[:3]]  # Top 3 failures
        
        # Generate insight
        if len(failed_steps) == len(plan.steps):
            insight = f"Complete failure - all {len(plan.steps)} steps failed for {goal.source.value} goals"
            confidence = 0.9
        elif len(failed_steps) > len(plan.steps) / 2:
            insight = f"Majority failure - {len(failed_steps)}/{len(plan.steps)} steps failed"
            confidence = 0.8
        else:
            insight = f"Partial failure - {len(failed_steps)}/{len(plan.steps)} steps failed"
            confidence = 0.7
        
        evidence = [
            f"Status: {plan.status.value}",
            f"Failed steps: {len(failed_steps)}",
            f"Failure reasons: {failure_reasons}",
        ]
        
        return SelfReflection(
            reflection_type=ReflectionType.FAILURE_ANALYSIS,
            insight=insight,
            evidence=evidence,
            confidence=confidence,
            actionable=True,  # Failures are always actionable
            action_taken=None,
        )
    
    def _update_self_model(self, goal, plan):
        """Update the self-model based on execution outcome."""
        from app.cognition.autonomous_goal_executor import ExecutionStatus
        from app.cognition.autonomous_goal_generator import GoalSource
        
        goal_source = goal.source.value
        
        # Update strong/weak areas based on success rate
        # This is simplified - in practice, you'd track per-source success rates
        if plan.status == ExecutionStatus.COMPLETED:
            if goal_source not in self.self_model.strong_areas:
                # Add to strong areas if not already there
                if len(self.self_model.strong_areas) < 5:
                    self.self_model.strong_areas.append(goal_source)
            
            # Remove from weak areas if present
            if goal_source in self.self_model.weak_areas:
                self.self_model.weak_areas.remove(goal_source)
        
        elif plan.status == ExecutionStatus.FAILED:
            if goal_source not in self.self_model.weak_areas:
                # Add to weak areas if not already there
                if len(self.self_model.weak_areas) < 5:
                    self.self_model.weak_areas.append(goal_source)
            
            # Remove from strong areas if present
            if goal_source in self.self_model.strong_areas:
                self.self_model.strong_areas.remove(goal_source)
        
        self.self_model.last_updated = _now()
    
    def discover_patterns(self, plans: List) -> List[ExecutionPattern]:
        """
        Discover patterns across multiple execution plans.
        
        Args:
            plans: List of ExecutionPlan objects
            
        Returns:
            List of discovered patterns
        """
        from app.cognition.autonomous_goal_executor import ExecutionStatus
        
        # Group plans by goal source
        plans_by_source = {}
        for plan in plans:
            # Extract goal source from goal_title (simplified)
            source = "unknown"
            title_lower = plan.goal_title.lower().replace(" ", "_")
            for s in ["system_optimization", "information_gap", "maintenance", "user_pattern", "curiosity"]:
                if s in title_lower:
                    source = s
                    break
            
            if source not in plans_by_source:
                plans_by_source[source] = []
            plans_by_source[source].append(plan)
        
        # Analyze each group
        patterns = []
        for source, source_plans in plans_by_source.items():
            if len(source_plans) < 2:
                continue  # Need at least 2 samples
            
            pattern = self._analyze_pattern(source, source_plans)
            if pattern:
                patterns.append(pattern)
                self._save_pattern(pattern)
        
        app_logger.info(f"Discovered {len(patterns)} execution pattern(s)")
        return patterns
    
    def _analyze_pattern(self, source: str, plans: List) -> Optional[ExecutionPattern]:
        """Analyze a pattern for a specific goal source."""
        from app.cognition.autonomous_goal_executor import ExecutionStatus
        
        # Calculate statistics
        completed = [p for p in plans if p.status == ExecutionStatus.COMPLETED]
        failed = [p for p in plans if p.status == ExecutionStatus.FAILED]
        
        success_rate = len(completed) / len(plans) if plans else 0.0
        
        # Average steps
        avg_steps = sum(len(p.steps) for p in plans) / len(plans)
        
        # Average confidence
        all_confidences = []
        for plan in plans:
            for step in plan.steps:
                if step.confidence > 0:
                    all_confidences.append(step.confidence)
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        
        # Common failure reasons
        failure_reasons = []
        for plan in failed:
            for step in plan.steps:
                if step.error:
                    failure_reasons.append(step.error)
        
        # Get top 3 most common failure reasons
        from collections import Counter
        common_failures = [reason for reason, _ in Counter(failure_reasons).most_common(3)]
        
        # Generate recommendations
        recommendations = []
        if success_rate < 0.5:
            recommendations.append(f"Low success rate ({success_rate:.0%}) - consider avoiding {source} goals")
        if avg_confidence < 0.6:
            recommendations.append("Low confidence - add verification steps")
        if common_failures:
            recommendations.append(f"Address common failures: {common_failures[0]}")
        
        return ExecutionPattern(
            goal_source=source,
            success_rate=success_rate,
            average_steps=int(avg_steps),
            average_confidence=avg_confidence,
            common_failure_reasons=common_failures,
            recommended_actions=recommendations,
            sample_size=len(plans),
        )
    
    def get_recommendations(self) -> List[str]:
        """Get recommendations for improving autonomous behavior."""
        recommendations = []
        
        # Based on self-model
        if self.self_model.weak_areas:
            recommendations.append(
                f"Avoid or improve weak areas: {', '.join(self.self_model.weak_areas)}"
            )
        
        if self.self_model.average_success_rate < 0.6:
            recommendations.append(
                f"Low overall success rate ({self.self_model.average_success_rate:.0%}) - be more selective with goals"
            )
        
        # Based on patterns
        patterns = self.list_patterns()
        for pattern in patterns:
            if pattern.success_rate < 0.5:
                recommendations.append(
                    f"{pattern.goal_source}: {pattern.recommended_actions[0] if pattern.recommended_actions else 'Low success rate'}"
                )
        
        return recommendations
    
    def adjust_goal_generation(self, goal_generator):
        """
        Adjust goal generation parameters based on self-reflection.
        
        Args:
            goal_generator: AutonomousGoalGenerator instance
        """
        # Increase auto-approval threshold for weak areas
        weak_sources = [s for s in self.self_model.weak_areas]
        
        if weak_sources:
            app_logger.info(f"Adjusting goal generation: being more cautious with {weak_sources}")
            # In practice, you'd modify goal_generator's behavior here
            # For now, just log the adjustment
    
    def _save_reflection(self, reflection: SelfReflection):
        """Save a reflection to the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO self_reflections
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reflection.reflection_id,
                reflection.reflection_type.value,
                reflection.insight,
                json.dumps(reflection.evidence),
                reflection.confidence,
                1 if reflection.actionable else 0,
                reflection.action_taken,
                reflection.created_at,
            ))
            conn.commit()
    
    def _save_pattern(self, pattern: ExecutionPattern):
        """Save a pattern to the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO execution_patterns
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pattern.pattern_id,
                pattern.goal_source,
                pattern.success_rate,
                pattern.average_steps,
                pattern.average_confidence,
                json.dumps(pattern.common_failure_reasons),
                json.dumps(pattern.recommended_actions),
                pattern.sample_size,
                pattern.discovered_at,
            ))
            conn.commit()
    
    def list_reflections(
        self,
        reflection_type: Optional[ReflectionType] = None,
        limit: int = 50
    ) -> List[SelfReflection]:
        """List reflections with optional filter."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM self_reflections WHERE 1=1"
            params = []
            
            if reflection_type:
                query += " AND reflection_type = ?"
                params.append(reflection_type.value)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_reflection(row) for row in cursor.fetchall()]
    
    def list_patterns(self, limit: int = 50) -> List[ExecutionPattern]:
        """List execution patterns."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM execution_patterns ORDER BY discovered_at DESC LIMIT ?",
                (limit,)
            )
            return [self._row_to_pattern(row) for row in cursor.fetchall()]
    
    def get_self_model(self) -> SelfModel:
        """Get the current self-model."""
        return self.self_model
    
    def _row_to_reflection(self, row) -> SelfReflection:
        """Convert a database row to a SelfReflection."""
        return SelfReflection(
            reflection_id=row[0],
            reflection_type=ReflectionType(row[1]),
            insight=row[2],
            evidence=json.loads(row[3]) if row[3] else [],
            confidence=row[4],
            actionable=bool(row[5]),
            action_taken=row[6],
            created_at=row[7],
        )
    
    def _row_to_pattern(self, row) -> ExecutionPattern:
        """Convert a database row to an ExecutionPattern."""
        return ExecutionPattern(
            pattern_id=row[0],
            goal_source=row[1],
            success_rate=row[2],
            average_steps=row[3],
            average_confidence=row[4],
            common_failure_reasons=json.loads(row[5]) if row[5] else [],
            recommended_actions=json.loads(row[6]) if row[6] else [],
            sample_size=row[7],
            discovered_at=row[8],
        )
