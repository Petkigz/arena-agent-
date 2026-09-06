"""Connect evidence, competing hypotheses, and belief revision.

Phase 1A: BeliefEngine now supports evidence-weighted revision with
time decay and provenance weighting. inspect() recalculates from all
evidence rather than relying on incremental updates.

Phase 1 (provenance hardening): Admissibility uses canonical SourceType
enum instead of substring matching.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .beliefs import BeliefStore, Evidence, AdmissibleEvidence
from .hypotheses import HypothesisSet
from .source_types import SourceType, ADMISSIBLE_SOURCES, INADMISSIBLE_SOURCES

@dataclass(frozen=True)
class RevisionResult:
    """
    Result of belief revision, explicitly separating authoritative belief from hypothesis.
    
    Authoritative belief (belief_value/belief_confidence):
      - Derived ONLY from admissible evidence (direct/environmental observations)
      - Stored in BeliefStore
      - Represents "what Arena believes about reality"
      - None if no admissible evidence exists
    
    Hypothesis assessment (hypothesis_value/hypothesis_score):
      - Derived from ALL evidence including inadmissible claims
      - Stored in HypothesisSet
      - Represents "what ranks highest among all claims"
      - May differ from belief when claims contradict observations
    
    Rule: A hypothesis must never masquerade as an environmental belief.
    """
    subject: str
    predicate: str
    # Authoritative environmental belief (from admissible evidence only)
    belief_value: Any = None
    belief_confidence: float = 0.0
    has_belief: bool = False
    # Hypothesis assessment (all evidence including claims)
    hypothesis_value: Any = None
    hypothesis_score: float = 0.0
    alternatives: tuple[Any, ...] = ()
    is_stale: bool = False
    evidence_count: int = 0
    hypothesis_count: int = 0
    hypotheses_bounded: bool = True
    has_competing_hypotheses: bool = False

class BeliefEngine:
    """
    Deterministic evidence aggregator with time-weighted belief revision.
    
    - ingest(): adds evidence and updates beliefs incrementally
    - inspect(): recalculates from all evidence with time decay + provenance weighting
    - maintain(): periodic decay recalculation across all beliefs
    """
    def __init__(self, beliefs: BeliefStore | None = None, hypotheses: HypothesisSet | None = None, db_path: str | None = None) -> None:
        self.beliefs = beliefs or BeliefStore(db_path=db_path)
        self.hypotheses = hypotheses or HypothesisSet()

    # ── Admissibility Gate ──────────────────────────────────────────────
    # Only authoritative environmental evidence enters the belief pool.
    # Uses canonical SourceType enum for exact matching (no substring).

    @classmethod
    def is_admissible(cls, source: Union[str, SourceType], observation_type: str,
                      confidence: float = 1.0) -> bool:
        """
        Check if evidence is admissible to the environmental belief pool.

        Admissibility requires:
        1. source is a canonical ADMISSIBLE SourceType
        2. observation_type is 'direct' or 'environmental' (required, no default)
        3. confidence > 0

        Non-admissible evidence (claims, tool output, user input, etc.)
        is tracked as hypotheses but does not enter BeliefStore.
        
        Phase 1: Uses canonical SourceType enum for exact matching.
        Phase 2: observation_type is required (no default).
        """
        if confidence <= 0:
            return False
        if observation_type not in ("direct", "environmental"):
            return False
        
        # Convert string to SourceType if needed
        if isinstance(source, str):
            source_type = SourceType.from_string(source)
        else:
            source_type = source
        
        return source_type in ADMISSIBLE_SOURCES

    def ingest(self, subject: str, predicate: str, value: Any, *, source: str,
               confidence: float = 1.0, rationale: str | None = None,
               task_id: str | None = None,
               observation_type: str,
               observation_id: str | None = None) -> RevisionResult:
        """
        Add evidence to the belief system.

        Admissible evidence (direct/environmental observations from authoritative
        sources) enters BeliefStore and influences environmental beliefs.

        Non-admissible evidence (self_reported, inferred, execution claims) is
        recorded as a hypothesis (tracked claim) but does NOT enter BeliefStore.
        This prevents tool output, LLM statements, and execution traces from
        becoming unqualified environmental beliefs.

        Phase 3: Creates AdmissibleEvidence (structurally enforced) when admissible.
        Only AdmissibleEvidence can enter BeliefStore — inadmissible evidence
        cannot enter at the type level.

        observation_type: Required classification of how the observation was obtained.
        Phase 2: No default — caller must explicitly classify every evidence submission.

        observation_id: Optional link back to the WorldModel Observation.
        Enables provenance tracing from belief → evidence → observation.
        """
        admissible = self.is_admissible(source, observation_type, confidence)

        if admissible:
            # Create raw Evidence, then wrap in AdmissibleEvidence
            raw_evidence = Evidence(
                source=source, value=value, confidence=confidence,
                observation_id=observation_id, observation_type=observation_type
            )
            admissible_evidence = AdmissibleEvidence.from_evidence(raw_evidence)
            belief = self.beliefs.observe(subject, predicate, admissible_evidence)
            evidence_count = len(belief.evidence)
        else:
            # Non-admissible: check if an authoritative belief already exists
            belief = self.beliefs.get(subject, predicate)
            evidence_count = len(belief.evidence) if belief else 0

        # All evidence is tracked as hypotheses regardless of admissibility
        score = confidence if admissible else confidence * 0.1  # Claims get minimal score
        self.hypotheses.upsert(subject, predicate, value, score=score, rationale=rationale)
        ranked = self.hypotheses.rank(subject, predicate)
        best = ranked[0]
        hypothesis_state = self.hypotheses.snapshot(subject, predicate)

        is_stale = self.beliefs.is_stale(subject, predicate) if admissible else False

        return RevisionResult(
            subject=subject,
            predicate=predicate,
            # Authoritative belief from BeliefStore (admissible evidence only)
            belief_value=belief.value if belief else None,
            belief_confidence=belief.confidence if belief else 0.0,
            has_belief=belief is not None,
            # Hypothesis assessment from all evidence (including claims)
            hypothesis_value=best.value,
            hypothesis_score=best.score,
            alternatives=tuple(h.value for h in ranked[1:]),
            is_stale=is_stale,
            evidence_count=evidence_count,
            hypothesis_count=hypothesis_state["count"],
            hypotheses_bounded=bool(hypothesis_state["bounded"]),
            has_competing_hypotheses=bool(hypothesis_state["competing"]),
        )

    def inspect(self, subject: str, predicate: str, now: Optional[datetime] = None) -> Optional[RevisionResult]:
        """
        Read the authoritative belief and hypothesis state.
        
        This is a READ-ONLY method — it does not modify any state.
        The authoritative belief comes directly from BeliefStore.revise().
        The hypothesis layer is read for informational purposes only (alternatives/claims).
        
        Hypothesis state is updated only by ingest() (the write path).
        inspect() never routes through hypotheses to determine the belief.
        
        Returns None only if no evidence exists at all (no beliefs, no hypotheses).
        """
        # Authoritative belief: recalculated from admissible evidence
        belief = self.beliefs.revise(subject, predicate, now=now)

        # Hypothesis state: read-only, for informational purposes
        ranked = self.hypotheses.rank(subject, predicate)
        if not ranked and not belief:
            return None  # No evidence at all

        best = ranked[0] if ranked else None
        hypothesis_state = self.hypotheses.snapshot(subject, predicate)
        is_stale = self.beliefs.is_stale(subject, predicate, now=now) if belief else False
        return RevisionResult(
            subject=subject,
            predicate=predicate,
            # Authoritative belief from BeliefStore (admissible evidence only)
            belief_value=belief.value if belief else None,
            belief_confidence=belief.confidence if belief else 0.0,
            has_belief=belief is not None,
            # Hypothesis assessment: informational only, never overrides belief
            hypothesis_value=best.value if best else None,
            hypothesis_score=best.score if best else 0.0,
            alternatives=tuple(h.value for h in ranked[1:]) if ranked else (),
            is_stale=is_stale,
            evidence_count=len(belief.evidence) if belief else 0,
            hypothesis_count=hypothesis_state["count"],
            hypotheses_bounded=bool(hypothesis_state["bounded"]),
            has_competing_hypotheses=bool(hypothesis_state["competing"]),
        )

    def hypothesis_snapshot(self, subject: str, predicate: str) -> Dict[str, Any]:
        """Expose bounded hypothesis state without promoting it to belief."""
        return self.hypotheses.snapshot(subject, predicate)

    def maintain(self, now: Optional[datetime] = None) -> int:
        """
        Recalculate all beliefs with current time decay.
        Call periodically (e.g., at session start or between tasks).
        Returns the number of beliefs that changed.
        """
        return self.beliefs.decay_all(now=now)

    def stale_beliefs(self, max_age_hours: float = 48.0, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """List beliefs that need fresh observation."""
        result = []
        for belief in self.beliefs.stale_beliefs(max_age_hours, now=now):
            result.append({
                "subject": belief.subject,
                "predicate": belief.predicate,
                "current_value": belief.value,
                "current_confidence": belief.confidence,
                "evidence_count": len(belief.evidence),
            })
        return result

    def evidence_report(self, subject: str, predicate: str) -> Optional[Dict[str, Any]]:
        """Full evidence provenance report for a belief."""
        return self.beliefs.evidence_summary(subject, predicate)
