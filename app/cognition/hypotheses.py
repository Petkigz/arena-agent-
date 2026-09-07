"""Bounded competing hypotheses for evidence-driven reasoning.

Hypotheses are candidate explanations, not environmental facts.  The set is
bounded so repeated claims cannot grow unbounded state or crowd out competing
explanations.  It deliberately exposes alternatives without synthesizing them
into a compromise; authoritative beliefs remain owned by ``BeliefStore``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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
        self.score = max(0.0, min(1.0, float(self.score)))


class HypothesisSet:
    """Keep a small ranked set of alternatives without premature synthesis."""

    DEFAULT_MAX_HYPOTHESES = 4

    def __init__(self, max_hypotheses: int = DEFAULT_MAX_HYPOTHESES) -> None:
        try:
            limit = int(max_hypotheses)
        except (TypeError, ValueError):
            limit = self.DEFAULT_MAX_HYPOTHESES
        self.max_hypotheses = max(1, limit)
        self._items: dict[tuple[str, str], list[Hypothesis]] = {}

    @staticmethod
    def _rank_key(hypothesis: Hypothesis) -> tuple[float, str, str, str]:
        # Score is primary; timestamps and ID make equal-score pruning
        # deterministic without treating the newest claim as authoritative.
        return (
            float(hypothesis.score),
            str(hypothesis.updated_at),
            str(hypothesis.created_at),
            str(hypothesis.hypothesis_id),
        )

    def _prune(self, key: tuple[str, str]) -> None:
        items = self._items.get(key, [])
        if len(items) <= self.max_hypotheses:
            return
        self._items[key] = sorted(items, key=self._rank_key, reverse=True)[: self.max_hypotheses]

    def add(self, hypothesis: Hypothesis) -> Hypothesis:
        key = (hypothesis.subject, hypothesis.predicate)
        self._items.setdefault(key, []).append(hypothesis)
        self._prune(key)
        return hypothesis

    def upsert(
        self,
        subject: str,
        predicate: str,
        value: Any,
        score: float = 0.5,
        rationale: Optional[str] = None,
    ) -> Hypothesis:
        key = (subject, predicate)
        existing = next((h for h in self._items.get(key, []) if h.value == value), None)
        if existing is None:
            existing = self.add(Hypothesis(subject, predicate, value, score))
        else:
            existing.score = max(0.0, min(1.0, float(score)))
            existing.updated_at = _now()
        if rationale and rationale not in existing.rationale:
            existing.rationale.append(rationale)
        self._prune(key)
        return existing

    def rank(self, subject: str, predicate: str) -> list[Hypothesis]:
        return sorted(
            self._items.get((subject, predicate), []),
            key=self._rank_key,
            reverse=True,
        )

    def best(self, subject: str, predicate: str) -> Optional[Hypothesis]:
        ranked = self.rank(subject, predicate)
        return ranked[0] if ranked else None

    def alternatives(self, subject: str, predicate: str) -> list[Hypothesis]:
        return self.rank(subject, predicate)[1:]

    def snapshot(self, subject: str, predicate: str) -> Dict[str, Any]:
        """Return bounded, provenance-labelled hypothesis state for telemetry.

        The ``competing`` flag only means that distinct candidate values are
        retained for the same subject/predicate. It is not a claim that either
        value is true, and it never enters the authoritative belief store.
        """
        ranked = self.rank(subject, predicate)
        values: list[Any] = []
        items: list[Dict[str, Any]] = []
        for hypothesis in ranked:
            if hypothesis.value not in values:
                values.append(hypothesis.value)
            items.append({
                "hypothesis_id": hypothesis.hypothesis_id,
                "subject": hypothesis.subject,
                "predicate": hypothesis.predicate,
                "value": hypothesis.value,
                "score": round(float(hypothesis.score), 6),
                "rationale": list(hypothesis.rationale),
                "created_at": hypothesis.created_at,
                "updated_at": hypothesis.updated_at,
                "epistemic_status": "hypothesis",
            })
        return {
            "subject": subject,
            "predicate": predicate,
            "items": items,
            "count": len(items),
            "max_hypotheses": self.max_hypotheses,
            "bounded": True,
            "competing": len(values) > 1,
            "epistemic_status": "hypothesis_set",
        }

    def all_for(self, subject: str, predicate: str) -> list[Hypothesis]:
        """Return a ranked copy, keeping callers from mutating internal state."""
        return list(self.rank(subject, predicate))
