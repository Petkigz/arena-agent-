"""Owner correction handling and evidence-linked strategy revision.

This is the runtime correction loop, distinct from the owner-reviewed LoRA
candidate endpoint. A correction first preserves the original trace, then
records the owner's correction as inadmissible owner evidence, optionally
updates a hypothesis, and only generalizes to strategy selection after
repeated corrections.

A single correction changes the current interpretation but does not globally
rewrite behavior. Repeated corrections can lower the historical utility of the
strategy that produced the error.
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

from app.cognition.source_types import SourceType
from app.utils.logger import app_logger, audit_logger


ERROR_TYPES = frozenset({
    "factual",
    "intent",
    "retrieval",
    "routing",
    "procedural",
    "tone",
    "other",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class UserCorrection:
    correction_id: str
    trace_id: str
    session_id: str
    request: str
    original_response: str
    correction: str
    error_type: str
    subject: str
    predicate: str
    corrected_value: Any
    action_type: str
    goal_type: str
    strategy_revision_status: str
    strategy_revision_count: int
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CorrectionStore:
    """SQLite store for immutable owner corrections and revision counts."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS user_corrections (
                correction_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                request TEXT NOT NULL,
                original_response TEXT NOT NULL,
                correction TEXT NOT NULL,
                error_type TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                predicate TEXT NOT NULL DEFAULT '',
                corrected_value_json TEXT,
                action_type TEXT NOT NULL DEFAULT '',
                goal_type TEXT NOT NULL DEFAULT '',
                strategy_revision_status TEXT NOT NULL,
                strategy_revision_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS correction_strategy_revisions (
                revision_key TEXT PRIMARY KEY,
                goal_type TEXT NOT NULL,
                action_type TEXT NOT NULL,
                error_type TEXT NOT NULL,
                correction_count INTEGER NOT NULL,
                last_correction_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_corrections_trace ON user_corrections(trace_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_corrections_strategy "
                "ON correction_strategy_revisions(goal_type, action_type, error_type)"
            )
            conn.commit()

    @staticmethod
    def _row(row: tuple[Any, ...]) -> UserCorrection:
        return UserCorrection(
            correction_id=row[0], trace_id=row[1], session_id=row[2],
            request=row[3], original_response=row[4], correction=row[5],
            error_type=row[6], subject=row[7], predicate=row[8],
            corrected_value=json.loads(row[9]) if row[9] is not None else None,
            action_type=row[10], goal_type=row[11],
            strategy_revision_status=row[12], strategy_revision_count=int(row[13]),
            created_at=row[14],
        )

    def trace_snapshot(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Read the original trace facts; never reconstruct them from prose."""
        with sqlite3.connect(self.db_path) as conn:
            columns = {item[1] for item in conn.execute(
                "PRAGMA table_info(cognitive_traces)"
            ).fetchall()}
            if not columns:
                return None
            required = {"trace_id", "session_id", "user_input", "assistant_reply"}
            if not required.issubset(columns):
                return None
            has_presentation = "epistemic_presentation_json" in columns
            presentation_column = ", epistemic_presentation_json" if has_presentation else ""
            row = conn.execute(
                "SELECT trace_id, session_id, user_input, assistant_reply, "
                "actions_json, model_used, goal_verified"
                f"{presentation_column} FROM cognitive_traces WHERE trace_id=?",
                (trace_id,),
            ).fetchone()
        if not row:
            return None
        actions = []
        try:
            actions = json.loads(row[4] or "[]")
        except (TypeError, ValueError):
            actions = []
        presentation = {}
        if has_presentation and len(row) > 7:
            try:
                presentation = json.loads(row[7] or "{}")
            except (TypeError, ValueError):
                presentation = {}
        return {
            "trace_id": row[0],
            "session_id": row[1],
            "request": row[2],
            "original_response": row[3],
            "actions": actions,
            "model_used": row[5],
            "goal_verified": bool(row[6]),
            "epistemic_presentation": presentation,
        }

    def _next_strategy_count(self, goal_type: str, action_type: str, error_type: str) -> int:
        key = _strategy_key(goal_type, action_type, error_type)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT correction_count FROM correction_strategy_revisions WHERE revision_key=?",
                (key,),
            ).fetchone()
        return int(row[0]) + 1 if row else 1

    def record(
        self,
        *,
        trace: Dict[str, Any],
        correction: str,
        error_type: str,
        subject: str = "",
        predicate: str = "",
        corrected_value: Any = None,
        action_type: str = "",
        goal_type: str = "",
    ) -> UserCorrection:
        correction = str(correction or "").strip()
        if len(correction) < 2:
            raise ValueError("Correction must contain at least 2 characters")
        error_type = str(error_type or "other").strip().lower()
        if error_type not in ERROR_TYPES:
            raise ValueError(f"Unknown correction error_type: {error_type}")
        count = self._next_strategy_count(goal_type, action_type, error_type)
        status = (
            "current_only"
            if count < 2 or not action_type or not goal_type
            else "strategy_deprioritized_after_repeated_corrections"
        )
        record = UserCorrection(
            correction_id=f"corr_{uuid4().hex[:14]}",
            trace_id=str(trace["trace_id"]),
            session_id=str(trace.get("session_id") or ""),
            request=str(trace.get("request") or "")[:8000],
            original_response=str(trace.get("original_response") or "")[:12000],
            correction=correction[:8000],
            error_type=error_type,
            subject=str(subject or "")[:240],
            predicate=str(predicate or "")[:240],
            corrected_value=corrected_value,
            action_type=str(action_type or "")[:160],
            goal_type=str(goal_type or "")[:160],
            strategy_revision_status=status,
            strategy_revision_count=count,
            created_at=_now(),
        )
        key = _strategy_key(record.goal_type, record.action_type, record.error_type)
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO user_corrections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.correction_id, record.trace_id, record.session_id,
                    record.request, record.original_response, record.correction,
                    record.error_type, record.subject, record.predicate,
                    json.dumps(record.corrected_value, default=str)
                    if record.corrected_value is not None else None,
                    record.action_type, record.goal_type,
                    record.strategy_revision_status, record.strategy_revision_count,
                    record.created_at,
                ),
            )
            if record.action_type and record.goal_type:
                conn.execute(
                    "INSERT OR REPLACE INTO correction_strategy_revisions "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        key, record.goal_type, record.action_type, record.error_type,
                        count, record.correction_id, record.created_at,
                    ),
                )
            conn.commit()
        audit_logger.info(
            "Owner correction recorded: %s trace=%s type=%s strategy=%s count=%s",
            record.correction_id, record.trace_id, record.error_type,
            record.strategy_revision_status, record.strategy_revision_count,
        )
        return record

    def list(self, trace_id: Optional[str] = None, limit: int = 100) -> List[UserCorrection]:
        query = "SELECT * FROM user_corrections"
        params: List[Any] = []
        if trace_id:
            query += " WHERE trace_id=?"
            params.append(trace_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row(row) for row in rows]


def _strategy_key(goal_type: str, action_type: str, error_type: str) -> str:
    return "|".join((str(goal_type or ""), str(action_type or ""), str(error_type or "other")))


class CorrectionHandler:
    """Apply an explicit owner correction without unsafe overgeneralization."""

    MIN_CORRECTIONS_FOR_STRATEGY_REVISION = 2

    def __init__(
        self,
        db_path: str | Path,
        *,
        belief_engine: Optional[Any] = None,
        strategy_store: Optional[Any] = None,
    ) -> None:
        self.store = CorrectionStore(db_path)
        self.belief_engine = belief_engine
        self.strategy_store = strategy_store

    def handle(
        self,
        *,
        trace_id: str,
        correction: str,
        error_type: str = "other",
        subject: str = "",
        predicate: str = "",
        corrected_value: Any = None,
        action_type: str = "",
        goal_type: str = "",
    ) -> Dict[str, Any]:
        trace = self.store.trace_snapshot(trace_id)
        if trace is None:
            raise KeyError(f"Trace not found: {trace_id}")
        record = self.store.record(
            trace=trace,
            correction=correction,
            error_type=error_type,
            subject=subject,
            predicate=predicate,
            corrected_value=corrected_value,
            action_type=action_type,
            goal_type=goal_type,
        )

        belief_update: Dict[str, Any] = {
            "applied": False,
            "reason": "No structured subject/predicate/value supplied",
        }
        if self.belief_engine is not None and subject and predicate and corrected_value is not None:
            try:
                revision = self.belief_engine.ingest(
                    subject=subject,
                    predicate=predicate,
                    value=corrected_value,
                    source=SourceType.USER_INPUT.value,
                    observation_type="self_reported",
                    confidence=1.0,
                    rationale=f"Explicit owner correction {record.correction_id}",
                )
                belief_update = {
                    "applied": True,
                    "kind": "hypothesis_update",
                    "authoritative_belief_unchanged": True,
                    "has_belief": revision.has_belief,
                    "hypothesis_value": revision.hypothesis_value,
                    "evidence_count": revision.evidence_count,
                }
            except Exception as exc:
                # The correction itself remains durable, but callers receive
                # actionable failure information rather than a false claim that
                # the belief update succeeded.
                app_logger.error("Correction belief update failed", exc_info=True)
                belief_update = {
                    "applied": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        strategy_update: Dict[str, Any] = {
            "applied": False,
            "reason": "No strategy key supplied",
        }
        if self.strategy_store is not None and action_type and goal_type:
            try:
                # A correction is a verified failure of the interpretation or
                # strategy from the owner's perspective. Existing strategy
                # calibration requires repeated samples before it changes
                # selection, which prevents one correction from global drift.
                self.strategy_store.record_outcome(
                    goal_type=goal_type,
                    action_type=action_type,
                    success=False,
                    latency_ms=0.0,
                    surprisal=1.0,
                    goal_text=f"Owner correction {record.correction_id}: {correction}",
                )
                score = self.strategy_store.score_strategy(goal_type, action_type)
                generalized = bool(
                    score is not None
                    and score.total_attempts >= self.MIN_CORRECTIONS_FOR_STRATEGY_REVISION
                    and record.strategy_revision_count >= self.MIN_CORRECTIONS_FOR_STRATEGY_REVISION
                )
                strategy_update = {
                    "applied": True,
                    "generalized": generalized,
                    "status": record.strategy_revision_status,
                    "correction_count": record.strategy_revision_count,
                    "strategy_attempts": score.total_attempts if score else 0,
                    "adjustment_factor": self.strategy_store.adjustment_factor(goal_type, action_type),
                }
            except Exception as exc:
                app_logger.error("Correction strategy update failed", exc_info=True)
                strategy_update = {
                    "applied": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "correction_id": record.correction_id,
                }

        return {
            "success": True,
            "correction": record.to_dict(),
            "original_trace": trace,
            "belief_update": belief_update,
            "strategy_update": strategy_update,
            "note": (
                "The immediate interpretation was corrected. Strategy behavior "
                "is generalized only after repeated corrections."
            ),
        }
