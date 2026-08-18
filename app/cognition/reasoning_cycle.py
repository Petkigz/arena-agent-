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
    proposed_action: Optional[Any] = None


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
        proposed_action: Optional[Any] = None,
        available_capabilities: Optional[dict[str, bool]] = None,
    ) -> ReasoningDecision:
        belief = self.engine.inspect(subject, predicate)

        # 1. Action Intent: Direct system modification or tool execution requested
        if predicate == "action_intent":
            if action_available:
                return ReasoningDecision(
                    ReasoningAction.ACT,
                    belief.confidence if belief else 0.9,
                    "Explicit action intent provided with verified available execution capabilities.",
                    belief=belief,
                    proposed_action=proposed_action
                )
            else:
                missing_caps = [c for c, avail in (available_capabilities or {}).items() if not avail]
                missing_str = missing_caps[0] if missing_caps else "requested"
                return ReasoningDecision(
                    ReasoningAction.DEFER,
                    0.0,
                    f"Action intent requested, but required capability '{missing_str}' is currently unavailable or offline.",
                    belief=belief
                )

        # 2. Information Need: Diagnostic or missing evidence query
        if predicate == "information_need" or belief is None:
            need = choose_information_need(information_needs or [])
            if need or predicate == "information_need":
                return ReasoningDecision(
                    ReasoningAction.INVESTIGATE,
                    belief.confidence if belief else 0.3,
                    "Information need or diagnostic query detected; running investigation probes.",
                    information_need=need,
                    belief=belief
                )

        # 3. Knowledge Query: Direct answer or high confidence belief
        if belief and belief.confidence >= self.answer_threshold:
            return ReasoningDecision(ReasoningAction.ANSWER, belief.confidence, "Best hypothesis exceeds answer threshold.", belief=belief)

        if predicate == "knowledge_query":
            return ReasoningDecision(ReasoningAction.ANSWER, 0.9, "Knowledge query provided; formulating direct conversational answer.", belief=belief)

        need = choose_information_need(information_needs or [])
        if need is not None:
            return ReasoningDecision(ReasoningAction.INVESTIGATE, belief.confidence if belief else 0.4, "Uncertainty remains and useful information is available.", information_need=need, belief=belief)

        if action_available and belief and belief.confidence >= self.investigate_threshold:
            return ReasoningDecision(ReasoningAction.ACT, belief.confidence, "Evidence is sufficient for a bounded action.", belief=belief, proposed_action=proposed_action)

        return ReasoningDecision(ReasoningAction.DEFER, belief.confidence if belief else 0.0, "Evidence is insufficient for a safe decision.", belief=belief)

    def observe_and_decide(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0, rationale: str | None = None, information_needs: list[InformationNeed] | None = None, action_available: bool = False, proposed_action: Optional[Any] = None, available_capabilities: Optional[dict[str, bool]] = None) -> ReasoningDecision:
        self.engine.ingest(subject, predicate, value, source=source, confidence=confidence, rationale=rationale)
        return self.decide(subject, predicate, information_needs=information_needs, action_available=action_available, proposed_action=proposed_action, available_capabilities=available_capabilities)
