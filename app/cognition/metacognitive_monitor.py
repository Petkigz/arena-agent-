"""
Phase 18: Metacognitive Monitoring

Enables the agent to:
1. Monitor its own cognitive processes
2. Detect reasoning errors and inefficiencies
3. Optimize cognitive strategies
4. Learn from cognitive failures
5. Adapt reasoning approaches based on self-awareness

This is a critical capability for human-level AGI - the ability to think about thinking.
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
import json
import sqlite3
import uuid


class CognitiveProcessType(Enum):
    """Types of cognitive processes that can be monitored."""
    REASONING = "reasoning"
    PLANNING = "planning"
    LEARNING = "learning"
    MEMORY_RETRIEVAL = "memory_retrieval"
    DECISION_MAKING = "decision_making"
    PROBLEM_SOLVING = "problem_solving"
    CREATIVITY = "creativity"
    SOCIAL_COGNITION = "social_cognition"


class CognitiveState(Enum):
    """States of cognitive processes."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STUCK = "stuck"
    INEFFICIENT = "inefficient"
    OPTIMAL = "optimal"


class ErrorType(Enum):
    """Types of cognitive errors."""
    LOGICAL_FALLACY = "logical_fallacy"
    BIAS = "bias"
    INCONSISTENCY = "inconsistency"
    OVERGENERALIZATION = "overgeneralization"
    UNDERGENERALIZATION = "undergeneralization"
    PREMATURE_CONCLUSION = "premature_conclusion"
    CIRCULAR_REASONING = "circular_reasoning"
    MISSING_EVIDENCE = "missing_evidence"


class OptimizationStrategy(Enum):
    """Strategies for optimizing cognitive processes."""
    SIMPLIFY = "simplify"  # Reduce complexity
    DECOMPOSE = "decompose"  # Break into smaller parts
    PARALLELIZE = "parallelize"  # Run multiple processes concurrently
    CACHE = "cache"  # Store intermediate results
    PRUNE = "prune"  # Remove unnecessary branches
    REFOCUS = "refocus"  # Change attention/focus
    STRATEGY_SWITCH = "strategy_switch"  # Try different approach


@dataclass
class CognitiveProcess:
    """Represents a cognitive process being monitored."""
    process_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    process_type: CognitiveProcessType = CognitiveProcessType.REASONING
    description: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    state: CognitiveState = CognitiveState.RUNNING
    steps_completed: int = 0
    total_steps: Optional[int] = None
    errors_detected: List[ErrorType] = field(default_factory=list)
    confidence_level: float = 0.5
    resource_usage: Dict[str, float] = field(default_factory=dict)
    intermediate_results: List[Any] = field(default_factory=list)
    optimization_suggestions: List[OptimizationStrategy] = field(default_factory=list)
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate process duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    @property
    def progress(self) -> Optional[float]:
        """Calculate progress percentage."""
        if self.total_steps and self.total_steps > 0:
            return self.steps_completed / self.total_steps
        return None
    
    @property
    def efficiency_score(self) -> float:
        """Calculate efficiency score (0-1)."""
        score = 1.0
        
        # Penalize for errors
        score -= len(self.errors_detected) * 0.1
        
        # Penalize for low confidence
        score -= (1.0 - self.confidence_level) * 0.2
        
        # Penalize for long duration (if we have a baseline)
        if self.duration and self.duration > 10.0:  # More than 10 seconds
            score -= min(0.3, (self.duration - 10.0) / 100.0)
        
        # Reward for progress
        if self.progress:
            score += self.progress * 0.2
        
        return max(0.0, min(1.0, score))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "process_id": self.process_id,
            "process_type": self.process_type.value,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "state": self.state.value,
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
            "errors_detected": [e.value for e in self.errors_detected],
            "confidence_level": self.confidence_level,
            "resource_usage": self.resource_usage,
            "optimization_suggestions": [s.value for s in self.optimization_suggestions],
            "duration": self.duration,
            "progress": self.progress,
            "efficiency_score": self.efficiency_score
        }


@dataclass
class CognitiveInsight:
    """An insight about cognitive processes."""
    insight_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    process_type: CognitiveProcessType = CognitiveProcessType.REASONING
    insight_type: str = ""  # e.g., "pattern", "error", "optimization"
    description: str = ""
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.5
    actionable: bool = False
    recommended_actions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "insight_id": self.insight_id,
            "timestamp": self.timestamp,
            "process_type": self.process_type.value,
            "insight_type": self.insight_type,
            "description": self.description,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "actionable": self.actionable,
            "recommended_actions": self.recommended_actions
        }


@dataclass
class CognitiveStrategy:
    """A strategy for approaching cognitive tasks."""
    strategy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    applicable_to: List[CognitiveProcessType] = field(default_factory=list)
    success_rate: float = 0.5
    average_efficiency: float = 0.5
    times_used: int = 0
    last_used: Optional[float] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "applicable_to": [p.value for p in self.applicable_to],
            "success_rate": self.success_rate,
            "average_efficiency": self.average_efficiency,
            "times_used": self.times_used,
            "last_used": self.last_used,
            "parameters": self.parameters
        }


class MetacognitiveMonitor:
    """
    Monitors and optimizes cognitive processes.
    
    Provides methods for:
    - Tracking cognitive processes
    - Detecting errors and inefficiencies
    - Generating insights about cognition
    - Recommending optimization strategies
    - Learning from cognitive performance
    """
    
    def __init__(self, db_path: str = "metacognitive_monitor.db"):
        """Initialize the metacognitive monitor."""
        self.db_path = db_path
        self.processes: Dict[str, CognitiveProcess] = {}
        self.insights: List[CognitiveInsight] = []
        self.strategies: Dict[str, CognitiveStrategy] = {}
        self._init_database()
        self._load_default_strategies()
    
    def _init_database(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create processes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cognitive_processes (
                process_id TEXT PRIMARY KEY,
                process_type TEXT NOT NULL,
                description TEXT,
                start_time REAL NOT NULL,
                end_time REAL,
                state TEXT NOT NULL,
                steps_completed INTEGER DEFAULT 0,
                total_steps INTEGER,
                errors_detected TEXT,
                confidence_level REAL DEFAULT 0.5,
                resource_usage TEXT,
                optimization_suggestions TEXT
            )
        """)
        
        # Create insights table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cognitive_insights (
                insight_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                process_type TEXT NOT NULL,
                insight_type TEXT NOT NULL,
                description TEXT,
                evidence TEXT,
                confidence REAL DEFAULT 0.5,
                actionable BOOLEAN DEFAULT FALSE,
                recommended_actions TEXT
            )
        """)
        
        # Create strategies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cognitive_strategies (
                strategy_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                applicable_to TEXT,
                success_rate REAL DEFAULT 0.5,
                average_efficiency REAL DEFAULT 0.5,
                times_used INTEGER DEFAULT 0,
                last_used REAL,
                parameters TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _load_default_strategies(self):
        """Load default cognitive strategies."""
        default_strategies = [
            CognitiveStrategy(
                name="Divide and Conquer",
                description="Break complex problems into smaller, manageable subproblems",
                applicable_to=[
                    CognitiveProcessType.PROBLEM_SOLVING,
                    CognitiveProcessType.PLANNING
                ],
                success_rate=0.7,
                average_efficiency=0.7
            ),
            CognitiveStrategy(
                name="Working Backwards",
                description="Start from the desired outcome and work backwards to current state",
                applicable_to=[
                    CognitiveProcessType.PLANNING,
                    CognitiveProcessType.PROBLEM_SOLVING
                ],
                success_rate=0.6,
                average_efficiency=0.65
            ),
            CognitiveStrategy(
                name="Analogical Reasoning",
                description="Use similar past problems to inform current problem",
                applicable_to=[
                    CognitiveProcessType.REASONING,
                    CognitiveProcessType.PROBLEM_SOLVING,
                    CognitiveProcessType.CREATIVITY
                ],
                success_rate=0.65,
                average_efficiency=0.7
            ),
            CognitiveStrategy(
                name="Iterative Refinement",
                description="Start with a rough solution and iteratively improve it",
                applicable_to=[
                    CognitiveProcessType.CREATIVITY,
                    CognitiveProcessType.PROBLEM_SOLVING,
                    CognitiveProcessType.LEARNING
                ],
                success_rate=0.75,
                average_efficiency=0.7
            ),
            CognitiveStrategy(
                name="Evidence-Based Reasoning",
                description="Base conclusions on available evidence and update as new evidence arrives",
                applicable_to=[
                    CognitiveProcessType.REASONING,
                    CognitiveProcessType.DECISION_MAKING
                ],
                success_rate=0.8,
                average_efficiency=0.75
            ),
        ]
        
        for strategy in default_strategies:
            self.strategies[strategy.strategy_id] = strategy
    
    def start_process(
        self,
        process_type: CognitiveProcessType,
        description: str,
        total_steps: Optional[int] = None
    ) -> str:
        """
        Start monitoring a cognitive process.
        
        Args:
            process_type: Type of cognitive process
            description: Description of the process
            total_steps: Expected number of steps (optional)
        
        Returns:
            Process ID
        """
        process = CognitiveProcess(
            process_type=process_type,
            description=description,
            total_steps=total_steps
        )
        
        self.processes[process.process_id] = process
        return process.process_id
    
    def update_process(
        self,
        process_id: str,
        steps_completed: Optional[int] = None,
        confidence_level: Optional[float] = None,
        resource_usage: Optional[Dict[str, float]] = None,
        intermediate_result: Optional[Any] = None
    ) -> None:
        """
        Update a cognitive process.
        
        Args:
            process_id: Process ID
            steps_completed: Number of steps completed
            confidence_level: Current confidence level (0-1)
            resource_usage: Resource usage metrics
            intermediate_result: Intermediate result to store
        """
        if process_id not in self.processes:
            return
        
        process = self.processes[process_id]
        
        if steps_completed is not None:
            process.steps_completed = steps_completed
        
        if confidence_level is not None:
            process.confidence_level = confidence_level
        
        if resource_usage is not None:
            process.resource_usage.update(resource_usage)
        
        if intermediate_result is not None:
            process.intermediate_results.append(intermediate_result)
    
    def complete_process(
        self,
        process_id: str,
        state: CognitiveState = CognitiveState.COMPLETED
    ) -> None:
        """
        Mark a cognitive process as complete.
        
        Args:
            process_id: Process ID
            state: Final state of the process
        """
        if process_id not in self.processes:
            return
        
        process = self.processes[process_id]
        process.end_time = time.time()
        process.state = state
        
        # Generate insights about the process
        self._analyze_process(process)
        
        # Save to database
        self._save_process(process)
    
    def detect_error(
        self,
        process_id: str,
        error_type: ErrorType,
        description: str
    ) -> None:
        """
        Record a cognitive error.
        
        Args:
            process_id: Process ID
            error_type: Type of error
            description: Description of the error
        """
        if process_id not in self.processes:
            return
        
        process = self.processes[process_id]
        process.errors_detected.append(error_type)
        
        # Generate insight about the error
        insight = CognitiveInsight(
            process_type=process.process_type,
            insight_type="error",
            description=f"Detected {error_type.value}: {description}",
            evidence=[description],
            confidence=0.8,
            actionable=True,
            recommended_actions=self._get_error_recommendations(error_type)
        )
        
        self.insights.append(insight)
        self._save_insight(insight)
    
    def suggest_optimization(
        self,
        process_id: str,
        strategy: OptimizationStrategy,
        reason: str
    ) -> None:
        """
        Suggest an optimization for a process.
        
        Args:
            process_id: Process ID
            strategy: Optimization strategy
            reason: Reason for the suggestion
        """
        if process_id not in self.processes:
            return
        
        process = self.processes[process_id]
        process.optimization_suggestions.append(strategy)
        
        # Generate insight
        insight = CognitiveInsight(
            process_type=process.process_type,
            insight_type="optimization",
            description=f"Suggested optimization: {strategy.value}. {reason}",
            evidence=[reason],
            confidence=0.7,
            actionable=True,
            recommended_actions=[f"Apply {strategy.value} strategy"]
        )
        
        self.insights.append(insight)
        self._save_insight(insight)
    
    def get_process(self, process_id: str) -> Optional[CognitiveProcess]:
        """Get a cognitive process by ID."""
        return self.processes.get(process_id)
    
    def get_active_processes(self) -> List[CognitiveProcess]:
        """Get all active (running) processes."""
        return [p for p in self.processes.values() if p.state == CognitiveState.RUNNING]
    
    def get_process_history(
        self,
        process_type: Optional[CognitiveProcessType] = None,
        limit: int = 10
    ) -> List[CognitiveProcess]:
        """
        Get history of cognitive processes.
        
        Args:
            process_type: Filter by process type (optional)
            limit: Maximum number of processes to return
        
        Returns:
            List of processes (most recent first)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM cognitive_processes"
        params = []
        
        if process_type:
            query += " WHERE process_type = ?"
            params.append(process_type.value)
        
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        processes = []
        for row in rows:
            process = CognitiveProcess(
                process_id=row[0],
                process_type=CognitiveProcessType(row[1]),
                description=row[2],
                start_time=row[3],
                end_time=row[4],
                state=CognitiveState(row[5]),
                steps_completed=row[6],
                total_steps=row[7],
                errors_detected=[ErrorType(e) for e in json.loads(row[8]) if row[8]],
                confidence_level=row[9],
                resource_usage=json.loads(row[10]) if row[10] else {},
                optimization_suggestions=[
                    OptimizationStrategy(s) for s in json.loads(row[11]) if row[11]
                ]
            )
            processes.append(process)
        
        return processes
    
    def get_insights(
        self,
        process_type: Optional[CognitiveProcessType] = None,
        insight_type: Optional[str] = None,
        limit: int = 20
    ) -> List[CognitiveInsight]:
        """
        Get cognitive insights.
        
        Args:
            process_type: Filter by process type (optional)
            insight_type: Filter by insight type (optional)
            limit: Maximum number of insights to return
        
        Returns:
            List of insights (most recent first)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM cognitive_insights"
        params = []
        conditions = []
        
        if process_type:
            conditions.append("process_type = ?")
            params.append(process_type.value)
        
        if insight_type:
            conditions.append("insight_type = ?")
            params.append(insight_type)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        insights = []
        for row in rows:
            insight = CognitiveInsight(
                insight_id=row[0],
                timestamp=row[1],
                process_type=CognitiveProcessType(row[2]),
                insight_type=row[3],
                description=row[4],
                evidence=json.loads(row[5]) if row[5] else [],
                confidence=row[6],
                actionable=bool(row[7]),
                recommended_actions=json.loads(row[8]) if row[8] else []
            )
            insights.append(insight)
        
        return insights
    
    def recommend_strategy(
        self,
        process_type: CognitiveProcessType,
        context: Dict[str, Any]
    ) -> Optional[CognitiveStrategy]:
        """
        Recommend a cognitive strategy for a given process type and context.
        
        Args:
            process_type: Type of cognitive process
            context: Context information
        
        Returns:
            Recommended strategy or None
        """
        applicable_strategies = [
            s for s in self.strategies.values()
            if process_type in s.applicable_to
        ]
        
        if not applicable_strategies:
            return None
        
        # Sort by success rate and efficiency
        applicable_strategies.sort(
            key=lambda s: (s.success_rate * 0.6 + s.average_efficiency * 0.4),
            reverse=True
        )
        
        return applicable_strategies[0]
    
    def record_strategy_use(
        self,
        strategy_id: str,
        success: bool,
        efficiency: float
    ) -> None:
        """
        Record the use of a cognitive strategy.
        
        Args:
            strategy_id: Strategy ID
            success: Whether the strategy was successful
            efficiency: Efficiency score (0-1)
        """
        if strategy_id not in self.strategies:
            return
        
        strategy = self.strategies[strategy_id]
        
        # Update statistics
        strategy.times_used += 1
        strategy.last_used = time.time()
        
        # Update success rate (exponential moving average)
        alpha = 0.1
        strategy.success_rate = (
            (1 - alpha) * strategy.success_rate + alpha * (1.0 if success else 0.0)
        )
        
        # Update average efficiency (exponential moving average)
        strategy.average_efficiency = (
            (1 - alpha) * strategy.average_efficiency + alpha * efficiency
        )
    
    def get_cognitive_profile(self) -> Dict[str, Any]:
        """
        Get a profile of cognitive performance.
        
        Returns:
            Dictionary with cognitive performance metrics
        """
        all_processes = list(self.processes.values())
        
        if not all_processes:
            return {
                "total_processes": 0,
                "average_efficiency": 0.0,
                "error_rate": 0.0,
                "average_confidence": 0.0,
                "most_common_errors": [],
                "best_strategies": []
            }
        
        # Calculate metrics
        total_processes = len(all_processes)
        avg_efficiency = sum(p.efficiency_score for p in all_processes) / total_processes
        avg_confidence = sum(p.confidence_level for p in all_processes) / total_processes
        
        # Count errors
        error_counts = {}
        for process in all_processes:
            for error in process.errors_detected:
                error_counts[error.value] = error_counts.get(error.value, 0) + 1
        
        total_errors = sum(error_counts.values())
        error_rate = total_errors / total_processes if total_processes > 0 else 0.0
        
        # Most common errors
        most_common_errors = sorted(
            error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # Best strategies
        best_strategies = sorted(
            self.strategies.values(),
            key=lambda s: (s.success_rate * 0.6 + s.average_efficiency * 0.4),
            reverse=True
        )[:5]
        
        return {
            "total_processes": total_processes,
            "average_efficiency": avg_efficiency,
            "error_rate": error_rate,
            "average_confidence": avg_confidence,
            "most_common_errors": most_common_errors,
            "best_strategies": [s.name for s in best_strategies]
        }
    
    def _analyze_process(self, process: CognitiveProcess) -> None:
        """Analyze a completed process and generate insights."""
        # Check for inefficiency
        if process.efficiency_score < 0.5:
            insight = CognitiveInsight(
                process_type=process.process_type,
                insight_type="inefficiency",
                description=f"Process was inefficient (score: {process.efficiency_score:.2f})",
                evidence=[
                    f"Duration: {process.duration:.2f}s",
                    f"Errors: {len(process.errors_detected)}",
                    f"Confidence: {process.confidence_level:.2f}"
                ],
                confidence=0.8,
                actionable=True,
                recommended_actions=[
                    "Consider breaking problem into smaller parts",
                    "Review for logical errors",
                    "Try alternative strategies"
                ]
            )
            self.insights.append(insight)
            self._save_insight(insight)
        
        # Check for patterns in errors
        if len(process.errors_detected) >= 3:
            insight = CognitiveInsight(
                process_type=process.process_type,
                insight_type="error_pattern",
                description=f"Multiple errors detected ({len(process.errors_detected)})",
                evidence=[e.value for e in process.errors_detected],
                confidence=0.9,
                actionable=True,
                recommended_actions=[
                    "Review reasoning process",
                    "Check for systematic biases",
                    "Consider using evidence-based reasoning"
                ]
            )
            self.insights.append(insight)
            self._save_insight(insight)
        
        # Check for low confidence
        if process.confidence_level < 0.4:
            insight = CognitiveInsight(
                process_type=process.process_type,
                insight_type="low_confidence",
                description=f"Low confidence in results ({process.confidence_level:.2f})",
                evidence=[
                    f"Final confidence: {process.confidence_level:.2f}"
                ],
                confidence=0.7,
                actionable=True,
                recommended_actions=[
                    "Gather more evidence",
                    "Verify conclusions",
                    "Consider alternative explanations"
                ]
            )
            self.insights.append(insight)
            self._save_insight(insight)
    
    def _get_error_recommendations(self, error_type: ErrorType) -> List[str]:
        """Get recommendations for addressing an error type."""
        recommendations = {
            ErrorType.LOGICAL_FALLACY: [
                "Review logical structure",
                "Check for hidden assumptions",
                "Verify each step follows from previous"
            ],
            ErrorType.BIAS: [
                "Consider alternative perspectives",
                "Check for confirmation bias",
                "Seek contradictory evidence"
            ],
            ErrorType.INCONSISTENCY: [
                "Review for contradictions",
                "Check assumptions",
                "Verify all statements are compatible"
            ],
            ErrorType.OVERGENERALIZATION: [
                "Check sample size",
                "Look for counterexamples",
                "Narrow the scope of conclusions"
            ],
            ErrorType.UNDERGENERALIZATION: [
                "Look for broader patterns",
                "Consider if conclusions apply more widely",
                "Check for missed connections"
            ],
            ErrorType.PREMATURE_CONCLUSION: [
                "Gather more evidence",
                "Consider alternative explanations",
                "Delay judgment until more information available"
            ],
            ErrorType.CIRCULAR_REASONING: [
                "Check if conclusion is used as premise",
                "Find independent evidence",
                "Restructure argument"
            ],
            ErrorType.MISSING_EVIDENCE: [
                "Identify what evidence is needed",
                "Gather additional data",
                "Acknowledge uncertainty"
            ]
        }
        
        return recommendations.get(error_type, ["Review reasoning process"])
    
    def _save_process(self, process: CognitiveProcess) -> None:
        """Save a process to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO cognitive_processes VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            process.process_id,
            process.process_type.value,
            process.description,
            process.start_time,
            process.end_time,
            process.state.value,
            process.steps_completed,
            process.total_steps,
            json.dumps([e.value for e in process.errors_detected]),
            process.confidence_level,
            json.dumps(process.resource_usage),
            json.dumps([s.value for s in process.optimization_suggestions])
        ))
        
        conn.commit()
        conn.close()
    
    def _save_insight(self, insight: CognitiveInsight) -> None:
        """Save an insight to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO cognitive_insights VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            insight.insight_id,
            insight.timestamp,
            insight.process_type.value,
            insight.insight_type,
            insight.description,
            json.dumps(insight.evidence),
            insight.confidence,
            1 if insight.actionable else 0,
            json.dumps(insight.recommended_actions)
        ))
        
        conn.commit()
        conn.close()
