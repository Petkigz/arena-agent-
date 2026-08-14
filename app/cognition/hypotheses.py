"""Competing hypotheses for evidence-driven reasoning."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Hypothesis:
    subject: str
    predicate: str
    value: Any
    score: float = 0.5
    rationale: List[str] = field(default_factory=list)
    hypothesis_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.score = max(0.0, min(1.0, self.score))

class HypothesisSet:
    """Keeps alternatives alive instead of collapsing uncertainty into one fact."""
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], list[Hypothesis]] = {}

    def add(self, hypothesis: Hypothesis) -> Hypothesis:
        key = (hypothesis.subject, hypothesis.predicate)
        self._items.setdefault(key, []).append(hypothesis)
        return hypothesis

    def upsert(self, subject: str, predicate: str, value: Any, score: float = 0.5, rationale: Optional[str] = None) -> Hypothesis:
        key = (subject, predicate)
        existing = next((h for h in self._items.get(key, []) if h.value == value), None)
        if existing is None:
            existing = self.add(Hypothesis(subject, predicate, value, score))
        else:
            existing.score = max(0.0, min(1.0, score))
            existing.updated_at = _now()
        if rationale:
            existing.rationale.append(rationale)
        return existing

    def rank(self, subject: str, predicate: str) -> list[Hypothesis]:
        return sorted(self._items.get((subject, predicate), []), key=lambda h: h.score, reverse=True)

    def best(self, subject: str, predicate: str) -> Optional[Hypothesis]:
        ranked = self.rank(subject, predicate)
        return ranked[0] if ranked else None

    def alternatives(self, subject: str, predicate: str) -> list[Hypothesis]:
        return self.rank(subject, predicate)[1:]
