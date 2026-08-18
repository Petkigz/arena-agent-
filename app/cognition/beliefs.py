"""Phase 3: evidence-backed beliefs and belief revision."""

from __future__ import annotations

import sqlite3
import json
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
    """Belief layer with optional SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._beliefs: Dict[tuple[str, str], Belief] = {}
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS persistent_beliefs (
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (subject, predicate)
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT subject, predicate, value, confidence, evidence, updated_at FROM persistent_beliefs")
        rows = cursor.fetchall()
        for s, p, v, conf, ev_json, updated in rows:
            try:
                val = json.loads(v)
            except Exception:
                val = v

            ev_list = []
            if ev_json:
                try:
                    ev_items = json.loads(ev_json)
                    for item in ev_items:
                        ev_list.append(Evidence(
                            source=item.get("source", "system"),
                            value=item.get("value"),
                            confidence=item.get("confidence", 1.0),
                            observed_at=item.get("observed_at", updated),
                            evidence_id=item.get("evidence_id", uuid4().hex)
                        ))
                except Exception:
                    pass

            b = Belief(s, p, val, conf, evidence=ev_list, updated_at=updated)
            self._beliefs[(s, p)] = b
        conn.close()

    def _save_to_db(self, belief: Belief) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        val_str = json.dumps(belief.value) if not isinstance(belief.value, str) else belief.value
        ev_json = json.dumps([
            {
                "source": e.source,
                "value": e.value,
                "confidence": e.confidence,
                "observed_at": e.observed_at,
                "evidence_id": e.evidence_id
            } for e in belief.evidence
        ])
        cursor.execute("""
            INSERT OR REPLACE INTO persistent_beliefs (subject, predicate, value, confidence, evidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (belief.subject, belief.predicate, val_str, belief.confidence, ev_json, belief.updated_at))
        conn.commit()
        conn.close()

    def observe(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0) -> Belief:
        evidence = Evidence(source=source, value=value, confidence=confidence)
        key = (subject, predicate)
        current = self._beliefs.get(key)
        if current is None:
            belief = Belief(subject, predicate, value, confidence, [evidence])
            self._beliefs[key] = belief
            self._save_to_db(belief)
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

        self._save_to_db(current)
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
