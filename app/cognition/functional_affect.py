"""Bounded functional affect telemetry, not subjective emotion.

The vector is a decaying control signal derived only from explicit execution,
load, and evidence events. Effects are advisory, capped, and auditable; this
module does not claim feelings, intrinsic care, or authority to act.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

AFFECT_FIELDS = ("confidence", "load", "frustration", "engagement", "uncertainty")
SIGNAL_FIELDS = frozenset(AFFECT_FIELDS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 6)


@dataclass(frozen=True)
class AffectVector:
    confidence: float = 0.5
    load: float = 0.0
    frustration: float = 0.0
    engagement: float = 0.5
    uncertainty: float = 0.5
    updated_at: str = ""
    revision: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FunctionalAffectError(ValueError):
    """Invalid or unverifiable functional-affect update."""


class FunctionalAffectStore:
    """Persistent decaying vector with bounded advisory modifiers."""

    STORAGE_SCHEMA_VERSION = 1
    HALF_LIFE_HOURS = 6.0
    BASELINE = {
        "confidence": 0.5,
        "load": 0.0,
        "frustration": 0.0,
        "engagement": 0.5,
        "uncertainty": 0.5,
    }

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS affect_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                    storage_schema_version INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    revision INTEGER NOT NULL
                )
            """)
            row = conn.execute(
                "SELECT storage_schema_version FROM affect_meta WHERE singleton=1"
            ).fetchone()
            if row is None:
                vector = AffectVector(updated_at=_now()).to_dict()
                conn.execute(
                    "INSERT INTO affect_meta VALUES (1, ?, ?, ?, 0)",
                    (self.STORAGE_SCHEMA_VERSION, json.dumps(vector, sort_keys=True), vector["updated_at"]),
                )
            elif int(row[0]) != self.STORAGE_SCHEMA_VERSION:
                raise FunctionalAffectError(
                    f"unsupported functional affect schema_version={row[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}"
                )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS affect_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    field_name TEXT,
                    delta REAL,
                    vector_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    trace_id TEXT,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS affect_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    modifiers_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def _decay_value(value: float, field_name: str, elapsed_hours: float) -> float:
        baseline = FunctionalAffectStore.BASELINE[field_name]
        factor = math.exp(-math.log(2.0) * max(0.0, elapsed_hours) / FunctionalAffectStore.HALF_LIFE_HOURS)
        return _clamp(baseline + (float(value) - baseline) * factor)

    def _read(self) -> AffectVector:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT vector_json, updated_at, revision FROM affect_meta WHERE singleton=1"
            ).fetchone()
        if row is None:
            raise FunctionalAffectError("functional affect vector is missing")
        try:
            raw = json.loads(row[0])
            values = {field: _clamp(float(raw.get(field, self.BASELINE[field]))) for field in AFFECT_FIELDS}
            updated = str(row[1])
            previous = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            elapsed = max(0.0, (datetime.now(timezone.utc) - previous.astimezone(timezone.utc)).total_seconds() / 3600.0)
            values = {field: self._decay_value(values[field], field, elapsed) for field in AFFECT_FIELDS}
            return AffectVector(**values, updated_at=_now(), revision=int(row[2]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FunctionalAffectError(f"functional affect vector is invalid: {exc}") from exc

    def snapshot(self) -> AffectVector:
        with self._lock:
            vector = self._read()
            return self._persist(vector, event=None)

    def _persist(self, vector: AffectVector, *, event: Optional[Dict[str, Any]]) -> AffectVector:
        with sqlite3.connect(self.db_path) as conn:
            current = conn.execute("SELECT revision FROM affect_meta WHERE singleton=1").fetchone()
            revision = int(current[0]) + 1 if current else vector.revision
            stored = AffectVector(
                confidence=vector.confidence, load=vector.load, frustration=vector.frustration,
                engagement=vector.engagement, uncertainty=vector.uncertainty,
                updated_at=vector.updated_at or _now(), revision=revision,
            )
            conn.execute(
                "UPDATE affect_meta SET vector_json=?, updated_at=?, revision=? WHERE singleton=1",
                (json.dumps(stored.to_dict(), sort_keys=True), stored.updated_at, revision),
            )
            if event is not None:
                conn.execute(
                    "INSERT INTO affect_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"affect_event_{uuid4().hex[:16]}", event["event_type"], event.get("field_name"),
                        event.get("delta"), json.dumps(stored.to_dict(), sort_keys=True), event["source"],
                        event.get("trace_id"), json.dumps(event["evidence_ids"]), _now(),
                    ),
                )
            conn.commit()
        return stored

    def apply_signal(
        self,
        field_name: str,
        delta: float,
        *,
        source: str,
        trace_id: str,
        evidence_ids: Iterable[str],
    ) -> AffectVector:
        if field_name not in SIGNAL_FIELDS:
            raise FunctionalAffectError(f"unsupported affect field: {field_name}")
        if not source or not trace_id:
            raise FunctionalAffectError("affect signals require source and trace_id")
        evidence = [str(item) for item in evidence_ids if str(item).strip()]
        if not evidence:
            raise FunctionalAffectError("affect signals require evidence_ids")
        try:
            delta = float(delta)
        except (TypeError, ValueError) as exc:
            raise FunctionalAffectError("affect delta must be numeric") from exc
        if not math.isfinite(delta) or not -1.0 <= delta <= 1.0:
            raise FunctionalAffectError("affect delta must be finite and in [-1, 1]")
        with self._lock:
            current = self._read()
            values = current.to_dict()
            values[field_name] = _clamp(values[field_name] + delta)
            vector = AffectVector(
                **{field: values[field] for field in AFFECT_FIELDS},
                updated_at=_now(), revision=current.revision,
            )
            return self._persist(vector, event={
                "event_type": "signal", "field_name": field_name, "delta": delta,
                "source": source, "trace_id": trace_id, "evidence_ids": evidence,
            })

    def advisory_modifiers(self) -> Dict[str, Any]:
        """Return capped, non-authoritative effects for routing/style telemetry."""
        vector = self.snapshot()
        clarification = _clamp(1.0 + 0.15 * vector.uncertainty + 0.10 * vector.frustration)
        exploration = _clamp(1.0 + 0.10 * vector.engagement - 0.15 * vector.load)
        reasoning = _clamp(1.0 + 0.10 * vector.uncertainty - 0.10 * vector.load)
        style = "concise" if vector.load >= 0.75 else "standard"
        return {
            "clarification_multiplier": clarification,
            "exploration_multiplier": exploration,
            "reasoning_budget_multiplier": reasoning,
            "response_style": style,
            "vector": vector.to_dict(),
            "bounded": True,
            "advisory_only": True,
            "authority": "none",
        }

    def record_outcome(
        self,
        *,
        trace_id: str,
        outcome: str,
        evidence_ids: Iterable[str],
    ) -> Dict[str, Any]:
        if not trace_id or not outcome:
            raise FunctionalAffectError("affect outcome requires trace_id and outcome")
        evidence = [str(item) for item in evidence_ids if str(item).strip()]
        if not evidence:
            raise FunctionalAffectError("affect outcome requires evidence_ids")
        modifiers = self.advisory_modifiers()
        outcome_id = f"affect_outcome_{uuid4().hex[:16]}"
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO affect_outcomes VALUES (?, ?, ?, ?, ?, ?)",
                (outcome_id, trace_id, str(outcome), json.dumps(modifiers, sort_keys=True), json.dumps(evidence), _now()),
            )
            conn.commit()
        return {
            "outcome_id": outcome_id,
            "trace_id": trace_id,
            "outcome": outcome,
            "modifiers": modifiers,
            "evidence_ids": evidence,
            "affect_is_not_causal_proof": True,
        }

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, field_name, delta, vector_json, source, trace_id, evidence_json, created_at "
                "FROM affect_events ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "event_id": row[0], "event_type": row[1], "field_name": row[2], "delta": row[3],
                "vector": json.loads(row[4]), "source": row[5], "trace_id": row[6],
                "evidence_ids": json.loads(row[7]), "created_at": row[8],
            }
            for row in rows
        ]
