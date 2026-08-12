"""Phase 3: evidence-backed beliefs and belief revision."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Evidence:
    source: str
    value: Any
    confidence: float = 1.0
    observed_at: str = field(default_factory=_now)
    evidence_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass
class Belief:
    subject: str
    predicate: str
    value: Any
    confidence: float
    evidence: List[Evidence] = field(default_factory=list)
    belief_id: str = field(default_factory=lambda: uuid4().hex)
    updated_at: str = field(default_factory=_now)


class BeliefStore:
    """Small in-memory belief layer; persistence can be added after its semantics stabilize."""

    def __init__(self) -> None:
        self._beliefs: Dict[tuple[str, str], Belief] = {}

    def observe(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0) -> Belief:
        evidence = Evidence(source=source, value=value, confidence=confidence)
        key = (subject, predicate)
        current = self._beliefs.get(key)
        if current is None:
            belief = Belief(subject, predicate, value, confidence, [evidence])
            self._beliefs[key] = belief
            return belief

        current.evidence.append(evidence)
        current.updated_at = _now()
        # Stronger evidence can revise a belief; weak contradictory evidence
        # should reduce confidence rather than immediately flip the belief.
        if value == current.value:
            current.confidence = min(1.0, current.confidence + (1.0 - current.confidence) * confidence * 0.5)
        elif confidence > current.confidence:
            current.value = value
            current.confidence = confidence
        else:
            current.confidence = max(0.0, current.confidence - confidence * 0.25)
        return current

    def get(self, subject: str, predicate: str) -> Optional[Belief]:
        return self._beliefs.get((subject, predicate))

    def list(self, subject: Optional[str] = None) -> List[Belief]:
        values = list(self._beliefs.values())
        if subject is not None:
            values = [belief for belief in values if belief.subject == subject]
        return values

    def contradictions(self, subject: Optional[str] = None) -> List[Dict[str, Any]]:
        result = []
        for belief in self.list(subject):
            values = {repr(item.value) for item in belief.evidence}
            if len(values) > 1:
                result.append({"belief": belief, "values": values})
        return result
