"""User-facing epistemic status for evidence-grounded responses.

This module turns the runtime's evidence state into a concise presentation for
an owner.  It deliberately does not pretend that a raw model score is a
calibrated probability: a score is labelled ``evidence_derived`` until
verified outcome history exists for the relevant task class.

The presentation is a summary of trace facts, not hidden chain-of-thought.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


LABEL_HIGH = "Highly confident"
LABEL_MODERATE = "Moderately confident"
LABEL_TENTATIVE = "Tentative"
LABEL_UNKNOWN = "Unknown"


@dataclass(frozen=True)
class EpistemicPresentation:
    """Bounded, user-facing epistemic summary.

    ``confidence_score`` is intentionally optional.  When present, it is an
    evidence-derived or empirically calibrated score, never a claim of
    subjective certainty.  ``calibration_status`` says which one it is.
    """

    evidence_state: str
    confidence_label: str
    confidence_score: Optional[float] = None
    calibration_status: str = "evidence_derived"
    evidence_basis: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    what_would_change: List[str] = field(default_factory=list)
    source_count: int = 0
    freshness: str = "unknown"
    visible: bool = True
    omission_reason: str = ""

    def __post_init__(self) -> None:
        if self.confidence_score is not None:
            object.__setattr__(
                self,
                "confidence_score",
                max(0.0, min(1.0, float(self.confidence_score))),
            )
        object.__setattr__(self, "source_count", max(0, int(self.source_count)))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def short_label(self) -> str:
        """A stable label suitable for clients that do not render prose."""
        return self.confidence_label

    def user_text(self) -> str:
        """Render only trace-backed facts for normal user-facing output."""
        if not self.visible:
            return ""
        basis = "; ".join(self.evidence_basis[:2]) or "no sufficient evidence"
        text = f"Epistemic status: {self.confidence_label} — {basis}."
        if self.assumptions:
            text += f" Assumption: {self.assumptions[0]}."
        if self.what_would_change:
            text += f" This changes if {self.what_would_change[0]}."
        return text

    def append_to(self, reply: str) -> str:
        """Append a concise status without duplicating an existing marker."""
        reply = str(reply or "")
        marker = "Epistemic status:"
        if not self.visible or marker in reply:
            return reply
        suffix = self.user_text()
        return f"{reply.rstrip()}\n\n{suffix}" if reply.strip() else suffix

    def explanation(self) -> Dict[str, Any]:
        """Return an on-demand explanation payload without private reasoning."""
        return {
            "confidence_label": self.confidence_label,
            "evidence_state": self.evidence_state,
            "calibration_status": self.calibration_status,
            "confidence_score": self.confidence_score,
            "evidence_basis": list(self.evidence_basis),
            "assumptions": list(self.assumptions),
            "what_would_change": list(self.what_would_change),
            "source_count": self.source_count,
            "freshness": self.freshness,
            "unknowns": [
                "Private chain-of-thought is not exposed or claimed.",
            ],
        }


def _normalise_items(items: Optional[Iterable[Any]]) -> List[str]:
    result: List[str] = []
    for item in items or []:
        text = str(item).strip()
        if text and text not in result:
            result.append(text[:240])
    return result


def _label_for(
    evidence_state: str,
    confidence_score: Optional[float],
    *,
    direct_observation: bool,
    source_count: int,
) -> str:
    state = (evidence_state or "unknown").strip().lower()
    if state in {"unknown", "contradictory", "unverified", "unavailable"}:
        return LABEL_UNKNOWN if state in {"unknown", "unavailable"} else LABEL_TENTATIVE
    if state in {"simulated", "inferred", "recalled"}:
        if confidence_score is not None and confidence_score >= 0.75 and source_count >= 2:
            return LABEL_MODERATE
        return LABEL_TENTATIVE
    if direct_observation and confidence_score is not None and confidence_score >= 0.85 and source_count >= 1:
        return LABEL_HIGH
    if confidence_score is not None and confidence_score >= 0.65:
        return LABEL_MODERATE
    return LABEL_TENTATIVE


def build_epistemic_presentation(
    *,
    evidence_state: str,
    confidence_score: Optional[float] = None,
    direct_observation: bool = False,
    evidence_basis: Optional[Iterable[Any]] = None,
    assumptions: Optional[Iterable[Any]] = None,
    what_would_change: Optional[Iterable[Any]] = None,
    source_count: int = 0,
    freshness: str = "unknown",
    calibration_status: str = "evidence_derived",
    visible: bool = True,
    omission_reason: str = "",
) -> EpistemicPresentation:
    """Build a conservative user-facing epistemic summary.

    The caller supplies facts from the authoritative runtime path.  This
    helper only maps those facts to a label; it never upgrades UNKNOWN merely
    because a model produced fluent prose.
    """
    basis = _normalise_items(evidence_basis)
    assumptions_list = _normalise_items(assumptions)
    changes = _normalise_items(what_would_change)
    source_count = max(int(source_count), len(basis))
    label = _label_for(
        evidence_state,
        confidence_score,
        direct_observation=direct_observation,
        source_count=source_count,
    )
    return EpistemicPresentation(
        evidence_state=(evidence_state or "unknown").strip().lower(),
        confidence_label=label,
        confidence_score=confidence_score,
        calibration_status=calibration_status,
        evidence_basis=basis,
        assumptions=assumptions_list,
        what_would_change=changes,
        source_count=source_count,
        freshness=freshness or "unknown",
        visible=bool(visible),
        omission_reason=omission_reason,
    )


def presentation_for_cycle(
    *,
    goal_verified: bool,
    environment_observed: bool = False,
    evidence_items: Optional[Iterable[Any]] = None,
    action_type: str = "",
    failed: bool = False,
    unknown: bool = False,
    confidence_score: Optional[float] = None,
    source_count: int = 0,
) -> EpistemicPresentation:
    """Build a conservative presentation for one cognitive-cycle result."""
    items = _normalise_items(evidence_items)
    if unknown:
        state = "unknown"
        items = items or ["the required observation was unavailable"]
        score = None
    elif failed:
        state = "contradictory" if environment_observed else "unverified"
        items = items or ["the requested outcome was not independently verified"]
        score = confidence_score
    elif environment_observed and goal_verified:
        state = "verified"
        items = items or ["an authoritative observation matched the requested outcome"]
        score = confidence_score if confidence_score is not None else 0.9
    elif goal_verified:
        state = "inferred"
        items = items or ["the response was accepted without a direct environmental observation"]
        score = confidence_score if confidence_score is not None else 0.6
    else:
        state = "unverified"
        items = items or ["the response or action has not been independently verified"]
        score = confidence_score

    assumptions = []
    if not environment_observed:
        assumptions.append("the available context is sufficient for this response")
    changes = ["new evidence contradicts or materially changes the recorded result"]
    if action_type:
        changes.append(f"a later observation changes the outcome of {action_type}")
    return build_epistemic_presentation(
        evidence_state=state,
        confidence_score=score,
        direct_observation=environment_observed,
        evidence_basis=items,
        assumptions=assumptions,
        what_would_change=changes,
        source_count=source_count or len(items),
        freshness="current cycle" if environment_observed else "not directly observed",
        calibration_status="evidence_derived",
    )
