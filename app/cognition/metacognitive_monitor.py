"""
Phase 18: Metacognitive Monitoring

Enables the Arena Agent to:
1. Monitor its own cognitive processes
2. Track reasoning strategies and their effectiveness
3. Detect cognitive biases and errors
4. Optimize cognitive load and resource allocation
5. Debug and improve its own thinking

This is a critical capability for human-level AGI - the ability to reflect on and improve one's own cognition.
"""

import sqlite3
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class CognitiveProcess(Enum):
    """Types of cognitive processes."""
    PERCEPTION = "perception"
    REASONING = "reasoning"
    PLANNING = "planning"
    DECISION_MAKING = "decision_making"
    LEARNING = "learning"
    MEMORY_RETRIEVAL = "memory_retrieval"
    PROBLEM_SOLVING = "problem_solving"
    CREATIVITY = "creativity"


class ReasoningStrategy(Enum):
    """Types of reasoning strategies."""
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"
    CAUSAL = "causal"
    PROBABILISTIC = "probabilistic"
    HEURISTIC = "heuristic"


class CognitiveBias(Enum):
    """Common cognitive biases."""
    CONFIRMATION_BIAS = "confirmation_bias"
    ANCHORING_BIAS = "anchoring_bias"
    AVAILABILITY_BIAS = "availability_bias"
    OVERCONFIDENCE = "overconfidence"
    SUNK_COST_FALLACY = "sunk_cost_fallacy"
    BANDWAGON_EFFECT = "bandwagon_effect"
    HALO_EFFECT = "halo_effect"
    DUNNING_KRUGER = "dunning_kruger"


class CognitiveLoad(Enum):
    """Cognitive load levels."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    OVERLOAD = "overload"


@dataclass
class CognitiveProcessRecord:
    """Record of a cognitive process execution."""
    record_id: str = field(default_factory=lambda: f"cog_{uuid.uuid4().hex[:8]}")
    process_type: CognitiveProcess = CognitiveProcess.REASONING
    strategy: ReasoningStrategy = ReasoningStrategy.DEDUCTIVE
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    confidence: float = 0.5
    cognitive_load: CognitiveLoad = CognitiveLoad.MODERATE
    biases_detected: List[CognitiveBias] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    success: bool = True
    lessons_learned: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'record_id': self.record_id,
            'process_type': self.process_type.value,
            'strategy': self.strategy.value,
            'input_data': self.input_data,
            'output_data': self.output_data,
            'execution_time_ms': self.execution_time_ms,
            'confidence': self.confidence,
            'cognitive_load': self.cognitive_load.value,
            'biases_detected': [b.value for b in self.biases_detected],
            'errors': self.errors,
            'success': self.success,
            'lessons_learned': self.lessons_learned,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CognitiveProcessRecord':
        """Create from dictionary."""
        return cls(
            record_id=data['record_id'],
            process_type=CognitiveProcess(data['process_type']),
            strategy=ReasoningStrategy(data['strategy']),
            input_data=data.get('input_data', {}),
            output_data=data.get('output_data', {}),
            execution_time_ms=data.get('execution_time_ms', 0.0),
            confidence=data.get('confidence', 0.5),
            cognitive_load=CognitiveLoad(data.get('cognitive_load', 'moderate')),
            biases_detected=[CognitiveBias(b) for b in data.get('biases_detected', [])],
            errors=data.get('errors', []),
            success=data.get('success', True),
            lessons_learned=data.get('lessons_learned', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class CognitiveProfile:
    """Profile of cognitive capabilities and patterns."""
    profile_id: str = field(default_factory=lambda: f"profile_{uuid.uuid4().hex[:8]}")
    process_type: CognitiveProcess = CognitiveProcess.REASONING
    strategy_preferences: Dict[str, float] = field(default_factory=dict)  # strategy -> preference score
    average_execution_time_ms: float = 0.0
    average_confidence: float = 0.5
    success_rate: float = 0.5
    common_biases: List[CognitiveBias] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    total_executions: int = 0
    last_updated: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'profile_id': self.profile_id,
            'process_type': self.process_type.value,
            'strategy_preferences': self.strategy_preferences,
            'average_execution_time_ms': self.average_execution_time_ms,
            'average_confidence': self.average_confidence,
            'success_rate': self.success_rate,
            'common_biases': [b.value for b in self.common_biases],
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'total_executions': self.total_executions,
            'last_updated': self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CognitiveProfile':
        """Create from dictionary."""
        return cls(
            profile_id=data['profile_id'],
            process_type=CognitiveProcess(data['process_type']),
            strategy_preferences=data.get('strategy_preferences', {}),
            average_execution_time_ms=data.get('average_execution_time_ms', 0.0),
            average_confidence=data.get('average_confidence', 0.5),
            success_rate=data.get('success_rate', 0.5),
            common_biases=[CognitiveBias(b) for b in data.get('common_biases', [])],
            strengths=data.get('strengths', []),
            weaknesses=data.get('weaknesses', []),
            total_executions=data.get('total_executions', 0),
            last_updated=data.get('last_updated', _now())
        )


@dataclass
class CognitiveOptimization:
    """Recommendation for cognitive optimization."""
    optimization_id: str = field(default_factory=lambda: f"opt_{uuid.uuid4().hex[:8]}")
    process_type: CognitiveProcess = CognitiveProcess.REASONING
    recommendation: str = ""
    rationale: str = ""
    expected_improvement: float = 0.0  # Expected improvement percentage
    priority: int = 1  # 1 (highest) to 5 (lowest)
    implemented: bool = False
    implemented_at: Optional[str] = None
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'optimization_id': self.optimization_id,
            'process_type': self.process_type.value,
            'recommendation': self.recommendation,
            'rationale': self.rationale,
            'expected_improvement': self.expected_improvement,
            'priority': self.priority,
            'implemented': self.implemented,
            'implemented_at': self.implemented_at,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CognitiveOptimization':
        """Create from dictionary."""
        return cls(
            optimization_id=data['optimization_id'],
            process_type=CognitiveProcess(data['process_type']),
            recommendation=data['recommendation'],
            rationale=data.get('rationale', ''),
            expected_improvement=data.get('expected_improvement', 0.0),
            priority=data.get('priority', 1),
            implemented=data.get('implemented', False),
            implemented_at=data.get('implemented_at'),
            created_at=data.get('created_at', _now())
        )


class MetacognitiveMonitor:
    """
    Monitor for metacognitive processes.
    
    Provides methods for:
    - Tracking cognitive process execution
    - Detecting cognitive biases
    - Analyzing reasoning patterns
    - Generating optimization recommendations
    - Managing cognitive load
    """
    
    def __init__(self, db_path: str = "data/metacognitive_monitor.db"):
        """Initialize the metacognitive monitor."""
        self.db_path = db_path
        self._ensure_db()
        self.current_load = CognitiveLoad.LOW
        self.active_processes = 0
        app_logger.info(f"Metacognitive Monitor initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_processes (
                    record_id TEXT PRIMARY KEY,
                    process_type TEXT NOT NULL,
                    process_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_profiles (
                    profile_id TEXT PRIMARY KEY,
                    process_type TEXT NOT NULL UNIQUE,
                    profile_data TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_optimizations (
                    optimization_id TEXT PRIMARY KEY,
                    process_type TEXT NOT NULL,
                    optimization_data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processes_type
                ON cognitive_processes(process_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processes_timestamp
                ON cognitive_processes(timestamp)
            """)
            
            conn.commit()
    
    def record_process(
        self,
        process_type: CognitiveProcess,
        strategy: ReasoningStrategy,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        execution_time_ms: float,
        confidence: float,
        success: bool,
        errors: List[str] = None
    ) -> CognitiveProcessRecord:
        """
        Record a cognitive process execution.
        
        Args:
            process_type: Type of cognitive process
            strategy: Reasoning strategy used
            input_data: Input to the process
            output_data: Output from the process
            execution_time_ms: Execution time in milliseconds
            confidence: Confidence in the result (0-1)
            success: Whether the process succeeded
            errors: List of errors encountered
        
        Returns:
            CognitiveProcessRecord object
        """
        errors = errors or []
        
        # Detect cognitive biases
        biases = self._detect_biases(process_type, strategy, input_data, output_data, confidence)
        
        # Determine cognitive load
        cognitive_load = self._assess_cognitive_load(execution_time_ms, len(errors))
        
        # Generate lessons learned
        lessons = self._generate_lessons(process_type, strategy, success, errors, biases)
        
        record = CognitiveProcessRecord(
            process_type=process_type,
            strategy=strategy,
            input_data=input_data,
            output_data=output_data,
            execution_time_ms=execution_time_ms,
            confidence=confidence,
            cognitive_load=cognitive_load,
            biases_detected=biases,
            errors=errors,
            success=success,
            lessons_learned=lessons
        )
        
        # Save record
        self._save_process_record(record)
        
        # Update cognitive profile
        self._update_profile(record)
        
        app_logger.info(
            f"Recorded {process_type.value} process: "
            f"strategy={strategy.value}, time={execution_time_ms:.1f}ms, "
            f"success={success}, biases={len(biases)}"
        )
        
        return record
    
    def _detect_biases(
        self,
        process_type: CognitiveProcess,
        strategy: ReasoningStrategy,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        confidence: float
    ) -> List[CognitiveBias]:
        """Detect cognitive biases in the process."""
        biases = []
        
        # Overconfidence detection
        if confidence > 0.9 and process_type == CognitiveProcess.DECISION_MAKING:
            biases.append(CognitiveBias.OVERCONFIDENCE)
        
        # Confirmation bias detection (simplified)
        if process_type == CognitiveProcess.REASONING:
            evidence = input_data.get('evidence', [])
            if isinstance(evidence, list) and len(evidence) > 0:
                # Check if all evidence supports the same conclusion
                supporting = sum(1 for e in evidence if e.get('supports', False))
                if supporting == len(evidence) and len(evidence) > 3:
                    biases.append(CognitiveBias.CONFIRMATION_BIAS)
        
        # Anchoring bias detection (simplified)
        if 'initial_estimate' in input_data and 'final_estimate' in output_data:
            initial = input_data.get('initial_estimate')
            final = output_data.get('final_estimate')
            if isinstance(initial, (int, float)) and isinstance(final, (int, float)):
                # If final estimate is very close to initial, might be anchoring
                if abs(final - initial) < abs(initial) * 0.1:
                    biases.append(CognitiveBias.ANCHORING_BIAS)
        
        return biases
    
    def _assess_cognitive_load(
        self,
        execution_time_ms: float,
        error_count: int
    ) -> CognitiveLoad:
        """Assess cognitive load based on execution characteristics."""
        # Simple heuristic based on execution time and errors
        if execution_time_ms > 5000 or error_count > 3:
            return CognitiveLoad.OVERLOAD
        elif execution_time_ms > 2000 or error_count > 1:
            return CognitiveLoad.HIGH
        elif execution_time_ms > 1000 or error_count > 0:
            return CognitiveLoad.MODERATE
        else:
            return CognitiveLoad.LOW
    
    def _generate_lessons(
        self,
        process_type: CognitiveProcess,
        strategy: ReasoningStrategy,
        success: bool,
        errors: List[str],
        biases: List[CognitiveBias]
    ) -> List[str]:
        """Generate lessons learned from the process."""
        lessons = []
        
        if not success:
            lessons.append(f"Process failed with {len(errors)} errors")
            if errors:
                lessons.append(f"Primary error: {errors[0]}")
        
        if biases:
            lessons.append(f"Detected {len(biases)} cognitive biases")
            for bias in biases[:2]:  # Mention top 2 biases
                lessons.append(f"Bias detected: {bias.value}")
        
        if success and not biases:
            lessons.append(f"{strategy.value} strategy worked well for {process_type.value}")
        
        return lessons
    
    def _update_profile(self, record: CognitiveProcessRecord) -> None:
        """Update cognitive profile based on process record."""
        profile = self.get_profile(record.process_type)
        
        if not profile:
            # Create new profile
            profile = CognitiveProfile(process_type=record.process_type)
        
        # Update statistics
        profile.total_executions += 1
        
        # Update average execution time
        profile.average_execution_time_ms = (
            (profile.average_execution_time_ms * (profile.total_executions - 1) + record.execution_time_ms)
            / profile.total_executions
        )
        
        # Update average confidence
        profile.average_confidence = (
            (profile.average_confidence * (profile.total_executions - 1) + record.confidence)
            / profile.total_executions
        )
        
        # Update success rate
        profile.success_rate = (
            (profile.success_rate * (profile.total_executions - 1) + (1.0 if record.success else 0.0))
            / profile.total_executions
        )
        
        # Update strategy preferences
        strategy_name = record.strategy.value
        if strategy_name not in profile.strategy_preferences:
            profile.strategy_preferences[strategy_name] = 0.0
        
        # Increase preference for successful strategies
        if record.success:
            profile.strategy_preferences[strategy_name] += 0.1
        else:
            profile.strategy_preferences[strategy_name] -= 0.1
        
        # Update common biases
        for bias in record.biases_detected:
            if bias not in profile.common_biases:
                profile.common_biases.append(bias)
        
        # Update strengths and weaknesses
        if record.success and record.confidence > 0.8:
            strength = f"{record.strategy.value} strategy for {record.process_type.value}"
            if strength not in profile.strengths:
                profile.strengths.append(strength)
        
        if not record.success:
            weakness = f"{record.strategy.value} strategy for {record.process_type.value}"
            if weakness not in profile.weaknesses:
                profile.weaknesses.append(weakness)
        
        profile.last_updated = _now()
        
        # Save profile
        self._save_profile(profile)
    
    def get_profile(self, process_type: CognitiveProcess) -> Optional[CognitiveProfile]:
        """Get cognitive profile for a process type."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT profile_data FROM cognitive_profiles WHERE process_type = ?",
                (process_type.value,)
            )
            row = cursor.fetchone()
            
            if row:
                profile_data = json.loads(row[0])
                return CognitiveProfile.from_dict(profile_data)
            
            return None
    
    def get_all_profiles(self) -> List[CognitiveProfile]:
        """Get all cognitive profiles."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT profile_data FROM cognitive_profiles ORDER BY process_type"
            )
            
            profiles = []
            for row in cursor.fetchall():
                profile_data = json.loads(row[0])
                profiles.append(CognitiveProfile.from_dict(profile_data))
            
            return profiles
    
    def get_process_history(
        self,
        process_type: Optional[CognitiveProcess] = None,
        limit: int = 100
    ) -> List[CognitiveProcessRecord]:
        """
        Get history of cognitive processes.
        
        Args:
            process_type: Filter by process type (optional)
            limit: Maximum number of records to return
        
        Returns:
            List of CognitiveProcessRecord objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT process_data FROM cognitive_processes"
            params = []
            
            if process_type:
                query += " WHERE process_type = ?"
                params.append(process_type.value)
            
            query += " ORDER BY timestamp DESC, rowid DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            records = []
            for row in cursor.fetchall():
                process_data = json.loads(row[0])
                records.append(CognitiveProcessRecord.from_dict(process_data))
            
            return records
    
    def analyze_patterns(
        self,
        process_type: CognitiveProcess,
        time_window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Analyze patterns in cognitive process execution.
        
        Args:
            process_type: Type of process to analyze
            time_window_hours: Time window to analyze (hours)
        
        Returns:
            Dictionary with pattern analysis
        """
        # Get recent processes
        cutoff_time = datetime.now(timezone.utc).timestamp() - (time_window_hours * 3600)
        records = self.get_process_history(process_type, limit=1000)
        
        # Filter by time window
        records = [
            r for r in records
            if datetime.fromisoformat(r.timestamp).timestamp() > cutoff_time
        ]
        
        if not records:
            return {
                "process_type": process_type.value,
                "total_executions": 0,
                "patterns": []
            }
        
        # Analyze patterns
        strategy_usage = {}
        bias_frequency = {}
        error_patterns = {}
        
        for record in records:
            # Strategy usage
            strategy_name = record.strategy.value
            strategy_usage[strategy_name] = strategy_usage.get(strategy_name, 0) + 1
            
            # Bias frequency
            for bias in record.biases_detected:
                bias_name = bias.value
                bias_frequency[bias_name] = bias_frequency.get(bias_name, 0) + 1
            
            # Error patterns
            for error in record.errors:
                error_patterns[error] = error_patterns.get(error, 0) + 1
        
        # Find most common strategy
        most_common_strategy = max(strategy_usage.items(), key=lambda x: x[1])[0] if strategy_usage else None
        
        # Find most common bias
        most_common_bias = max(bias_frequency.items(), key=lambda x: x[1])[0] if bias_frequency else None
        
        # Calculate success rate by strategy
        strategy_success = {}
        for record in records:
            strategy_name = record.strategy.value
            if strategy_name not in strategy_success:
                strategy_success[strategy_name] = {"success": 0, "total": 0}
            strategy_success[strategy_name]["total"] += 1
            if record.success:
                strategy_success[strategy_name]["success"] += 1
        
        strategy_success_rates = {
            strategy: data["success"] / data["total"]
            for strategy, data in strategy_success.items()
        }
        
        return {
            "process_type": process_type.value,
            "time_window_hours": time_window_hours,
            "total_executions": len(records),
            "strategy_usage": strategy_usage,
            "most_common_strategy": most_common_strategy,
            "bias_frequency": bias_frequency,
            "most_common_bias": most_common_bias,
            "error_patterns": error_patterns,
            "strategy_success_rates": strategy_success_rates
        }
    
    def generate_optimizations(self) -> List[CognitiveOptimization]:
        """
        Generate optimization recommendations based on cognitive profiles.
        
        Returns:
            List of CognitiveOptimization objects
        """
        optimizations = []
        profiles = self.get_all_profiles()
        
        for profile in profiles:
            # Check for low success rate
            if profile.success_rate < 0.6 and profile.total_executions > 10:
                optimizations.append(CognitiveOptimization(
                    process_type=profile.process_type,
                    recommendation=f"Improve {profile.process_type.value} success rate",
                    rationale=f"Current success rate is {profile.success_rate:.1%}, below 60% threshold",
                    expected_improvement=0.2,
                    priority=1
                ))
            
            # Check for common biases (trigger if 2 or more common biases)
            if len(profile.common_biases) >= 2:
                bias_names = [b.value for b in profile.common_biases[:3]]
                optimizations.append(CognitiveOptimization(
                    process_type=profile.process_type,
                    recommendation=f"Reduce cognitive biases in {profile.process_type.value}",
                    rationale=f"Common biases detected: {', '.join(bias_names)}",
                    expected_improvement=0.15,
                    priority=2
                ))
            
            # Check for slow execution
            if profile.average_execution_time_ms > 3000 and profile.total_executions > 10:
                optimizations.append(CognitiveOptimization(
                    process_type=profile.process_type,
                    recommendation=f"Optimize {profile.process_type.value} performance",
                    rationale=f"Average execution time is {profile.average_execution_time_ms:.0f}ms, above 3s threshold",
                    expected_improvement=0.3,
                    priority=2
                ))
            
            # Check for low confidence
            if profile.average_confidence < 0.5 and profile.total_executions > 10:
                optimizations.append(CognitiveOptimization(
                    process_type=profile.process_type,
                    recommendation=f"Improve confidence in {profile.process_type.value}",
                    rationale=f"Average confidence is {profile.average_confidence:.1%}, below 50% threshold",
                    expected_improvement=0.25,
                    priority=3
                ))
        
        # Sort by priority
        optimizations.sort(key=lambda o: o.priority)
        
        # Save optimizations
        for opt in optimizations:
            self._save_optimization(opt)
        
        app_logger.info(f"Generated {len(optimizations)} optimization recommendations")
        
        return optimizations
    
    def get_optimizations(
        self,
        process_type: Optional[CognitiveProcess] = None,
        implemented: Optional[bool] = None
    ) -> List[CognitiveOptimization]:
        """
        Get optimization recommendations.
        
        Args:
            process_type: Filter by process type (optional)
            implemented: Filter by implementation status (optional)
        
        Returns:
            List of CognitiveOptimization objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT optimization_data FROM cognitive_optimizations WHERE 1=1"
            params = []
            
            if process_type:
                query += " AND process_type = ?"
                params.append(process_type.value)
            
            if implemented is not None:
                query += " AND json_extract(optimization_data, '$.implemented') = ?"
                params.append(1 if implemented else 0)
            
            query += " ORDER BY json_extract(optimization_data, '$.priority') ASC"
            
            cursor = conn.execute(query, params)
            
            optimizations = []
            for row in cursor.fetchall():
                optimization_data = json.loads(row[0])
                optimizations.append(CognitiveOptimization.from_dict(optimization_data))
            
            return optimizations
    
    def mark_optimization_implemented(self, optimization_id: str) -> Optional[CognitiveOptimization]:
        """
        Mark an optimization as implemented.
        
        Args:
            optimization_id: ID of the optimization
        
        Returns:
            Updated CognitiveOptimization or None if not found
        """
        # Get optimization
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT optimization_data FROM cognitive_optimizations WHERE optimization_id = ?",
                (optimization_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            optimization_data = json.loads(row[0])
            optimization = CognitiveOptimization.from_dict(optimization_data)
            
            # Mark as implemented
            optimization.implemented = True
            optimization.implemented_at = _now()
            
            # Save
            self._save_optimization(optimization)
            
            app_logger.info(f"Marked optimization {optimization_id} as implemented")
            
            return optimization
    
    def get_cognitive_summary(self) -> Dict[str, Any]:
        """
        Get summary of cognitive performance.
        
        Returns:
            Dictionary with cognitive metrics
        """
        profiles = self.get_all_profiles()
        
        if not profiles:
            return {
                "total_processes": 0,
                "process_types": 0,
                "average_success_rate": 0.0,
                "average_confidence": 0.0,
                "total_biases_detected": 0,
                "optimizations_pending": 0
            }
        
        total_executions = sum(p.total_executions for p in profiles)
        avg_success_rate = sum(p.success_rate for p in profiles) / len(profiles)
        avg_confidence = sum(p.average_confidence for p in profiles) / len(profiles)
        total_biases = sum(len(p.common_biases) for p in profiles)
        
        # Get pending optimizations
        pending_optimizations = self.get_optimizations(implemented=False)
        
        return {
            "total_processes": total_executions,
            "process_types": len(profiles),
            "average_success_rate": avg_success_rate,
            "average_confidence": avg_confidence,
            "total_biases_detected": total_biases,
            "optimizations_pending": len(pending_optimizations),
            "profiles": {
                p.process_type.value: {
                    "executions": p.total_executions,
                    "success_rate": p.success_rate,
                    "avg_confidence": p.average_confidence,
                    "biases": len(p.common_biases)
                }
                for p in profiles
            }
        }
    
    def _save_process_record(self, record: CognitiveProcessRecord) -> None:
        """Save process record to database."""
        process_data = json.dumps(record.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO cognitive_processes
                (record_id, process_type, process_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                record.record_id,
                record.process_type.value,
                process_data,
                record.timestamp
            ))
            conn.commit()
    
    def _save_profile(self, profile: CognitiveProfile) -> None:
        """Save cognitive profile to database."""
        profile_data = json.dumps(profile.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cognitive_profiles
                (profile_id, process_type, profile_data, last_updated)
                VALUES (?, ?, ?, ?)
            """, (
                profile.profile_id,
                profile.process_type.value,
                profile_data,
                profile.last_updated
            ))
            conn.commit()
    
    def _save_optimization(self, optimization: CognitiveOptimization) -> None:
        """Save optimization to database."""
        optimization_data = json.dumps(optimization.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cognitive_optimizations
                (optimization_id, process_type, optimization_data, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                optimization.optimization_id,
                optimization.process_type.value,
                optimization_data,
                optimization.created_at
            ))
            conn.commit()
