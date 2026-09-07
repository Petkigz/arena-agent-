"""Bounded pre-gate criticality review for action recommendations.

This review is a challenge record, not an authorization path. It asks whether
risk, missing history, contradictory evidence, or high confidence should make
the recommendation more visible before the existing ActionGate runs. It never
turns a historical result into execution truth and never bypasses owner
approval, cancellation, or execution verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass(frozen=True)
class CriticalityReview:
    review_id: str
    action_type: str
    severity: str
    triggers: List[str] = field(default_factory=list)
    challenged_assumptions: List[str] = field(default_factory=list)
    checks: Dict[str, bool] = field(default_factory=dict)
    recommendation: str = "proceed_to_existing_gate"
    decision_stage: str = "criticality_review"

    @property
    def required(self) -> bool:
        return bool(self.triggers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "action_type": self.action_type,
            "severity": self.severity,
            "triggers": list(self.triggers),
            "challenged_assumptions": list(self.challenged_assumptions),
            "checks": dict(self.checks),
            "recommendation": self.recommendation,
            "decision_stage": self.decision_stage,
            "required": self.required,
        }


def review_action_proposal(
    proposal: Any,
    *,
    goal_rep: Optional[Any] = None,
    calibrated_confidence: Optional[float] = None,
    history_available: Optional[bool] = None,
    memory_conflict: bool = False,
) -> CriticalityReview:
    """Run deterministic adversarial checks before the existing ActionGate."""
    action_type = str(getattr(proposal, "action_type", "") or "")
    raw_payload = getattr(proposal, "payload", None)
    payload = {} if raw_payload is None else raw_payload
    raw_predicted = getattr(proposal, "predicted_outcome", None)
    predicted = {} if raw_predicted is None else raw_predicted
    triggers: List[str] = []
    assumptions: List[str] = []

    safety_level: Optional[int] = None
    try:
        from app.cognition.tool_registry import capability_safety_or_none
        declared = capability_safety_or_none(action_type)
        # Unknown-to-the-authority is not evidence of safety. Preserve a
        # proposal's declared level only when the registry cannot be consulted
        # at all; otherwise an unknown capability remains high-risk for review.
        safety_level = (
            int(declared)
            if declared is not None
            else 99
        )
    except Exception:
        try:
            safety_level = int(getattr(proposal, "safety_level", 0) or 0)
        except (TypeError, ValueError):
            safety_level = 99
    if safety_level >= 3:
        triggers.append("high_risk_action")
        assumptions.append("owner authorization and the existing policy gate must still approve this action")

    if history_available is False:
        triggers.append("no_verified_action_history")
        assumptions.append("the candidate has no verified local outcome history")

    if memory_conflict:
        triggers.append("conflicting_historical_evidence")
        assumptions.append("historical records disagree and must not be silently synthesized")

    unknowns = list(getattr(goal_rep, "unknowns", []) or []) if goal_rep is not None else []
    if unknowns:
        triggers.append("unresolved_goal_unknowns")
        assumptions.append(f"{len(unknowns)} goal unknown(s) remain unresolved")

    confidence = None if calibrated_confidence is None else float(calibrated_confidence)
    if confidence is not None and confidence >= 0.85 and (history_available is not True or unknowns):
        triggers.append("high_confidence_under_uncertainty")
        assumptions.append("high confidence is not treated as verification while evidence is incomplete")

    checks = {
        "action_type_present": bool(action_type),
        "payload_is_mapping": isinstance(payload, dict),
        "predicted_outcome_present": bool(predicted),
        "authorization_left_to_action_gate": True,
        "execution_truth_left_to_observation": True,
    }
    if not checks["action_type_present"] or not checks["payload_is_mapping"]:
        triggers.append("malformed_recommendation")
    if not checks["predicted_outcome_present"]:
        triggers.append("missing_prediction")

    severity = "high" if any(
        trigger in triggers
        for trigger in (
            "high_risk_action",
            "conflicting_historical_evidence",
            "malformed_recommendation",
        )
    ) else ("moderate" if triggers else "low")
    recommendation = "proceed_to_existing_gate"
    if triggers:
        recommendation = "surface_review_and_preserve_uncertainty"

    return CriticalityReview(
        review_id=f"review_{uuid4().hex[:12]}",
        action_type=action_type,
        severity=severity,
        triggers=triggers,
        challenged_assumptions=assumptions,
        checks=checks,
        recommendation=recommendation,
    )
