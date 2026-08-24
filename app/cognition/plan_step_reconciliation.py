"""Reconciliation outcomes applied to exact reviewed plan steps.

Preemption reconciliation verifies what the interrupted execution actually
achieved. Until now the recommendation (skip / wait / replan) was recorded but
never applied to the plan step itself, so a resumed plan could re-execute work
that had already completed — repeating real side effects.

This store binds each reconciliation outcome to an exact reviewed step and maps
it to a step status that the executor consults on resume:

  skip_verified_step_and_review_next → completed (verified; never re-executed)
  wait_for_evidence                  → unknown_pending_evidence (halt; re-observe)
  create_fresh_replan                → needs_fresh_replan (halt; new revision)

Honesty rules:
  * Only verification evidence can mark a step completed; a completed record is
    never downgraded — a contradicting later observation is kept in history and
    the conflict is surfaced instead of silently flipping the status.
  * `unknown` stays `unknown_pending_evidence`; it never becomes completed or
    failed by inference.
  * The owner-approved review snapshot is never mutated; these records live
    beside it and reference the snapshot's step ids.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


STATUS_COMPLETED = "completed"
STATUS_UNKNOWN_PENDING_EVIDENCE = "unknown_pending_evidence"
STATUS_NEEDS_FRESH_REPLAN = "needs_fresh_replan"

_RECOMMENDATION_STATUS = {
    "skip_verified_step_and_review_next": STATUS_COMPLETED,
    "wait_for_evidence": STATUS_UNKNOWN_PENDING_EVIDENCE,
    "create_fresh_replan": STATUS_NEEDS_FRESH_REPLAN,
}


@dataclass
class StepReconciliationRecord:
    step_id: str
    plan_id: str
    action_type: str
    status: str
    recommendation: str
    preemption_id: str
    execution_id: str
    goal_verified: bool
    verification_unknown: bool
    evidence: Dict[str, Any] = field(default_factory=dict)
    conflict: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    recorded_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PlanStepReconciliationStore:
    """SQLite store of reconciliation outcomes per reviewed plan step."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "plan_step_reconciliations.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS plan_step_reconciliations (
                step_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                preemption_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                goal_verified INTEGER NOT NULL,
                verification_unknown INTEGER NOT NULL,
                evidence_json TEXT NOT NULL,
                conflict TEXT,
                history_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )""")
            conn.commit()

    def _row(self, row: sqlite3.Row) -> StepReconciliationRecord:
        return StepReconciliationRecord(
            step_id=row[0], plan_id=row[1], action_type=row[2], status=row[3],
            recommendation=row[4], preemption_id=row[5], execution_id=row[6],
            goal_verified=bool(row[7]), verification_unknown=bool(row[8]),
            evidence=json.loads(row[9]), conflict=row[10],
            history=json.loads(row[11]), recorded_at=row[12],
        )

    def _save(self, record: StepReconciliationRecord) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO plan_step_reconciliations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.step_id, record.plan_id, record.action_type, record.status,
                    record.recommendation, record.preemption_id, record.execution_id,
                    int(record.goal_verified), int(record.verification_unknown),
                    json.dumps(record.evidence, default=str), record.conflict,
                    json.dumps(record.history, default=str), record.recorded_at,
                ),
            )
            conn.commit()

    def apply(
        self,
        plan_id: str,
        step: Dict[str, Any],
        recommendation: str,
        *,
        verification: Dict[str, Any],
        preemption_id: str,
        execution_id: str,
    ) -> StepReconciliationRecord:
        """Apply one reconciliation recommendation to an exact reviewed step."""
        status = _RECOMMENDATION_STATUS.get(recommendation)
        if status is None:
            raise ValueError(f"Unknown reconciliation recommendation: {recommendation}")
        step_id = str(step.get("step_id") or "")
        if not step_id:
            raise ValueError("Step binding requires an exact reviewed step_id")
        with self._lock:
            existing = self.get(step_id)
            record = StepReconciliationRecord(
                step_id=step_id,
                plan_id=str(plan_id),
                action_type=str(step.get("action_type") or ""),
                status=status,
                recommendation=recommendation,
                preemption_id=str(preemption_id),
                execution_id=str(execution_id),
                goal_verified=bool(verification.get("goal_verified")),
                verification_unknown=bool(verification.get("verification_unknown")),
                evidence=dict(verification),
                recorded_at=_now(),
            )
            if existing is not None:
                record.history = existing.history + [existing.to_dict()]
                if existing.status == STATUS_COMPLETED and status != STATUS_COMPLETED:
                    # A verified completion is never silently downgraded; the
                    # contradiction is recorded and surfaced.
                    record.status = STATUS_COMPLETED
                    record.conflict = (
                        f"Later reconciliation recommended '{recommendation}' after this step was "
                        "already verified completed; keeping verified completion and recording the conflict."
                    )
                    audit_logger.warning(
                        f"Step {step_id}: conflicting reconciliation '{recommendation}' after verified completion"
                    )
                    app_logger.warning(record.conflict)
            self._save(record)
            audit_logger.info(
                f"Step {step_id} reconciliation applied: {record.status} "
                f"(preemption {preemption_id}, execution {execution_id})"
            )
            return self.get(step_id) or record

    def get(self, step_id: str) -> Optional[StepReconciliationRecord]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM plan_step_reconciliations WHERE step_id=?", (step_id,)
            ).fetchone()
        return self._row(row) if row else None

    def for_plan(self, plan_id: str) -> List[StepReconciliationRecord]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM plan_step_reconciliations WHERE plan_id=? ORDER BY recorded_at ASC",
                (str(plan_id),),
            ).fetchall()
        return [self._row(r) for r in rows]


# Module-level singleton, mirroring plan_review_store.
plan_step_reconciliation_store = PlanStepReconciliationStore()
