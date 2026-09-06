"""Trace-linked usefulness feedback, kept separate from correctness.

A correct answer can be unhelpful, and an incomplete answer can still be useful
if it is honestly scoped. This store records explicit ratings and bounded
interaction signals without silently treating every follow-up as a negative
rating.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


SIGNAL_TYPES = frozenset({
    "explicit_rating",
    "task_completed",
    "follow_up_correction",
    "clarification_requested",
    "abandoned",
    "accepted_without_followup",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class UsefulnessFeedback:
    feedback_id: str
    trace_id: str
    signal_type: str
    value: float
    source: str
    note: str
    confidence_label: str
    evidence_state: str
    confidence_score: Optional[float]
    latency_ms: float
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UsefulnessFeedbackStore:
    """Append-only trace-linked usefulness events and bounded summaries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS usefulness_feedback (
                feedback_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                value REAL NOT NULL,
                source TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                confidence_label TEXT NOT NULL DEFAULT '',
                evidence_state TEXT NOT NULL DEFAULT '',
                confidence_score REAL,
                latency_ms REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL
            )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usefulness_trace "
                "ON usefulness_feedback(trace_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usefulness_label "
                "ON usefulness_feedback(confidence_label, signal_type)"
            )
            conn.commit()

    @staticmethod
    def _trace_context(conn: sqlite3.Connection, trace_id: str) -> Optional[Dict[str, Any]]:
        columns = {item[1] for item in conn.execute(
            "PRAGMA table_info(cognitive_traces)"
        ).fetchall()}
        required = {"trace_id", "latency_ms"}
        if not required.issubset(columns):
            return None
        optional = ", epistemic_presentation_json" if "epistemic_presentation_json" in columns else ""
        row = conn.execute(
            "SELECT trace_id, latency_ms" + optional +
            " FROM cognitive_traces WHERE trace_id=?",
            (trace_id,),
        ).fetchone()
        if not row:
            return None
        presentation: Dict[str, Any] = {}
        if optional:
            try:
                parsed = json.loads(row[2] or "{}")
                if isinstance(parsed, dict):
                    presentation = parsed
            except (TypeError, ValueError):
                pass
        return {
            "trace_id": row[0],
            "latency_ms": float(row[1] or 0.0),
            "epistemic_presentation": presentation,
        }

    def record(
        self,
        *,
        trace_id: str,
        signal_type: str,
        value: float,
        source: str = "owner",
        note: str = "",
    ) -> UsefulnessFeedback:
        signal_type = str(signal_type or "").strip().lower()
        if signal_type not in SIGNAL_TYPES:
            raise ValueError(f"Unknown usefulness signal_type: {signal_type}")
        value = max(0.0, min(1.0, float(value)))
        note = str(note or "")[:2000]
        with self._lock, sqlite3.connect(self.db_path) as conn:
            context = self._trace_context(conn, trace_id)
            if context is None:
                raise KeyError(f"Trace not found: {trace_id}")
            presentation = context["epistemic_presentation"]
            feedback = UsefulnessFeedback(
                feedback_id=f"use_{uuid4().hex[:14]}",
                trace_id=trace_id,
                signal_type=signal_type,
                value=round(value, 4),
                source=str(source or "owner")[:80],
                note=note,
                confidence_label=str(presentation.get("confidence_label") or ""),
                evidence_state=str(presentation.get("evidence_state") or ""),
                confidence_score=(
                    float(presentation["confidence_score"])
                    if presentation.get("confidence_score") is not None else None
                ),
                latency_ms=context["latency_ms"],
                created_at=_now(),
            )
            conn.execute(
                "INSERT INTO usefulness_feedback VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    feedback.feedback_id, feedback.trace_id, feedback.signal_type,
                    feedback.value, feedback.source, feedback.note,
                    feedback.confidence_label, feedback.evidence_state,
                    feedback.confidence_score, feedback.latency_ms,
                    feedback.created_at,
                ),
            )
            conn.commit()
        return feedback

    def record_rating(
        self,
        *,
        trace_id: str,
        rating: int,
        note: str = "",
    ) -> UsefulnessFeedback:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError("Usefulness rating must be an integer from 1 to 5")
        return self.record(
            trace_id=trace_id,
            signal_type="explicit_rating",
            value=(rating - 1) / 4.0,
            source="owner_explicit",
            note=note,
        )

    def list(self, trace_id: Optional[str] = None, limit: int = 200) -> List[UsefulnessFeedback]:
        query = "SELECT * FROM usefulness_feedback"
        params: List[Any] = []
        if trace_id:
            query += " WHERE trace_id=?"
            params.append(trace_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            UsefulnessFeedback(
                feedback_id=row[0], trace_id=row[1], signal_type=row[2],
                value=float(row[3]), source=row[4], note=row[5],
                confidence_label=row[6], evidence_state=row[7],
                confidence_score=float(row[8]) if row[8] is not None else None,
                latency_ms=float(row[9]), created_at=row[10],
            )
            for row in rows
        ]

    def summary(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT signal_type, confidence_label, evidence_state, value "
                "FROM usefulness_feedback"
            ).fetchall()
        def aggregate(items: List[tuple[Any, ...]]) -> Dict[str, Any]:
            if not items:
                return {"samples": 0, "mean_usefulness": None}
            return {
                "samples": len(items),
                "mean_usefulness": round(sum(float(item[-1]) for item in items) / len(items), 4),
            }
        by_label: Dict[str, List[tuple[Any, ...]]] = {}
        by_signal: Dict[str, List[tuple[Any, ...]]] = {}
        for row in rows:
            by_label.setdefault(str(row[1] or "unknown"), []).append(row)
            by_signal.setdefault(str(row[0]), []).append(row)
        return {
            "samples": len(rows),
            "overall": aggregate(rows),
            "by_confidence_label": {
                key: aggregate(value) for key, value in sorted(by_label.items())
            },
            "by_signal_type": {
                key: aggregate(value) for key, value in sorted(by_signal.items())
            },
            "note": (
                "Usefulness signals are observational feedback, not correctness "
                "labels or proof of user intent."
            ),
        }
