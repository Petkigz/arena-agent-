"""Phase 3 cognitive loop: assess, identify uncertainty, and choose next step."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .belief_engine import BeliefEngine, RevisionResult
from .information_gain import InformationNeed, choose_information_need


class ReasoningAction(str, Enum):
    ANSWER = "answer"
    INVESTIGATE = "investigate"
    ACT = "act"
    DEFER = "defer"


@dataclass(frozen=True)
class ReasoningDecision:
    action: ReasoningAction
    confidence: float
    reason: str
    information_need: Optional[InformationNeed] = None
    belief: Optional[RevisionResult] = None


@dataclass
class ReasoningCycle:
    """Cheap deterministic gate around deeper reasoning.

    The cycle never treats the current belief as immutable truth. A caller can
    provide information needs and an action callback; a future planner/LLM can
    replace the policy without changing the evidence and belief interfaces.
    """
    engine: BeliefEngine = field(default_factory=BeliefEngine)
    answer_threshold: float = 0.85
    investigate_threshold: float = 0.55

    def decide(
        self,
        subject: str,
        predicate: str,
        *,
        information_needs: list[InformationNeed] | None = None,
        action_available: bool = False,
    ) -> ReasoningDecision:
        belief = self.engine.inspect(subject, predicate)
        if belief is None:
            need = choose_information_need(information_needs or [])
            return ReasoningDecision(
                ReasoningAction.INVESTIGATE if need else ReasoningAction.DEFER,
                0.0,
                "No supported belief exists yet.",
                need,
                None,
            )

        if belief.confidence >= self.answer_threshold:
            return ReasoningDecision(ReasoningAction.ANSWER, belief.confidence, "Best hypothesis exceeds answer threshold.", belief=belief)

        need = choose_information_need(information_needs or [])
        if need is not None:
            return ReasoningDecision(ReasoningAction.INVESTIGATE, belief.confidence, "Uncertainty remains and useful information is available.", need, belief)

        if action_available and belief.confidence >= self.investigate_threshold:
            return ReasoningDecision(ReasoningAction.ACT, belief.confidence, "Evidence is sufficient for a bounded action, but not certainty.", belief=belief)

        return ReasoningDecision(ReasoningAction.DEFER, belief.confidence, "Evidence is insufficient for a safe decision.", belief=belief)

    def observe_and_decide(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0, rationale: str | None = None, information_needs: list[InformationNeed] | None = None, action_available: bool = False) -> ReasoningDecision:
        self.engine.ingest(subject, predicate, value, source=source, confidence=confidence, rationale=rationale)
        return self.decide(subject, predicate, information_needs=information_needs, action_available=action_available)
