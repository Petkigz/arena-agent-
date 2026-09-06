"""Owner-visible, bounded incubation queue for safe background reasoning.

Incubation is a resumable reasoning work item, not an execution queue. The
queue never invokes tools, changes the world, or treats a generated hypothesis
as an observation. A caller must supply a bounded processor and record a trace
and evidence IDs for every completed result.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import uuid4

from app.cognition.owner_decisions import DECISION_INCUBATION_AUTHORIZATION


WORK_KINDS = frozenset({
    "unresolved_hypothesis",
    "stale_belief",
    "failed_strategy",
    "owner_question",
})
STATUSES = frozenset({"queued", "running", "completed", "failed", "cancelled"})
RESULT_TYPES = frozenset({
    "new_observation",
    "revised_belief",
    "generated_hypothesis",
    "no_change",
    "unknown",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IncubationPolicy:
    enabled: bool
    max_items_per_slice: int
    max_seconds_per_slice: int
    updated_at: str
    decision_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IncubationItem:
    item_id: str
    kind: str
    title: str
    payload: Dict[str, Any]
    status: str
    priority: int
    owner_decision_id: Optional[str]
    attempts: int
    cancel_requested: bool
    resume_token: Optional[str]
    last_trace_id: Optional[str]
    result_type: Optional[str]
    result: Dict[str, Any]
    evidence_ids: List[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IncubationQueueError(ValueError):
    """Invalid, unauthorized, or unsafe incubation queue operation."""


class IncubationQueue:
    """Persistent low-priority queue with explicit owner and cancellation boundaries."""

    STORAGE_SCHEMA_VERSION = 1
    DEFAULT_MAX_ITEMS = 3
    DEFAULT_MAX_SECONDS = 30
    LEASE_SECONDS = 60

    def __init__(self, db_path: str | Path, *, owner_decisions: Optional[Any] = None) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.owner_decisions = owner_decisions
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incubation_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                    storage_schema_version INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    max_items_per_slice INTEGER NOT NULL,
                    max_seconds_per_slice INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    decision_id TEXT
                )
            """)
            meta = conn.execute(
                "SELECT storage_schema_version FROM incubation_meta WHERE singleton=1"
            ).fetchone()
            if meta is None:
                conn.execute(
                    "INSERT INTO incubation_meta VALUES (1, ?, 0, ?, ?, ?, NULL)",
                    (self.STORAGE_SCHEMA_VERSION, self.DEFAULT_MAX_ITEMS, self.DEFAULT_MAX_SECONDS, _now()),
                )
            elif int(meta[0]) != self.STORAGE_SCHEMA_VERSION:
                raise IncubationQueueError(
                    f"unsupported incubation store schema_version={meta[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}"
                )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incubation_items (
                    item_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    owner_decision_id TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    resume_token TEXT,
                    last_trace_id TEXT,
                    result_type TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    lease_token TEXT,
                    lease_expires_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incubation_events (
                    event_id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trace_id TEXT,
                    evidence_json TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def policy(self) -> IncubationPolicy:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT enabled, max_items_per_slice, max_seconds_per_slice, updated_at, decision_id "
                "FROM incubation_meta WHERE singleton=1"
            ).fetchone()
        if row is None:
            raise IncubationQueueError("incubation policy is missing")
        return IncubationPolicy(bool(row[0]), int(row[1]), int(row[2]), row[3], row[4])

    def _authorize(self, decision_id: Optional[str], operation: str) -> None:
        if not decision_id:
            raise PermissionError(f"owner authorization is required for incubation operation: {operation}")
        if self.owner_decisions is None:
            raise PermissionError("owner decision store is unavailable")
        result = self.owner_decisions.validate(
            decision_id,
            decision_type=DECISION_INCUBATION_AUTHORIZATION,
            claimed_change_types=[operation],
        )
        if not result.get("valid"):
            raise PermissionError(
                f"incubation operation was not authorized: {result.get('reasons', [])}"
            )

    def set_policy(
        self,
        *,
        enabled: bool,
        max_items_per_slice: int = DEFAULT_MAX_ITEMS,
        max_seconds_per_slice: int = DEFAULT_MAX_SECONDS,
        owner_decision_id: Optional[str],
    ) -> IncubationPolicy:
        if isinstance(max_items_per_slice, bool) or not 1 <= int(max_items_per_slice) <= 20:
            raise IncubationQueueError("max_items_per_slice must be between 1 and 20")
        if isinstance(max_seconds_per_slice, bool) or not 1 <= int(max_seconds_per_slice) <= 300:
            raise IncubationQueueError("max_seconds_per_slice must be between 1 and 300")
        self._authorize(owner_decision_id, "configure_incubation")
        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE incubation_meta SET enabled=?, max_items_per_slice=?, max_seconds_per_slice=?, "
                "updated_at=?, decision_id=? WHERE singleton=1",
                (int(bool(enabled)), int(max_items_per_slice), int(max_seconds_per_slice), now, owner_decision_id),
            )
            self._event_conn(
                conn,
                item_id="__policy__",
                event_type="policy_changed",
                status="enabled" if enabled else "disabled",
                detail={
                    "enabled": bool(enabled),
                    "max_items_per_slice": int(max_items_per_slice),
                    "max_seconds_per_slice": int(max_seconds_per_slice),
                    "decision_id": owner_decision_id,
                },
            )
            conn.commit()
        return self.policy()

    def enqueue(
        self,
        kind: str,
        title: str,
        payload: Dict[str, Any],
        *,
        priority: int = 0,
        owner_decision_id: Optional[str] = None,
    ) -> IncubationItem:
        if kind not in WORK_KINDS:
            raise IncubationQueueError(f"unsupported incubation kind: {kind}")
        if not title or len(title) > 300:
            raise IncubationQueueError("incubation title must be between 1 and 300 characters")
        if not isinstance(payload, dict):
            raise IncubationQueueError("incubation payload must be a mapping")
        if isinstance(priority, bool) or not -10 <= int(priority) <= 10:
            raise IncubationQueueError("incubation priority must be between -10 and 10")
        # A disabled queue may still receive an owner-authorized item, but it
        # cannot be claimed until the owner enables incubation.
        if not self.policy().enabled:
            self._authorize(owner_decision_id, "enqueue_incubation")
        item_id = f"incubation_{uuid4().hex[:16]}"
        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO incubation_items "
                "(item_id, kind, title, payload_json, status, priority, owner_decision_id, attempts, "
                "cancel_requested, resume_token, last_trace_id, result_type, result_json, evidence_json, "
                "created_at, updated_at, lease_token, lease_expires_at) "
                "VALUES (?, ?, ?, ?, 'queued', ?, ?, 0, 0, NULL, NULL, NULL, '{}', '[]', ?, ?, NULL, NULL)",
                (item_id, kind, title, json.dumps(payload, sort_keys=True, default=str), int(priority), owner_decision_id, now, now),
            )
            self._event_conn(
                conn,
                item_id=item_id,
                event_type="enqueued",
                status="queued",
                detail={"kind": kind, "title": title, "priority": int(priority)},
            )
            conn.commit()
        return self.get(item_id)  # type: ignore[return-value]

    def _item_from_row(self, row: tuple) -> IncubationItem:
        return IncubationItem(
            item_id=row[0], kind=row[1], title=row[2], payload=json.loads(row[3]), status=row[4],
            priority=int(row[5]), owner_decision_id=row[6], attempts=int(row[7]),
            cancel_requested=bool(row[8]), resume_token=row[9], last_trace_id=row[10],
            result_type=row[11], result=json.loads(row[12]), evidence_ids=json.loads(row[13]),
            created_at=row[14], updated_at=row[15],
        )

    @staticmethod
    def _select_columns() -> str:
        return (
            "item_id, kind, title, payload_json, status, priority, owner_decision_id, attempts, "
            "cancel_requested, resume_token, last_trace_id, result_type, result_json, evidence_json, "
            "created_at, updated_at"
        )

    def get(self, item_id: str) -> Optional[IncubationItem]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                f"SELECT {self._select_columns()} FROM incubation_items WHERE item_id=?", (item_id,)
            ).fetchone()
        return self._item_from_row(row) if row else None

    def list(self, status: Optional[str] = None, limit: int = 100) -> List[IncubationItem]:
        if status is not None and status not in STATUSES:
            raise IncubationQueueError(f"unsupported incubation status: {status}")
        query = f"SELECT {self._select_columns()} FROM incubation_items"
        params: List[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY priority DESC, created_at ASC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._item_from_row(row) for row in rows]

    def cancel(self, item_id: str, *, reason: str = "owner cancellation") -> IncubationItem:
        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                f"SELECT {self._select_columns()}, lease_token FROM incubation_items WHERE item_id=?",
                (item_id,),
            ).fetchone()
            if row is None:
                raise KeyError(item_id)
            status = row[4]
            if status in {"completed", "failed", "cancelled"}:
                return self._item_from_row(row[:16])
            if status == "queued":
                conn.execute(
                    "UPDATE incubation_items SET status='cancelled', cancel_requested=1, updated_at=? WHERE item_id=?",
                    (now, item_id),
                )
                event_status = "cancelled"
            else:
                conn.execute(
                    "UPDATE incubation_items SET cancel_requested=1, updated_at=? WHERE item_id=?",
                    (now, item_id),
                )
                event_status = "cancellation_requested"
            self._event_conn(conn, item_id=item_id, event_type=event_status, status=event_status,
                             detail={"reason": str(reason or "owner cancellation")})
            conn.commit()
        return self.get(item_id)  # type: ignore[return-value]

    def claim_next(self) -> Optional[IncubationItem]:
        if not self.policy().enabled:
            return None
        now = _now()
        lease_until = (datetime.now(timezone.utc) + timedelta(seconds=self.LEASE_SECONDS)).isoformat()
        lease_token = f"lease_{uuid4().hex[:16]}"
        with self._lock, sqlite3.connect(self.db_path, timeout=10, isolation_level=None) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE incubation_items SET status='queued', lease_token=NULL, lease_expires_at=NULL, updated_at=? "
                "WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at<?",
                (now, now),
            )
            row = conn.execute(
                f"SELECT {self._select_columns()} FROM incubation_items "
                "WHERE status='queued' AND cancel_requested=0 ORDER BY priority DESC, created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            item_id = row[0]
            updated = conn.execute(
                "UPDATE incubation_items SET status='running', attempts=attempts+1, lease_token=?, "
                "lease_expires_at=?, updated_at=? WHERE item_id=? AND status='queued' AND cancel_requested=0",
                (lease_token, lease_until, now, item_id),
            ).rowcount
            if updated != 1:
                conn.execute("ROLLBACK")
                return None
            self._event_conn(conn, item_id=item_id, event_type="claimed", status="running",
                             detail={"lease_token": lease_token})
            conn.execute("COMMIT")
        return self.get(item_id)

    def is_cancel_requested(self, item_id: str) -> bool:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT cancel_requested FROM incubation_items WHERE item_id=?", (item_id,)).fetchone()
        return bool(row and row[0])

    def complete(
        self,
        item_id: str,
        *,
        result_type: str,
        result: Dict[str, Any],
        trace_id: str,
        evidence_ids: Iterable[str],
        resume_token: Optional[str] = None,
    ) -> IncubationItem:
        if result_type not in RESULT_TYPES:
            raise IncubationQueueError(f"unsupported incubation result type: {result_type}")
        if not trace_id:
            raise IncubationQueueError("incubation completion requires a trace_id")
        evidence = [str(item) for item in evidence_ids if str(item).strip()]
        if not evidence:
            raise IncubationQueueError(
                "incubation completion requires evidence_ids; use an explicit evidence item for UNKNOWN results"
            )
        if not isinstance(result, dict):
            raise IncubationQueueError("incubation result must be a mapping")
        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status, cancel_requested FROM incubation_items WHERE item_id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise KeyError(item_id)
            if row[0] != "running":
                raise IncubationQueueError(f"incubation item is not actively claimed: {row[0]}")
            if row[1]:
                conn.execute(
                    "UPDATE incubation_items SET status='cancelled', cancel_requested=1, updated_at=?, "
                    "lease_token=NULL, lease_expires_at=NULL WHERE item_id=?",
                    (now, item_id),
                )
                self._event_conn(conn, item_id=item_id, event_type="cancelled", status="cancelled",
                                 trace_id=trace_id, evidence=evidence,
                                 detail={"reason": "cancellation observed before completion"})
            else:
                conn.execute(
                    "UPDATE incubation_items SET status='completed', result_type=?, result_json=?, evidence_json=?, "
                    "last_trace_id=?, resume_token=?, updated_at=?, lease_token=NULL, lease_expires_at=NULL "
                    "WHERE item_id=?",
                    (result_type, json.dumps(result, sort_keys=True, default=str), json.dumps(evidence),
                     trace_id, resume_token, now, item_id),
                )
                self._event_conn(conn, item_id=item_id, event_type="completed", status="completed",
                                 trace_id=trace_id, evidence=evidence,
                                 detail={"result_type": result_type, "resume_token": resume_token})
            conn.commit()
        return self.get(item_id)  # type: ignore[return-value]

    def fail(self, item_id: str, *, trace_id: str, evidence_ids: Iterable[str], error: str) -> IncubationItem:
        evidence = [str(item) for item in evidence_ids if str(item).strip()]
        if not trace_id or not evidence:
            raise IncubationQueueError("incubation failure requires a trace_id and evidence_ids")
        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status, cancel_requested FROM incubation_items WHERE item_id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise KeyError(item_id)
            if row[1]:
                conn.execute(
                    "UPDATE incubation_items SET status='cancelled', result_type=NULL, result_json='{}', "
                    "evidence_json=?, last_trace_id=?, updated_at=?, lease_token=NULL, lease_expires_at=NULL WHERE item_id=?",
                    (json.dumps(evidence), trace_id, now, item_id),
                )
                self._event_conn(
                    conn, item_id=item_id, event_type="cancelled", status="cancelled", trace_id=trace_id,
                    evidence=evidence, detail={"reason": "cancellation observed before failure commit"},
                )
            else:
                conn.execute(
                    "UPDATE incubation_items SET status='failed', result_type='unknown', result_json=?, "
                    "evidence_json=?, last_trace_id=?, updated_at=?, lease_token=NULL, lease_expires_at=NULL WHERE item_id=?",
                    (json.dumps({"error": str(error)}, sort_keys=True), json.dumps(evidence), trace_id, now, item_id),
                )
                self._event_conn(conn, item_id=item_id, event_type="failed", status="failed", trace_id=trace_id,
                                 evidence=evidence, detail={"error": str(error)})
            conn.commit()
        return self.get(item_id)  # type: ignore[return-value]

    def resume(self, item_id: str) -> IncubationItem:
        """Requeue a completed/failed item while preserving its resume token and history."""
        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT status FROM incubation_items WHERE item_id=?", (item_id,)).fetchone()
            if row is None:
                raise KeyError(item_id)
            if row[0] not in {"completed", "failed", "cancelled"}:
                raise IncubationQueueError(f"only terminal incubation items can resume: {row[0]}")
            conn.execute(
                "UPDATE incubation_items SET status='queued', cancel_requested=0, updated_at=?, "
                "lease_token=NULL, lease_expires_at=NULL WHERE item_id=?",
                (now, item_id),
            )
            self._event_conn(conn, item_id=item_id, event_type="resumed", status="queued",
                             detail={"resume_token_preserved": True})
            conn.commit()
        return self.get(item_id)  # type: ignore[return-value]

    def run_slice(self, processor: Callable[[IncubationItem], Dict[str, Any]]) -> Dict[str, Any]:
        """Run only bounded, non-executing processors during an enabled slice."""
        if not callable(processor):
            raise IncubationQueueError("incubation processor must be callable")
        policy = self.policy()
        if not policy.enabled:
            return {"status": "disabled", "processed": 0, "items": []}
        started = time.monotonic()
        processed: List[Dict[str, Any]] = []
        while len(processed) < policy.max_items_per_slice and time.monotonic() - started < policy.max_seconds_per_slice:
            item = self.claim_next()
            if item is None:
                break
            if self.is_cancel_requested(item.item_id):
                self.cancel(item.item_id, reason="cancellation observed before processor start")
                continue
            try:
                outcome = processor(item)
                if not isinstance(outcome, dict):
                    raise IncubationQueueError("incubation processor must return a mapping")
                completed = self.complete(
                    item.item_id,
                    result_type=str(outcome["result_type"]),
                    result=dict(outcome.get("result", {})),
                    trace_id=str(outcome["trace_id"]),
                    evidence_ids=outcome.get("evidence_ids", []),
                    resume_token=outcome.get("resume_token"),
                )
            except Exception as exc:
                completed = self.fail(
                    item.item_id,
                    trace_id=f"incubation-error:{item.item_id}",
                    evidence_ids=[f"processor-error:{type(exc).__name__}"],
                    error=str(exc),
                )
            processed.append(completed.to_dict())
        return {
            "status": "completed",
            "processed": len(processed),
            "items": processed,
            "budget": policy.to_dict(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "execution_performed": False,
        }

    def history(self, item_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        query = (
            "SELECT event_id, item_id, event_type, status, trace_id, evidence_json, detail_json, created_at "
            "FROM incubation_events"
        )
        params: List[Any] = []
        if item_id:
            query += " WHERE item_id=?"
            params.append(item_id)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(max(1, min(int(limit), 2000)))
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "event_id": row[0], "item_id": row[1], "event_type": row[2], "status": row[3],
                "trace_id": row[4], "evidence_ids": json.loads(row[5]), "detail": json.loads(row[6]),
                "created_at": row[7],
            }
            for row in rows
        ]

    @staticmethod
    def _event_conn(
        conn: sqlite3.Connection,
        *,
        item_id: str,
        event_type: str,
        status: str,
        trace_id: Optional[str] = None,
        evidence: Iterable[str] = (),
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        conn.execute(
            "INSERT INTO incubation_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"incubation_event_{uuid4().hex[:16]}", item_id, event_type, status, trace_id,
                json.dumps(list(evidence)), json.dumps(detail or {}, sort_keys=True, default=str), _now(),
            ),
        )
