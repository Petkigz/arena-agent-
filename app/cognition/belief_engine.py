"""Connect evidence, competing hypotheses, and belief revision."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Dict
from .beliefs import BeliefStore
from .hypotheses import HypothesisSet

@dataclass(frozen=True)
class RevisionResult:
    subject: str
    predicate: str
    selected_value: Any
    confidence: float
    alternatives: tuple[Any, ...]
    contradictions: tuple[Any, ...] = ()

class BeliefEngine:
    """Deterministic evidence aggregator; reasoning models can challenge its output."""
    def __init__(self, beliefs: Optional[BeliefStore] = None, hypotheses: Optional[HypothesisSet] = None, db_path: Optional[str] = None) -> None:
        self.beliefs = beliefs or BeliefStore(db_path=db_path)
        self.hypotheses = hypotheses or HypothesisSet()

    def ingest(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0, rationale: Optional[str] = None, source_reliability: float = 1.0, half_life_seconds: Optional[float] = None, task_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> RevisionResult:
        belief = self.beliefs.observe(subject, predicate, value, source=source, confidence=confidence, source_reliability=source_reliability, half_life_seconds=half_life_seconds, task_id=task_id, metadata=metadata)
        for candidate in {repr(e.value): e.value for e in belief.evidence}.values():
            support = sum(e.effective_confidence() for e in belief.evidence if e.value == candidate)
            total = sum(e.effective_confidence() for e in belief.evidence) or 1.0
            self.hypotheses.upsert(subject, predicate, candidate, score=min(1.0, support / total), rationale=rationale if candidate == value else None)
        ranked = self.hypotheses.rank(subject, predicate)
        best = ranked[0]
        contradictions = tuple(h.value for h in ranked[1:] if h.score > 0.2)
        return RevisionResult(subject, predicate, best.value, best.score, tuple(h.value for h in ranked[1:]), contradictions)

    def inspect(self, subject: str, predicate: str) -> Optional[RevisionResult]:
        belief = self.beliefs.refresh(subject, predicate)
        if belief is None: return None
        return self.ingest(subject, predicate, belief.value, source="belief_refresh", confidence=belief.confidence)
