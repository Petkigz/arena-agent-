"""Connect evidence, competing hypotheses, and belief revision."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .beliefs import BeliefStore
from .hypotheses import HypothesisSet

@dataclass(frozen=True)
class RevisionResult:
    subject: str
    predicate: str
    selected_value: Any
    confidence: float
    alternatives: tuple[Any, ...]

class BeliefEngine:
    """Deterministic evidence aggregator; reasoning models can challenge its output."""
    def __init__(self, beliefs: BeliefStore | None = None, hypotheses: HypothesisSet | None = None) -> None:
        self.beliefs = beliefs or BeliefStore()
        self.hypotheses = hypotheses or HypothesisSet()

    def ingest(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0, rationale: str | None = None) -> RevisionResult:
        belief = self.beliefs.observe(subject, predicate, value, source=source, confidence=confidence)
        self.hypotheses.upsert(subject, predicate, value, score=belief.confidence, rationale=rationale)
        ranked = self.hypotheses.rank(subject, predicate)
        best = ranked[0]
        return RevisionResult(subject, predicate, best.value, best.score, tuple(h.value for h in ranked[1:]))

    def inspect(self, subject: str, predicate: str) -> RevisionResult | None:
        ranked = self.hypotheses.rank(subject, predicate)
        if not ranked:
            return None
        best = ranked[0]
        return RevisionResult(subject, predicate, best.value, best.score, tuple(h.value for h in ranked[1:]))
