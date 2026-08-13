"""Connect evidence, competing hypotheses, calibration, and belief revision."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Dict
from .beliefs import BeliefStore
from .hypotheses import HypothesisSet
from .confidence import ConfidenceCalibrator

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
    def __init__(self, beliefs: Optional[BeliefStore] = None, hypotheses: Optional[HypothesisSet] = None,
                 db_path: Optional[str] = None, calibrator: Optional[ConfidenceCalibrator] = None) -> None:
        self.beliefs = beliefs or BeliefStore(db_path=db_path)
        self.hypotheses = hypotheses or HypothesisSet()
        self.calibrator = calibrator or ConfidenceCalibrator()
        self._rebuild_hypotheses()

    def _rebuild_hypotheses(self) -> None:
        for belief in self.beliefs.list():
            self._sync_hypotheses(belief.subject, belief.predicate, belief.evidence)

    def _sync_hypotheses(self, subject: str, predicate: str, evidence) -> None:
        scores: Dict[str, float] = {}; values: Dict[str, Any] = {}
        for item in evidence:
            key = repr(item.value); scores[key] = scores.get(key, 0.0) + item.effective_confidence(); values[key] = item.value
        total = sum(scores.values()) or 1.0
        for key, score in scores.items():
            self.hypotheses.upsert(subject, predicate, values[key], score=min(1.0, score / total))

    def ingest(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0,
               rationale: Optional[str] = None, source_reliability: Optional[float] = None,
               half_life_seconds: Optional[float] = None, task_id: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None) -> RevisionResult:
        reliability = self.calibrator.reliability(source) if source_reliability is None else source_reliability
        belief = self.beliefs.observe(subject, predicate, value, source=source, confidence=confidence,
                                      source_reliability=reliability, half_life_seconds=half_life_seconds,
                                      task_id=task_id, metadata=metadata)
        self._sync_hypotheses(subject, predicate, belief.evidence)
        ranked = self.hypotheses.rank(subject, predicate); best = ranked[0]
        return RevisionResult(subject, predicate, best.value, best.score,
                              tuple(h.value for h in ranked[1:]), tuple(h.value for h in ranked[1:] if h.score > 0.2))

    def inspect(self, subject: str, predicate: str) -> Optional[RevisionResult]:
        belief = self.beliefs.refresh(subject, predicate)
        if belief is None: return None
        self._sync_hypotheses(subject, predicate, belief.evidence)
        ranked = self.hypotheses.rank(subject, predicate)
        if not ranked: return None
        best = ranked[0]
        return RevisionResult(subject, predicate, best.value, best.score,
                              tuple(h.value for h in ranked[1:]), tuple(h.value for h in ranked[1:] if h.score > 0.2))

    def record_outcome(self, source: str, correct: bool) -> float:
        return self.calibrator.record(source, correct)
