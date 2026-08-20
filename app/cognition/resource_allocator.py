"""Phase 5C: Strategic Resource Allocation.

Classifies tasks by complexity and allocates reasoning budget accordingly:
- Simple tasks (single-step, high-confidence) → fast model, minimal investigation
- Complex tasks (multi-step, uncertain) → reasoning model, deeper investigation
- Bounded exploration: knows when to stop investigating

Optimizes latency for simple tasks without sacrificing quality on complex ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Task Complexity Classification ───────────────────────────────────

class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"        # Single-step, high confidence, known pattern
    SIMPLE = "simple"          # Single-step, moderate confidence
    MODERATE = "moderate"      # May need 2 steps or has some uncertainty
    COMPLEX = "complex"        # Multi-step, uncertain, requires investigation
    HARD = "hard"              # Novel, multi-step, high uncertainty


# Complexity → resource budget mapping
RESOURCE_BUDGETS = {
    TaskComplexity.TRIVIAL: {
        "model": "fast",
        "max_reasoning_cycles": 1,
        "max_investigation_depth": 0,
        "max_replan_attempts": 0,
        "max_tokens": 150,
        "timeout_ms": 5000,
    },
    TaskComplexity.SIMPLE: {
        "model": "fast",
        "max_reasoning_cycles": 2,
        "max_investigation_depth": 1,
        "max_replan_attempts": 1,
        "max_tokens": 300,
        "timeout_ms": 10000,
    },
    TaskComplexity.MODERATE: {
        "model": "fast",
        "max_reasoning_cycles": 3,
        "max_investigation_depth": 2,
        "max_replan_attempts": 2,
        "max_tokens": 500,
        "timeout_ms": 20000,
    },
    TaskComplexity.COMPLEX: {
        "model": "reasoning",
        "max_reasoning_cycles": 5,
        "max_investigation_depth": 3,
        "max_replan_attempts": 3,
        "max_tokens": 1000,
        "timeout_ms": 60000,
    },
    TaskComplexity.HARD: {
        "model": "reasoning",
        "max_reasoning_cycles": 8,
        "max_investigation_depth": 5,
        "max_replan_attempts": 4,
        "max_tokens": 1500,
        "timeout_ms": 120000,
    },
}


@dataclass(frozen=True)
class ResourceAllocation:
    """Resource budget allocated to a specific task."""
    complexity: TaskComplexity
    model: str                    # "fast" or "reasoning"
    max_reasoning_cycles: int
    max_investigation_depth: int
    max_replan_attempts: int
    max_tokens: int
    timeout_ms: int
    classification_reason: str
    timestamp: str = field(default_factory=_now)


@dataclass(frozen=True)
class AllocationStats:
    """Statistics about resource allocation effectiveness."""
    total_allocated: int
    by_complexity: Dict[str, int]
    avg_latency_by_complexity: Dict[str, float]
    success_rate_by_complexity: Dict[str, float]
    efficiency_score: float  # higher = better resource utilization
    over_allocated: int      # tasks that got more resources than needed
    under_allocated: int     # tasks that needed more resources than given


# ── Resource Allocator ───────────────────────────────────────────────

class ResourceAllocator:
    """
    Classifies task complexity and allocates appropriate resources.

    Classification signals:
    - Number of entities involved
    - Number of required capabilities
    - Presence of unknowns in goal representation
    - Historical success rate for similar tasks
    - Whether the task is a known pattern
    """

    # Thresholds for complexity classification
    SINGLE_STEP_CONFIDENCE = 0.8
    HIGH_CONFIDENCE = 0.9
    UNKNOWN_THRESHOLD = 2     # more than this many unknowns → complex
    MULTI_ENTITY_THRESHOLD = 3 # more than this → at least moderate

    def __init__(
        self,
        self_model: Optional[Any] = None,
        outcome_store: Optional[Any] = None
    ) -> None:
        self._self_model = self_model
        self._outcome_store = outcome_store
        self._allocation_history: List[Tuple[ResourceAllocation, bool, float]] = []
        # (allocation, success, latency_ms)

    def classify_complexity(
        self,
        goal_rep: Optional[Any] = None,
        action_type: str = "",
        candidates: Optional[List[Dict]] = None,
        user_text: str = ""
    ) -> Tuple[TaskComplexity, str]:
        """
        Classify task complexity based on multiple signals.
        Returns (complexity, reason).
        """
        signals: Dict[str, float] = {}
        reasons: List[str] = []

        # Signal 1: Number of candidate strategies
        num_candidates = len(candidates) if candidates else 0
        if num_candidates <= 1:
            signals["candidates"] = 0.0  # Single path → simpler
            reasons.append("single candidate strategy")
        elif num_candidates <= 3:
            signals["candidates"] = 0.3
        else:
            signals["candidates"] = 0.6
            reasons.append(f"{num_candidates} candidate strategies")

        # Signal 2: Number of entities
        entities = getattr(goal_rep, "entities", []) if goal_rep else []
        num_entities = len(entities)
        if num_entities <= 1:
            signals["entities"] = 0.0
        elif num_entities <= self.MULTI_ENTITY_THRESHOLD:
            signals["entities"] = 0.3
        else:
            signals["entities"] = 0.6
            reasons.append(f"{num_entities} entities involved")

        # Signal 3: Unknowns in goal representation
        unknowns = getattr(goal_rep, "unknowns", []) if goal_rep else []
        num_unknowns = len(unknowns)
        if num_unknowns == 0:
            signals["unknowns"] = 0.0
        elif num_unknowns <= self.UNKNOWN_THRESHOLD:
            signals["unknowns"] = 0.4
            reasons.append(f"{num_unknowns} unknowns")
        else:
            signals["unknowns"] = 0.8
            reasons.append(f"{num_unknowns} unknowns (high uncertainty)")

        # Signal 4: Required capabilities
        capabilities = getattr(goal_rep, "required_capabilities", []) if goal_rep else []
        num_caps = len(capabilities)
        if num_caps <= 1:
            signals["capabilities"] = 0.0
        elif num_caps <= 2:
            signals["capabilities"] = 0.3
        else:
            signals["capabilities"] = 0.6
            reasons.append(f"{num_caps} required capabilities")

        # Signal 5: Historical success rate for this action type
        if self._outcome_store and action_type:
            all_scores = self._outcome_store.all_scores()
            matching = [s for s in all_scores if s.action_type == action_type]
            if matching:
                avg_rate = sum(s.success_rate for s in matching) / len(matching)
                if avg_rate >= self.HIGH_CONFIDENCE:
                    signals["history"] = 0.0
                    reasons.append(f"historical success {avg_rate:.0%}")
                elif avg_rate >= 0.5:
                    signals["history"] = 0.3
                else:
                    signals["history"] = 0.7
                    reasons.append(f"historical difficulty ({avg_rate:.0%} success)")
            else:
                signals["history"] = 0.5  # Unknown → moderate uncertainty
                reasons.append("no historical data")

        # Signal 6: Self-model assessment
        if self._self_model and action_type:
            model_suggestion = self._self_model.suggest_model(action_type)
            if model_suggestion == "fast":
                signals["self_model"] = 0.0
            else:
                signals["self_model"] = 0.5
                reasons.append("self-model suggests reasoning model")

        # Aggregate score
        if not signals:
            return TaskComplexity.SIMPLE, "default classification"

        score = sum(signals.values()) / len(signals)

        # Map score to complexity
        if score < 0.1:
            complexity = TaskComplexity.TRIVIAL
        elif score < 0.25:
            complexity = TaskComplexity.SIMPLE
        elif score < 0.45:
            complexity = TaskComplexity.MODERATE
        elif score < 0.65:
            complexity = TaskComplexity.COMPLEX
        else:
            complexity = TaskComplexity.HARD

        reason = f"complexity_score={score:.2f}: " + ", ".join(reasons) if reasons else f"complexity_score={score:.2f}"
        return complexity, reason

    def allocate(
        self,
        goal_rep: Optional[Any] = None,
        action_type: str = "",
        candidates: Optional[List[Dict]] = None,
        user_text: str = "",
        override_complexity: Optional[TaskComplexity] = None
    ) -> ResourceAllocation:
        """
        Classify task complexity and allocate resources accordingly.
        """
        if override_complexity:
            complexity = override_complexity
            reason = f"overridden to {complexity.value}"
        else:
            complexity, reason = self.classify_complexity(
                goal_rep, action_type, candidates, user_text
            )

        budget = RESOURCE_BUDGETS[complexity]

        return ResourceAllocation(
            complexity=complexity,
            model=budget["model"],
            max_reasoning_cycles=budget["max_reasoning_cycles"],
            max_investigation_depth=budget["max_investigation_depth"],
            max_replan_attempts=budget["max_replan_attempts"],
            max_tokens=budget["max_tokens"],
            timeout_ms=budget["timeout_ms"],
            classification_reason=reason,
        )

    def record_outcome(
        self,
        allocation: ResourceAllocation,
        success: bool,
        latency_ms: float,
        cycles_used: int = 1
    ) -> None:
        """Record the outcome of a task with its resource allocation."""
        self._allocation_history.append((allocation, success, latency_ms))

    def should_stop_investigating(
        self,
        cycles_used: int,
        max_cycles: int,
        current_confidence: float,
        confidence_threshold: float = 0.7
    ) -> bool:
        """
        Bounded exploration: decide whether to stop investigating.
        Returns True if investigation should stop.
        """
        # Stop if we've used all cycles
        if cycles_used >= max_cycles:
            return True
        # Stop if confidence is already high enough
        if current_confidence >= confidence_threshold:
            return True
        # Stop if confidence isn't improving (diminishing returns)
        return False

    def get_stats(self) -> AllocationStats:
        """Compute allocation effectiveness statistics."""
        if not self._allocation_history:
            return AllocationStats(
                total_allocated=0,
                by_complexity={},
                avg_latency_by_complexity={},
                success_rate_by_complexity={},
                efficiency_score=0.0,
                over_allocated=0,
                under_allocated=0,
            )

        by_complexity: Dict[str, List[Tuple[bool, float]]] = {}
        for alloc, success, latency in self._allocation_history:
            key = alloc.complexity.value
            if key not in by_complexity:
                by_complexity[key] = []
            by_complexity[key].append((success, latency))

        count_by_complexity = {k: len(v) for k, v in by_complexity.items()}
        avg_latency = {
            k: sum(lat for _, lat in v) / len(v)
            for k, v in by_complexity.items()
        }
        success_rate = {
            k: sum(1 for s, _ in v if s) / len(v)
            for k, v in by_complexity.items()
        }

        # Count over/under allocated
        over_allocated = 0
        under_allocated = 0
        for alloc, success, latency in self._allocation_history:
            if alloc.complexity in (TaskComplexity.COMPLEX, TaskComplexity.HARD) and success and latency < alloc.timeout_ms * 0.3:
                over_allocated += 1  # Succeeded quickly with complex allocation
            elif alloc.complexity in (TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE) and not success:
                under_allocated += 1  # Failed with simple allocation

        # Efficiency score: lower latency + higher success = better
        total_latency = sum(lat for _, _, lat in self._allocation_history)
        total_success = sum(1 for _, s, _ in self._allocation_history if s)
        total = len(self._allocation_history)
        avg_lat = total_latency / total if total else 0
        avg_suc = total_success / total if total else 0
        # Normalize: lower latency and higher success = higher score
        efficiency = avg_suc * (1.0 - min(1.0, avg_lat / 60000.0))

        return AllocationStats(
            total_allocated=total,
            by_complexity=count_by_complexity,
            avg_latency_by_complexity={k: round(v, 1) for k, v in avg_latency.items()},
            success_rate_by_complexity={k: round(v, 3) for k, v in success_rate.items()},
            efficiency_score=round(efficiency, 3),
            over_allocated=over_allocated,
            under_allocated=under_allocated,
        )
