"""Phase 5A: Self-Model.

The system tracks its own capability performance per domain and knows
what it's good at and bad at. Routes tasks to appropriate models
(fast vs reasoning) based on self-assessment.

Builds on StrategyOutcomeStore and LessonStore to create a comprehensive
self-assessment backed by actual performance data.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Self-Assessment Data Structures ──────────────────────────────────

@dataclass(frozen=True)
class CapabilityAssessment:
    """Performance assessment for a specific capability in a domain."""
    action_type: str
    domain: str               # intent_type or target_domain
    total_attempts: int
    successes: int
    success_rate: float
    avg_latency_ms: float
    avg_surprisal: float       # prediction accuracy (low = predictable)
    confidence: float          # how confident we are in this assessment
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    last_assessed: str = field(default_factory=_now)

    @property
    def is_strong(self) -> bool:
        return self.success_rate >= 0.8 and self.total_attempts >= 3

    @property
    def is_weak(self) -> bool:
        return self.success_rate < 0.5 and self.total_attempts >= 3

    @property
    def proficiency_label(self) -> str:
        if self.total_attempts < 3:
            return "untested"
        if self.success_rate >= 0.9:
            return "expert"
        if self.success_rate >= 0.7:
            return "proficient"
        if self.success_rate >= 0.5:
            return "developing"
        return "struggling"


@dataclass(frozen=True)
class SelfReport:
    """Complete self-assessment report."""
    total_capabilities: int
    strong_capabilities: List[CapabilityAssessment]
    weak_capabilities: List[CapabilityAssessment]
    untested_capabilities: List[CapabilityAssessment]
    overall_success_rate: float
    total_tasks_completed: int
    best_domain: Optional[str]
    worst_domain: Optional[str]
    model_routing_suggestions: Dict[str, str]  # action_type → "fast" or "reasoning"
    timestamp: str = field(default_factory=_now)


# ── Self-Model Engine ────────────────────────────────────────────────

class SelfModel:
    """
    Aggregates performance data into a self-model that answers:
    - "What am I good at?"
    - "What am I bad at?"
    - "What model should handle this task?"
    """

    def __init__(
        self,
        outcome_store: Optional[Any] = None,
        lesson_store: Optional[Any] = None
    ) -> None:
        self._outcome_store = outcome_store
        self._lesson_store = lesson_store
        self._assessments: Dict[Tuple[str, str], CapabilityAssessment] = {}
        self._model_preferences: Dict[str, str] = {}  # action_type → "fast" or "reasoning"

    def assess_capability(self, action_type: str, domain: str = "") -> Optional[CapabilityAssessment]:
        """
        Assess performance for a specific capability.
        Pulls data from outcome_store if available.
        """
        if not self._outcome_store:
            return None

        # Try domain-specific first, then general
        score = None
        if domain:
            score = self._outcome_store.score_strategy(domain, action_type)
        if not score:
            # Try all domains
            all_scores = self._outcome_store.all_scores()
            matching = [s for s in all_scores if s.action_type == action_type]
            if matching:
                # Aggregate across domains
                total = sum(s.total_attempts for s in matching)
                successes = sum(s.successes for s in matching)
                avg_latency = sum(s.avg_latency_ms * s.total_attempts for s in matching) / total if total else 0
                avg_surprisal = sum(s.avg_surprisal * s.total_attempts for s in matching) / total if total else 0
                score = type('AggScore', (), {
                    'total_attempts': total,
                    'successes': successes,
                    'failures': total - successes,
                    'success_rate': successes / total if total else 0,
                    'avg_latency_ms': avg_latency,
                    'avg_surprisal': avg_surprisal,
                    'consecutive_failures': max(s.consecutive_failures for s in matching),
                    'last_used': matching[-1].last_used,
                })()

        if not score:
            return None

        # Determine strengths and weaknesses
        strengths = []
        weaknesses = []
        if score.success_rate >= 0.8:
            strengths.append(f"High success rate ({score.success_rate:.0%})")
        if score.avg_latency_ms < 200:
            strengths.append(f"Fast execution ({score.avg_latency_ms:.0f}ms avg)")
        if score.avg_surprisal < 0.2:
            strengths.append(f"Predictable outcomes (surprisal {score.avg_surprisal:.2f})")
        if score.success_rate < 0.5:
            weaknesses.append(f"Low success rate ({score.success_rate:.0%})")
        if score.consecutive_failures >= 3:
            weaknesses.append(f"{score.consecutive_failures} consecutive failures")
        if score.avg_surprisal > 0.5:
            weaknesses.append(f"Unpredictable outcomes (surprisal {score.avg_surprisal:.2f})")

        # Confidence in assessment grows with sample size
        confidence = min(1.0, score.total_attempts / 10.0)

        assessment = CapabilityAssessment(
            action_type=action_type,
            domain=domain or "general",
            total_attempts=score.total_attempts,
            successes=score.successes,
            success_rate=score.success_rate,
            avg_latency_ms=score.avg_latency_ms,
            avg_surprisal=score.avg_surprisal,
            confidence=confidence,
            strengths=strengths,
            weaknesses=weaknesses,
        )
        self._assessments[(action_type, domain or "general")] = assessment
        return assessment

    def generate_report(self) -> SelfReport:
        """Generate a complete self-assessment report."""
        # Assess all known capabilities
        if self._outcome_store:
            all_scores = self._outcome_store.all_scores()
            for score in all_scores:
                self.assess_capability(score.action_type, score.goal_type)

        all_assessments = list(self._assessments.values())
        strong = [a for a in all_assessments if a.is_strong]
        weak = [a for a in all_assessments if a.is_weak]
        untested = [a for a in all_assessments if a.total_attempts < 3]

        total_tasks = sum(a.total_attempts for a in all_assessments)
        total_successes = sum(a.successes for a in all_assessments)
        overall_rate = total_successes / total_tasks if total_tasks > 0 else 0.0

        # Find best and worst domains
        domain_rates: Dict[str, Tuple[int, int]] = {}
        for a in all_assessments:
            d = a.domain
            if d not in domain_rates:
                domain_rates[d] = [0, 0]
            domain_rates[d][0] += a.successes
            domain_rates[d][1] += a.total_attempts

        best_domain = None
        worst_domain = None
        if domain_rates:
            domain_scores = {
                d: (s / t if t > 0 else 0)
                for d, (s, t) in domain_rates.items() if t >= 3
            }
            if domain_scores:
                best_domain = max(domain_scores, key=domain_scores.get)
                worst_domain = min(domain_scores, key=domain_scores.get)

        # Model routing suggestions
        routing = {}
        for a in all_assessments:
            if a.total_attempts < 3:
                routing[a.action_type] = "reasoning"  # Unknown → use careful model
            elif a.is_strong and a.avg_surprisal < 0.3:
                routing[a.action_type] = "fast"  # Good at it → fast model
            elif a.is_weak or a.avg_surprisal > 0.5:
                routing[a.action_type] = "reasoning"  # Bad at it → reasoning model
            else:
                routing[a.action_type] = "fast"  # Default → fast model

        return SelfReport(
            total_capabilities=len(all_assessments),
            strong_capabilities=sorted(strong, key=lambda a: a.success_rate, reverse=True),
            weak_capabilities=sorted(weak, key=lambda a: a.success_rate),
            untested_capabilities=untested,
            overall_success_rate=overall_rate,
            total_tasks_completed=total_tasks,
            best_domain=best_domain,
            worst_domain=worst_domain,
            model_routing_suggestions=routing,
        )

    def suggest_model(self, action_type: str, complexity: str = "auto") -> str:
        """
        Suggest which model to use for a task.
        Returns "fast" or "reasoning".
        """
        if complexity != "auto":
            return complexity

        # Check explicit preferences first
        if action_type in self._model_preferences:
            return self._model_preferences[action_type]

        # Check assessments across all domains for this action_type
        matching = [
            a for (at, _), a in self._assessments.items()
            if at == action_type
        ]
        if matching:
            # Use the best assessment (highest success rate)
            best = max(matching, key=lambda a: a.success_rate)
            if best.is_strong and best.avg_surprisal < 0.3:
                return "fast"
            if best.is_weak or best.avg_surprisal > 0.5:
                return "reasoning"

        # Default: use reasoning for unknown tasks
        return "reasoning"

    def set_model_preference(self, action_type: str, model: str) -> None:
        """Explicitly set model preference for an action type."""
        if model not in ("fast", "reasoning"):
            raise ValueError(f"Model must be 'fast' or 'reasoning', got '{model}'")
        self._model_preferences[action_type] = model

    def what_am_i_good_at(self) -> List[CapabilityAssessment]:
        """Return capabilities where the system performs well."""
        if self._outcome_store:
            all_scores = self._outcome_store.all_scores()
            for score in all_scores:
                self.assess_capability(score.action_type, score.goal_type)
        return sorted(
            [a for a in self._assessments.values() if a.is_strong],
            key=lambda a: a.success_rate,
            reverse=True
        )

    def what_am_i_bad_at(self) -> List[CapabilityAssessment]:
        """Return capabilities where the system performs poorly."""
        if self._outcome_store:
            all_scores = self._outcome_store.all_scores()
            for score in all_scores:
                self.assess_capability(score.action_type, score.goal_type)
        return sorted(
            [a for a in self._assessments.values() if a.is_weak],
            key=lambda a: a.success_rate
        )
