"""Owner-correction telemetry kept separate from correctness and training state.

A correction is an owner-provided learning signal, not proof that the corrected
answer is true.  This store records when the signal was received, which durable
trace it refers to, and whether the linked strategy update stayed local or
became eligible for repeated-evidence influence.  Latency is explicitly a
trace-created-at to correction-received proxy; it is not a claim about human
reaction time or end-to-end response quality.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class CorrectionEvent:
    correction_id: str
    trace_id: str
    correction_type: str
    expected_effect: str
    strategy_applied: bool
    strategy_generalized: bool
    correction_count: int
    adjustment_factor: Optional[float]
    source_created_at: Optional[str]
    received_at: str
    latency_ms: Optional[float]
    latency_basis: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorrectionSummary:
    total_corrections: int
    trace_linked_corrections: int
    measured_latency_count: int
    mean_latency_ms: Optional[float]
    strategy_update_count: int
    generalized_update_count: int
    correction_types: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CorrectionMeasurementStore:
    """Persist owner-correction measurements without changing execution truth."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        *,
        trace_db_path: Optional[str | Path] = None,
    ) -> None:
        self.db_path = str(db_path or settings.DB_PATH)
        self.trace_db_path = str(trace_db_path or self.db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS correction_events (
                    correction_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL DEFAULT '',
                    correction_type TEXT NOT NULL,
                    expected_effect TEXT NOT NULL DEFAULT '',
                    strategy_applied INTEGER NOT NULL DEFAULT 0,
                    strategy_generalized INTEGER NOT NULL DEFAULT 0,
                    correction_count INTEGER NOT NULL DEFAULT 0,
                    adjustment_factor REAL,
                    source_created_at TEXT,
                    received_at TEXT NOT NULL,
                    latency_ms REAL,
                    latency_basis TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_correction_events_trace "
                "ON correction_events(trace_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_correction_events_received "
                "ON correction_events(received_at)"
            )
            conn.commit()

    def _trace_created_at(self, trace_id: str) -> Optional[str]:
        if not trace_id:
            return None
        path = Path(self.trace_db_path)
        if not path.exists():
            return None
        try:
            with sqlite3.connect(path) as conn:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(cognitive_traces)").fetchall()
                }
                if "trace_id" not in columns or "created_at" not in columns:
                    return None
                row = conn.execute(
                    "SELECT created_at FROM cognitive_traces WHERE trace_id=?",
                    (str(trace_id),),
                ).fetchone()
            return str(row[0]) if row and row[0] else None
        except sqlite3.Error:
            return None

    def record(
        self,
        *,
        trace_id: str = "",
        correction_type: str = "unspecified",
        expected_effect: str = "",
        strategy_update: Optional[Dict[str, Any]] = None,
        evidence: Optional[List[str]] = None,
        received_at: Optional[str] = None,
        source_created_at: Optional[str] = None,
    ) -> CorrectionEvent:
        """Record one correction signal and its bounded timing metadata."""
        update = dict(strategy_update or {})
        received = str(received_at or _now())
        source_created = source_created_at or self._trace_created_at(str(trace_id or ""))
        received_dt = _parse_timestamp(received)
        source_dt = _parse_timestamp(source_created) if source_created else None
        latency_ms: Optional[float] = None
        if received_dt is not None and source_dt is not None:
            latency_ms = round(max(0.0, (received_dt - source_dt).total_seconds() * 1000.0), 3)
        if source_created:
            latency_basis = "trace_created_at_to_correction_received"
        else:
            latency_basis = "unmeasured_no_trace_timestamp"
        event = CorrectionEvent(
            correction_id=f"correction_{uuid4().hex[:12]}",
            trace_id=str(trace_id or ""),
            correction_type=str(correction_type or "unspecified").strip().lower() or "unspecified",
            expected_effect=str(expected_effect or "")[:500],
            strategy_applied=bool(update.get("applied", False)),
            strategy_generalized=bool(update.get("generalized", False)),
            correction_count=int(update.get("correction_count", 0) or 0),
            adjustment_factor=(
                float(update["adjustment_factor"])
                if update.get("adjustment_factor") is not None else None
            ),
            source_created_at=source_created,
            received_at=received,
            latency_ms=latency_ms,
            latency_basis=latency_basis,
            evidence=[str(item)[:500] for item in (evidence or []) if str(item).strip()],
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO correction_events
                (correction_id, trace_id, correction_type, expected_effect,
                 strategy_applied, strategy_generalized, correction_count,
                 adjustment_factor, source_created_at, received_at, latency_ms,
                 latency_basis, evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.correction_id,
                    event.trace_id,
                    event.correction_type,
                    event.expected_effect,
                    int(event.strategy_applied),
                    int(event.strategy_generalized),
                    event.correction_count,
                    event.adjustment_factor,
                    event.source_created_at,
                    event.received_at,
                    event.latency_ms,
                    event.latency_basis,
                    json.dumps(event.evidence),
                ),
            )
            conn.commit()
        return event

    def history(self, limit: int = 100) -> List[CorrectionEvent]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT correction_id, trace_id, correction_type,
                    expected_effect, strategy_applied, strategy_generalized,
                    correction_count, adjustment_factor, source_created_at,
                    received_at, latency_ms, latency_basis, evidence_json
                    FROM correction_events ORDER BY received_at ASC LIMIT ?""",
                (max(1, min(int(limit), 5000)),),
            ).fetchall()
        return [
            CorrectionEvent(
                correction_id=row[0],
                trace_id=row[1],
                correction_type=row[2],
                expected_effect=row[3],
                strategy_applied=bool(row[4]),
                strategy_generalized=bool(row[5]),
                correction_count=int(row[6]),
                adjustment_factor=(float(row[7]) if row[7] is not None else None),
                source_created_at=row[8],
                received_at=row[9],
                latency_ms=(float(row[10]) if row[10] is not None else None),
                latency_basis=row[11],
                evidence=list(json.loads(row[12] or "[]")),
            )
            for row in rows
        ]

    def summary(self) -> CorrectionSummary:
        events = self.history(limit=5000)
        measured = [event.latency_ms for event in events if event.latency_ms is not None]
        type_counts: Dict[str, int] = {}
        for event in events:
            type_counts[event.correction_type] = type_counts.get(event.correction_type, 0) + 1
        return CorrectionSummary(
            total_corrections=len(events),
            trace_linked_corrections=sum(bool(event.trace_id) for event in events),
            measured_latency_count=len(measured),
            mean_latency_ms=(round(sum(measured) / len(measured), 3) if measured else None),
            strategy_update_count=sum(event.strategy_applied for event in events),
            generalized_update_count=sum(event.strategy_generalized for event in events),
            correction_types=type_counts,
        )
