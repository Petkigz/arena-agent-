"""
Phase 10: Periodic Autonomous Cycle

Runs autonomous goal generation and execution on a schedule:
1. Periodically observes the environment
2. Generates goals from observations
3. Executes approved goals
4. Reflects on outcomes
5. Improves over time

This makes the agent truly autonomous - it acts without user intervention.
"""

from __future__ import annotations

import sqlite3
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CycleStatus(str, Enum):
    """Status of an autonomous cycle."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ObservationSource(str, Enum):
    """Sources of environmental observations."""
    SYSTEM_HEALTH = "system_health"
    USER_BEHAVIOR = "user_behavior"
    PERFORMANCE_METRICS = "performance_metrics"
    KNOWLEDGE_GAPS = "knowledge_gaps"
    MAINTENANCE_NEEDS = "maintenance_needs"
    EXTERNAL_EVENTS = "external_events"


@dataclass
class AutonomousCycle:
    """A single autonomous cycle execution."""
    cycle_id: str = field(default_factory=lambda: f"cycle_{uuid4().hex[:8]}")
    status: CycleStatus = CycleStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    
    # Observations
    observations: List[str] = field(default_factory=list)
    observation_sources: List[str] = field(default_factory=list)
    
    # Goals
    goals_generated: int = 0
    goals_approved: int = 0
    goals_executed: int = 0
    goals_completed: int = 0
    goals_failed: int = 0
    
    # Reflections
    reflections_generated: int = 0
    patterns_discovered: int = 0
    
    # Outcomes
    summary: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "observations": self.observations,
            "observation_sources": self.observation_sources,
            "goals_generated": self.goals_generated,
            "goals_approved": self.goals_approved,
            "goals_executed": self.goals_executed,
            "goals_completed": self.goals_completed,
            "goals_failed": self.goals_failed,
            "reflections_generated": self.reflections_generated,
            "patterns_discovered": self.patterns_discovered,
            "summary": self.summary,
            "errors": self.errors,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AutonomousCycle':
        return cls(
            cycle_id=data.get("cycle_id", f"cycle_{uuid4().hex[:8]}"),
            status=CycleStatus(data.get("status", "pending")),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds", 0.0),
            observations=data.get("observations", []),
            observation_sources=data.get("observation_sources", []),
            goals_generated=data.get("goals_generated", 0),
            goals_approved=data.get("goals_approved", 0),
            goals_executed=data.get("goals_executed", 0),
            goals_completed=data.get("goals_completed", 0),
            goals_failed=data.get("goals_failed", 0),
            reflections_generated=data.get("reflections_generated", 0),
            patterns_discovered=data.get("patterns_discovered", 0),
            summary=data.get("summary"),
            errors=data.get("errors", []),
        )


class PeriodicAutonomousCycle:
    """
    Runs autonomous goal generation and execution on a schedule.
    """
    
    def __init__(
        self,
        goal_generator,
        goal_executor,
        reflection_engine,
        db_path: str = "data/autonomous_cycles.db",
        interval_seconds: int = 3600,  # Default: 1 hour
        max_goals_per_cycle: int = 3,
        autonomy_envelope=None,
    ):
        """
        Initialize the periodic autonomous cycle.
        
        Args:
            goal_generator: AutonomousGoalGenerator instance
            goal_executor: AutonomousGoalExecutor instance
            reflection_engine: SelfReflectionEngine instance
            db_path: Database path for cycle history
            interval_seconds: How often to run cycles (default: 1 hour)
            max_goals_per_cycle: Maximum goals to execute per cycle
        """
        self.goal_generator = goal_generator
        self.goal_executor = goal_executor
        self.reflection_engine = reflection_engine
        self.db_path = db_path
        self.interval_seconds = interval_seconds
        self.max_goals_per_cycle = max_goals_per_cycle
        self.autonomy_envelope = autonomy_envelope
        self._running = False
        
        self._ensure_db()
        app_logger.info(
            f"Periodic Autonomous Cycle initialized "
            f"(interval: {interval_seconds}s, max goals: {max_goals_per_cycle})"
        )
    
    def _ensure_db(self):
        """Ensure the database exists."""
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_cycles (
                    cycle_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_seconds REAL DEFAULT 0.0,
                    observations TEXT,
                    observation_sources TEXT,
                    goals_generated INTEGER DEFAULT 0,
                    goals_approved INTEGER DEFAULT 0,
                    goals_executed INTEGER DEFAULT 0,
                    goals_completed INTEGER DEFAULT 0,
                    goals_failed INTEGER DEFAULT 0,
                    reflections_generated INTEGER DEFAULT 0,
                    patterns_discovered INTEGER DEFAULT 0,
                    summary TEXT,
                    errors TEXT
                )
            """)
            conn.commit()
    
    def run_cycle(self, cognitive_runtime=None) -> AutonomousCycle:
        """
        Run a single autonomous cycle.
        
        Args:
            cognitive_runtime: Optional CognitiveRuntime for execution
            
        Returns:
            The completed AutonomousCycle
        """
        cycle = AutonomousCycle()
        cycle.status = CycleStatus.RUNNING
        cycle.started_at = _now()
        start_time = time.time()
        envelope_decision = {"cycle_allowed": True, "execution_allowed": True, "policy": {}}
        if self.autonomy_envelope is not None:
            from app.cognition.owner_control import owner_control_store
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT started_at FROM autonomous_cycles WHERE started_at IS NOT NULL "
                    "ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
            envelope_decision = self.autonomy_envelope.evaluate(
                owner_policy=owner_control_store.get_policy(),
                last_started_at=row[0] if row else None,
            )
            if not envelope_decision["cycle_allowed"]:
                cycle.status = CycleStatus.SKIPPED
                cycle.completed_at = _now()
                cycle.summary = "; ".join(envelope_decision["reasons"])
                self._save_cycle(cycle)
                return cycle
        envelope_policy = envelope_decision.get("policy", {})
        limits_enabled = bool(envelope_policy.get("limits_enabled", False))
        deadline = (
            start_time + int(envelope_policy.get("max_cycle_seconds", 300))
            if limits_enabled else float("inf")
        )
        execution_allowed = bool(envelope_decision["execution_allowed"])
        app_logger.info(f"Starting autonomous cycle {cycle.cycle_id}")
        
        try:
            # Step 1: Observe the environment
            observations = self._observe_environment(cognitive_runtime)
            cycle.observations = observations
            cycle.observation_sources = [ObservationSource.SYSTEM_HEALTH.value]  # Simplified
            
            app_logger.info(f"Cycle {cycle.cycle_id}: {len(observations)} observation(s)")
            
            # Step 2: Generate goals — evidence-driven (structured signals) first,
            # then information-gain curiosity, then keyword fallback. Thresholds
            # are calibrated from verified outcomes and bounded by owner budget.
            all_goals = []
            threshold_profile: Dict[str, Any] = {}
            if cognitive_runtime and hasattr(cognitive_runtime, "adaptive_autonomy"):
                try:
                    threshold_profile = cognitive_runtime.adaptive_autonomy.calibrate(
                        cognitive_runtime.outcomes
                    ).to_dict()
                except Exception as e:
                    app_logger.warning(f"Adaptive autonomy calibration failed: {e}")
            try:
                signals = self._observe_signals(cognitive_runtime, threshold_profile)
                signal_goals = self.goal_generator.generate_goals_from_signals(
                    signals, thresholds=threshold_profile
                )
                all_goals.extend(signal_goals)
                cycle.goals_generated += len(signal_goals)
            except Exception as e:
                app_logger.warning(f"Signal-driven goal generation failed (falling back): {e}")

            # P1-4 AGI: Information-gain curiosity — goals that maximize learning
            try:
                if cognitive_runtime:
                    budget = int(threshold_profile.get("exploration_budget", 3))
                    used = sum(
                        1 for goal in all_goals
                        if goal.source.value in ("curiosity", "information_gap")
                    )
                    info_thresholds = {
                        **threshold_profile,
                        "exploration_budget": max(0, budget - used),
                    }
                    info_goals = self.goal_generator.generate_goals_from_information_gain(
                        world_model=cognitive_runtime.world,
                        language_grounding=cognitive_runtime.language_grounding,
                        causal_engine=cognitive_runtime.causal_inference,
                        thresholds=info_thresholds,
                    )
                    all_goals.extend(info_goals)
                    cycle.goals_generated += len(info_goals)
            except Exception as e:
                app_logger.warning(f"Information-gain goal generation failed: {e}")

            # Free-text keyword generation is a true fallback, not an additional
            # unbounded curiosity channel.
            fallback_budget = int(threshold_profile.get("exploration_budget", 3))
            if not all_goals and fallback_budget > 0:
                for observation in observations[:fallback_budget]:
                    goals = self.goal_generator.generate_goals_from_observation(observation)
                    all_goals.extend(goals)
                    cycle.goals_generated += len(goals)
            
            app_logger.info(f"Cycle {cycle.cycle_id}: {cycle.goals_generated} goal(s) generated")
            
            # Step 3: Evaluate and approve goals using the calibrated threshold.
            approval_threshold = float(
                threshold_profile.get("goal_auto_approve_threshold", 0.7)
            )
            for goal in all_goals:
                self.goal_generator.evaluate_goal(goal)
                if execution_allowed and self.goal_generator.approve_goal(
                    goal.goal_id,
                    auto_approve_threshold=approval_threshold,
                ):
                    cycle.goals_approved += 1
            
            app_logger.info(f"Cycle {cycle.cycle_id}: {cycle.goals_approved} goal(s) approved")
            
            # Step 4: Execute approved goals (up to max_goals_per_cycle)
            executed_plans = []
            envelope_goal_cap = int(envelope_policy.get(
                "max_goal_executions_per_cycle", self.max_goals_per_cycle
            ))
            consecutive_failures = 0
            failure_cap = int(envelope_policy.get("max_consecutive_failures", 2)) if limits_enabled else 0
            execution_cap = (
                min(cycle.goals_approved, self.max_goals_per_cycle, envelope_goal_cap)
                if limits_enabled else cycle.goals_approved
            )
            for _ in range(execution_cap):
                if time.time() >= deadline or (failure_cap and consecutive_failures >= failure_cap):
                    cycle.errors.append("Autonomy execution budget reached")
                    break
                plan = self.goal_executor.execute_next_goal(self.goal_generator, cognitive_runtime)
                if plan:
                    cycle.goals_executed += 1
                    executed_plans.append(plan)
                    
                    from app.cognition.autonomous_goal_executor import ExecutionStatus
                    if plan.status == ExecutionStatus.COMPLETED:
                        cycle.goals_completed += 1
                        consecutive_failures = 0
                    elif plan.status == ExecutionStatus.FAILED:
                        cycle.goals_failed += 1
                        consecutive_failures += 1
            
            app_logger.info(
                f"Cycle {cycle.cycle_id}: {cycle.goals_executed} executed, "
                f"{cycle.goals_completed} completed, {cycle.goals_failed} failed"
            )

            # Step 4b: Resume owner-enabled persistent project DAGs. Each project
            # and step batch is bounded; exact actions still pass Owner Control,
            # ActionGate, observation, and verification.
            if execution_allowed and cognitive_runtime and hasattr(cognitive_runtime, "project_scheduler"):
                try:
                    project_cap = int(envelope_policy.get("max_projects_per_cycle", 3)) if limits_enabled else 100
                    step_cap = int(envelope_policy.get("max_project_steps_per_cycle", 3)) if limits_enabled else 1
                    project_cycle = (
                        cognitive_runtime.project_scheduler.run_cycle(
                            cognitive_runtime, max_projects=project_cap,
                            max_steps_per_project=1,
                        )
                        if project_cap > 0 and step_cap > 0
                        else {"projects_processed": 0, "reason": "owner envelope project budget is zero"}
                    )
                    app_logger.info(
                        f"Cycle {cycle.cycle_id}: project scheduler processed "
                        f"{project_cycle.get('projects_processed', 0)} project(s)"
                    )
                except Exception as e:
                    app_logger.warning(f"Cycle {cycle.cycle_id}: project scheduler skipped: {e}")
            
            # Step 5: Reflect on outcomes
            for plan in executed_plans:
                goal = self.goal_generator.get_goal(plan.goal_id)
                if goal:
                    reflections = self.reflection_engine.reflect_on_execution(plan, goal)
                    cycle.reflections_generated += len(reflections)
            
            app_logger.info(f"Cycle {cycle.cycle_id}: {cycle.reflections_generated} reflection(s)")
            
            # Step 6: Discover patterns (if enough data)
            if self.goal_executor.count_plans() >= 5:
                plans = self.goal_executor.list_plans(limit=20)
                patterns = self.reflection_engine.discover_patterns(plans)
                cycle.patterns_discovered = len(patterns)
                
                if patterns:
                    app_logger.info(f"Cycle {cycle.cycle_id}: {len(patterns)} pattern(s) discovered")
            
            # Step 7: Adjust goal generation based on reflections
            self.reflection_engine.adjust_goal_generation(self.goal_generator)
            
            # Step 8: Phase 4a — "sleep-like" memory consolidation (decay + prune + integrate).
            if cognitive_runtime and hasattr(cognitive_runtime, "consolidate_memory"):
                try:
                    consolidation = cognitive_runtime.consolidate_memory()
                    app_logger.info(
                        f"Cycle {cycle.cycle_id}: memory consolidation "
                        f"({consolidation.get('pruned_memories', 0)} pruned, "
                        f"{consolidation.get('consolidated', 0)} consolidated)"
                    )
                except Exception as e:
                    app_logger.warning(f"Cycle {cycle.cycle_id}: consolidation skipped: {e}")

            # Step 9: Phase 4b — proactive coworker maintenance (workspace index, self-heal).
            if cognitive_runtime and hasattr(cognitive_runtime, "run_proactive_maintenance"):
                try:
                    maintenance = cognitive_runtime.run_proactive_maintenance()
                    if maintenance.get("success"):
                        app_logger.info(f"Cycle {cycle.cycle_id}: proactive maintenance ran")
                except Exception as e:
                    app_logger.warning(f"Cycle {cycle.cycle_id}: maintenance skipped: {e}")

            # Generate summary
            cycle.summary = self._generate_summary(cycle)
            cycle.status = CycleStatus.COMPLETED
            
        except Exception as e:
            cycle.status = CycleStatus.FAILED
            cycle.errors.append(str(e))
            app_logger.error(f"Cycle {cycle.cycle_id} failed: {e}")
        
        finally:
            cycle.completed_at = _now()
            cycle.duration_seconds = time.time() - start_time
            
            # Save cycle
            self._save_cycle(cycle)
            
            app_logger.info(
                f"Cycle {cycle.cycle_id} completed in {cycle.duration_seconds:.1f}s: {cycle.summary}"
            )
        
        return cycle
    
    def _observe_environment(self, cognitive_runtime=None) -> List[str]:
        """
        Observe the environment and generate observations.

        Returns:
            List of observation strings
        """
        observations = []
        
        # System health observations
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage('/').percent
            
            if cpu_percent > 80:
                observations.append(f"System CPU usage is high: {cpu_percent}%")
            if memory_percent > 85:
                observations.append(f"System memory usage is high: {memory_percent}%")
            if disk_percent > 90:
                observations.append(f"Disk space is low: {100 - disk_percent}% free")
        except Exception as e:
            app_logger.warning(f"System health observation failed: {e}")
        
        # Knowledge gap observations
        if self.reflection_engine.self_model.weak_areas:
            weak = self.reflection_engine.self_model.weak_areas[0]
            observations.append(f"Information gap in {weak} - needs improvement")
        
        # Performance observations
        if self.reflection_engine.self_model.average_success_rate < 0.6:
            observations.append(
                f"Low success rate ({self.reflection_engine.self_model.average_success_rate:.0%}) "
                f"- investigate root cause"
            )
        
        # Maintenance observations
        cycle_count = self.count_cycles()
        if cycle_count > 0 and cycle_count % 10 == 0:
            observations.append("Periodic maintenance check - review system health")
        
        # Default observation if none generated
        if not observations:
            observations.append("System operating normally - explore optimization opportunities")
        
        return observations
    
    def _observe_signals(
        self,
        cognitive_runtime=None,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Observe the environment as STRUCTURED signals (not flattened strings), so
        goal generation can use the evidence-driven path (generate_goals_from_signals)
        instead of keyword matching. Reads the same sources as _observe_environment
        but returns raw values keyed by signal name.

        P1-4 AGI: Now also emits information-gain signals (unknown entities,
        low-confidence groundings, weak causal edges, unexplored files) so the
        agent generates curiosity-driven goals that maximize learning.
        """
        signals: Dict[str, Any] = {}
        threshold_values = thresholds or {}
        entity_threshold = float(threshold_values.get("unknown_entity_confidence", 0.5))
        grounding_threshold = float(threshold_values.get("grounding_confidence", 0.6))
        causal_threshold = float(threshold_values.get("weak_causal_confidence", 0.4))
        try:
            import psutil
            signals["resource_pressure"] = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "ram_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
            }
        except Exception as e:
            app_logger.warning(f"Signal observation (psutil) failed: {e}")

        try:
            signals["low_success_rate"] = self.reflection_engine.self_model.average_success_rate
            if self.reflection_engine.self_model.weak_areas:
                signals["stale_beliefs"] = list(self.reflection_engine.self_model.weak_areas[:3])
        except Exception as e:
            app_logger.warning(f"Signal observation (self-model) failed: {e}")

        # P1-4: Information gain signals
        if cognitive_runtime:
            # Unknown / low-confidence entities from WorldModel
            try:
                entities = cognitive_runtime.world.find_entities()[:50]
                unknown = [
                    ent.name for ent in entities
                    if ent.confidence < entity_threshold
                ]
                if unknown:
                    signals["unknown_entities"] = unknown[:5]
            except Exception as e:
                app_logger.warning(f"Signal observation (unknown entities) failed: {e}")

            # Low confidence groundings from LanguageGrounding
            try:
                lg_summary = cognitive_runtime.language_grounding.get_grounding_summary()
                if lg_summary.get("total_perceptual_groundings", 0) < 10:
                    signals["low_grounding_count"] = lg_summary.get("total_perceptual_groundings", 0)
                if lg_summary.get("average_perceptual_confidence", 1.0) < grounding_threshold:
                    # Get low confidence symbols
                    groundings = cognitive_runtime.language_grounding.get_perceptual_groundings(limit=20)
                    low_conf = [
                        g.symbol for g in groundings
                        if g.confidence < grounding_threshold
                    ]
                    if low_conf:
                        signals["low_confidence_groundings"] = low_conf[:3]
            except Exception as e:
                app_logger.warning(f"Signal observation (groundings) failed: {e}")

            # Weak causal edges
            try:
                weak = []
                for edge in cognitive_runtime.causal_inference.graph.edges.values():
                    if edge.confidence < causal_threshold:
                        src = cognitive_runtime.causal_inference.graph.nodes.get(edge.source_id)
                        tgt = cognitive_runtime.causal_inference.graph.nodes.get(edge.target_id)
                        if src and tgt:
                            weak.append(f"{src.name} → {tgt.name}")
                if weak:
                    signals["weak_causal_edges"] = weak[:3]
            except Exception as e:
                app_logger.warning(f"Signal observation (weak causal) failed: {e}")

            # Unexplored files (recent files in workspace not yet indexed)
            try:
                from pathlib import Path
                from app.config import settings
                workspace = settings.DATA_DIR / "workspace"
                if workspace.exists():
                    # Find files modified in last 24h not yet in memory
                    recent = []
                    for p in workspace.rglob("*"):
                        if p.is_file():
                            try:
                                if (time.time() - p.stat().st_mtime) < 86400:
                                    recent.append(str(p.name))
                            except Exception:
                                continue
                    if recent:
                        signals["unexplored_files"] = recent[:5]
            except Exception as e:
                app_logger.warning(f"Signal observation (unexplored files) failed: {e}")

        return signals
    
    def _generate_summary(self, cycle: AutonomousCycle) -> str:
        """Generate a human-readable summary of the cycle."""
        parts = []
        
        if cycle.goals_generated > 0:
            parts.append(f"{cycle.goals_generated} goal(s) generated")
        
        if cycle.goals_executed > 0:
            parts.append(f"{cycle.goals_executed} executed")
            parts.append(f"{cycle.goals_completed} completed")
            if cycle.goals_failed > 0:
                parts.append(f"{cycle.goals_failed} failed")
        
        if cycle.reflections_generated > 0:
            parts.append(f"{cycle.reflections_generated} reflection(s)")
        
        if cycle.patterns_discovered > 0:
            parts.append(f"{cycle.patterns_discovered} pattern(s)")
        
        return ", ".join(parts) if parts else "No activity"
    
    def _save_cycle(self, cycle: AutonomousCycle):
        """Save a cycle to the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO autonomous_cycles
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cycle.cycle_id,
                cycle.status.value,
                cycle.started_at,
                cycle.completed_at,
                cycle.duration_seconds,
                json.dumps(cycle.observations),
                json.dumps(cycle.observation_sources),
                cycle.goals_generated,
                cycle.goals_approved,
                cycle.goals_executed,
                cycle.goals_completed,
                cycle.goals_failed,
                cycle.reflections_generated,
                cycle.patterns_discovered,
                cycle.summary,
                json.dumps(cycle.errors),
            ))
            conn.commit()
    
    def get_cycle(self, cycle_id: str) -> Optional[AutonomousCycle]:
        """Get a cycle by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM autonomous_cycles WHERE cycle_id = ?", (cycle_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_cycle(row)
            return None
    
    def list_cycles(
        self,
        status: Optional[CycleStatus] = None,
        limit: int = 50
    ) -> List[AutonomousCycle]:
        """List cycles with optional status filter."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM autonomous_cycles WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_cycle(row) for row in cursor.fetchall()]
    
    def count_cycles(self, status: Optional[CycleStatus] = None) -> int:
        """Count cycles, optionally by status."""
        with sqlite3.connect(self.db_path) as conn:
            if status:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM autonomous_cycles WHERE status = ?",
                    (status.value,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM autonomous_cycles")
            return cursor.fetchone()[0]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics across all cycles."""
        cycles = self.list_cycles(limit=1000)
        
        if not cycles:
            return {
                "total_cycles": 0,
                "average_duration": 0.0,
                "total_goals_generated": 0,
                "total_goals_executed": 0,
                "total_goals_completed": 0,
                "total_goals_failed": 0,
                "overall_success_rate": 0.0,
            }
        
        total_duration = sum(c.duration_seconds for c in cycles)
        total_generated = sum(c.goals_generated for c in cycles)
        total_executed = sum(c.goals_executed for c in cycles)
        total_completed = sum(c.goals_completed for c in cycles)
        total_failed = sum(c.goals_failed for c in cycles)
        
        success_rate = total_completed / total_executed if total_executed > 0 else 0.0
        
        return {
            "total_cycles": len(cycles),
            "average_duration": total_duration / len(cycles),
            "total_goals_generated": total_generated,
            "total_goals_executed": total_executed,
            "total_goals_completed": total_completed,
            "total_goals_failed": total_failed,
            "overall_success_rate": success_rate,
        }
    
    def _row_to_cycle(self, row) -> AutonomousCycle:
        """Convert a database row to an AutonomousCycle."""
        return AutonomousCycle(
            cycle_id=row[0],
            status=CycleStatus(row[1]),
            started_at=row[2],
            completed_at=row[3],
            duration_seconds=row[4],
            observations=json.loads(row[5]) if row[5] else [],
            observation_sources=json.loads(row[6]) if row[6] else [],
            goals_generated=row[7],
            goals_approved=row[8],
            goals_executed=row[9],
            goals_completed=row[10],
            goals_failed=row[11],
            reflections_generated=row[12],
            patterns_discovered=row[13],
            summary=row[14],
            errors=json.loads(row[15]) if row[15] else [],
        )
