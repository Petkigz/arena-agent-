"""Cooperative cancellation registry and truthful rollback receipts."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_current_execution_id: ContextVar[Optional[str]] = ContextVar(
    "arena_current_execution_id", default=None
)


class ExecutionCancelled(RuntimeError):
    pass


@dataclass
class RollbackReceipt:
    receipt_id: str
    execution_id: str
    action_type: str
    supported: bool
    reason: str
    compensation_action: Optional[str] = None
    compensation_payload: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = True
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ControlledExecution:
    execution_id: str
    proposal_id: str
    action_type: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    cancel_requested: bool = False
    cancel_requested_at: Optional[str] = None
    cancellation_observed: bool = False
    rollback_receipt: Optional[RollbackReceipt] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["rollback_receipt"] = (
            self.rollback_receipt.to_dict() if self.rollback_receipt else None
        )
        return data


class ExecutionControlRegistry:
    """Thread-safe active execution registry backed by SQLite history."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "execution_control.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: Dict[str, ControlledExecution] = {}
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS controlled_executions (
                execution_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                cancel_requested INTEGER NOT NULL,
                cancel_requested_at TEXT,
                cancellation_observed INTEGER NOT NULL,
                rollback_receipt_json TEXT,
                note TEXT NOT NULL DEFAULT ''
            )""")
            conn.execute("""UPDATE controlled_executions
                SET status = 'interrupted', completed_at = ?,
                    note = CASE WHEN note = '' THEN 'Process restarted before completion' ELSE note END
                WHERE status = 'running'""", (_now(),))
            conn.commit()

    def _persist(self, record: ControlledExecution) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""INSERT OR REPLACE INTO controlled_executions VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                record.execution_id, record.proposal_id, record.action_type,
                record.status, record.started_at, record.completed_at,
                int(record.cancel_requested), record.cancel_requested_at,
                int(record.cancellation_observed),
                json.dumps(record.rollback_receipt.to_dict())
                if record.rollback_receipt else None,
                record.note,
            ))
            conn.commit()

    def begin(self, proposal_id: str, action_type: str) -> ControlledExecution:
        record = ControlledExecution(
            execution_id=f"exec_{uuid4().hex[:16]}",
            proposal_id=proposal_id,
            action_type=action_type,
            status="running",
            started_at=_now(),
        )
        with self._lock:
            self._records[record.execution_id] = record
            self._persist(record)
        audit_logger.info(
            f"Controlled execution started: {record.execution_id} action={action_type}"
        )
        return record

    @contextmanager
    def scope(self, execution_id: str):
        token = _current_execution_id.set(execution_id)
        try:
            yield
        finally:
            _current_execution_id.reset(token)

    def request_cancel(self, execution_id: str) -> Optional[ControlledExecution]:
        with self._lock:
            record = self._records.get(execution_id)
            if record is None:
                record = self.get(execution_id)
                if record is None:
                    return None
                self._records[execution_id] = record
            if record.status != "running":
                return record
            record.cancel_requested = True
            record.cancel_requested_at = _now()
            record.note = "Owner requested cooperative cancellation"
            self._persist(record)
            audit_logger.warning(f"Cancellation requested: {execution_id}")
            return record

    def is_cancel_requested(self, execution_id: Optional[str] = None) -> bool:
        execution_id = execution_id or _current_execution_id.get()
        if not execution_id:
            return False
        with self._lock:
            record = self._records.get(execution_id)
            return bool(record and record.cancel_requested)

    def checkpoint(self, label: str = "checkpoint") -> None:
        execution_id = _current_execution_id.get()
        if execution_id and self.is_cancel_requested(execution_id):
            with self._lock:
                record = self._records.get(execution_id)
                if record:
                    record.cancellation_observed = True
                    record.note = f"Cancellation observed at {label}"
                    self._persist(record)
            raise ExecutionCancelled(f"Execution cancelled at {label}")

    def complete(
        self,
        execution_id: str,
        *,
        status: str,
        rollback_receipt: Optional[RollbackReceipt] = None,
        note: str = "",
    ) -> ControlledExecution:
        with self._lock:
            record = self._records[execution_id]
            record.status = status
            record.completed_at = _now()
            record.rollback_receipt = rollback_receipt
            record.note = note or record.note
            self._persist(record)
            return record

    def create_rollback_receipt(
        self,
        execution_id: str,
        action_type: str,
        payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> RollbackReceipt:
        compensation_action = None
        compensation_payload: Dict[str, Any] = {}
        reason = "No deterministic compensation is registered for this action."
        if not result.get("success") and not result.get("side_effects"):
            return RollbackReceipt(
                receipt_id=f"rollback_{uuid4().hex[:12]}",
                execution_id=execution_id,
                action_type=action_type,
                supported=False,
                reason="Execution did not report success or structured side effects; no rollback is asserted.",
                requires_approval=True,
            )

        if action_type == "activate_lora":
            compensation_action = "deactivate_lora"
            reason = "Adapter selection can be reversed by selecting the base model."
        elif action_type == "create_note" and result.get("note_id"):
            compensation_action = "delete_note"
            compensation_payload = {"note_id": result["note_id"]}
            reason = "Created note can be deleted by ID; deletion still requires approval."
        elif action_type == "create_backup" and result.get("backup_path"):
            compensation_action = "restore_backup"
            compensation_payload = {"backup_path": result["backup_path"]}
            reason = "Backup can be restored explicitly; restore requires owner approval."

        return RollbackReceipt(
            receipt_id=f"rollback_{uuid4().hex[:12]}",
            execution_id=execution_id,
            action_type=action_type,
            supported=compensation_action is not None,
            reason=reason,
            compensation_action=compensation_action,
            compensation_payload=compensation_payload,
            requires_approval=True,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ControlledExecution:
        receipt = None
        if row[9]:
            receipt = RollbackReceipt(**json.loads(row[9]))
        return ControlledExecution(
            execution_id=row[0], proposal_id=row[1], action_type=row[2],
            status=row[3], started_at=row[4], completed_at=row[5],
            cancel_requested=bool(row[6]), cancel_requested_at=row[7],
            cancellation_observed=bool(row[8]), rollback_receipt=receipt,
            note=row[10],
        )

    def get(self, execution_id: str) -> Optional[ControlledExecution]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM controlled_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            return self._from_row(row) if row else None

    def list(self, active_only: bool = False, limit: int = 100) -> List[ControlledExecution]:
        with sqlite3.connect(self.db_path) as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM controlled_executions WHERE status = 'running' "
                    "ORDER BY started_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM controlled_executions ORDER BY started_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                ).fetchall()
            return [self._from_row(row) for row in rows]


def current_execution_id() -> Optional[str]:
    return _current_execution_id.get()


execution_control_registry = ExecutionControlRegistry()
