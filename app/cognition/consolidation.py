"""Audited consolidation of conflicts, durable gists, and calibration reports.

Consolidation is distinct from foreground execution and from belief ingestion:
it replays stored evidence, may create a clearly marked derived gist from
repeated verified episodes, and refreshes calibration telemetry. It never
silently resolves contradictory evidence and never invents observations.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConsolidationRun:
    run_id: str
    status: str
    started_at: str
    finished_at: Optional[str]
    conflicts_replayed: int
    gists_created: int
    calibration_refreshed: bool
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "conflicts_replayed": self.conflicts_replayed,
            "gists_created": self.gists_created,
            "calibration_refreshed": self.calibration_refreshed,
            "errors": list(self.errors),
        }


class ConsolidationError(ValueError):
    """Invalid consolidation configuration or unreadable consolidation history."""


class ConsolidationCoordinator:
    """Run bounded, evidence-preserving consolidation with durable telemetry."""

    STORAGE_SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consolidation_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                    storage_schema_version INTEGER NOT NULL
                )
            """)
            row = conn.execute(
                "SELECT storage_schema_version FROM consolidation_meta WHERE singleton=1"
            ).fetchone()
            if row is None:
                conn.execute("INSERT INTO consolidation_meta VALUES (1, ?)", (self.STORAGE_SCHEMA_VERSION,))
            elif int(row[0]) != self.STORAGE_SCHEMA_VERSION:
                raise ConsolidationError(
                    f"unsupported consolidation store schema_version={row[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}"
                )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consolidation_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    conflicts_replayed INTEGER NOT NULL DEFAULT 0,
                    gists_created INTEGER NOT NULL DEFAULT 0,
                    calibration_refreshed INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consolidation_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    subject_id TEXT,
                    status TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _start(self) -> str:
        run_id = f"consolidation_{uuid4().hex[:16]}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO consolidation_runs (run_id, status, started_at) VALUES (?, 'running', ?)",
                (run_id, _now()),
            )
            conn.commit()
        return run_id

    def _event(
        self,
        run_id: str,
        event_type: str,
        *,
        subject_id: Optional[str] = None,
        status: str,
        detail: Dict[str, Any],
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO consolidation_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"consolidation_event_{uuid4().hex[:16]}", run_id, event_type,
                    subject_id, status, json.dumps(detail, sort_keys=True, default=str), _now(),
                ),
            )
            conn.commit()

    @staticmethod
    def _conflict_tasks(memory_store: Any, limit: int) -> List[str]:
        """Find explicit task groups with disagreeing verified outcomes only."""
        with memory_store._connect() as conn:  # MemoryStore owns this local SQLite boundary.
            rows = conn.execute(
                """
                SELECT task_id
                FROM cognitive_memory
                WHERE task_id IS NOT NULL AND success IS NOT NULL
                GROUP BY task_id
                HAVING COUNT(DISTINCT success) > 1
                ORDER BY MIN(created_at)
                LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _replay_conflicts(self, run_id: str, memory_store: Any, *, limit: int) -> int:
        count = 0
        for task_id in self._conflict_tasks(memory_store, limit):
            records = memory_store.list_by_task(task_id, limit=200)
            verified = [record for record in records if record.success is not None]
            self._event(
                run_id,
                "conflict_replayed",
                subject_id=task_id,
                status="requires_fresh_evidence",
                detail={
                    "task_id": task_id,
                    "memory_ids": [record.memory_id for record in verified],
                    "outcomes": [
                        {"memory_id": record.memory_id, "success": record.success, "outcome": record.outcome}
                        for record in verified
                    ],
                    "resolution": "not_resolved",
                    "unknown_preserved": True,
                },
            )
            count += 1
        return count

    def _improve_gists(self, run_id: str, memory_store: Any, *, limit: int) -> int:
        with memory_store._connect() as conn:
            rows = conn.execute(
                """
                SELECT task_id
                FROM cognitive_memory
                WHERE task_id IS NOT NULL AND kind='episodic' AND source='goal_verifier' AND success=1
                GROUP BY task_id
                HAVING COUNT(*) >= 2
                ORDER BY MIN(created_at)
                LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        created = 0
        for row in rows:
            task_id = str(row[0])
            records = memory_store.list_by_task(task_id, limit=200)
            verified = [record for record in records if record.source == "goal_verifier" and record.success is not None]
            if any(record.success is False for record in verified):
                self._event(
                    run_id,
                    "gist_skipped",
                    subject_id=task_id,
                    status="conflict",
                    detail={"reason": "verified success and failure coexist", "unknown_preserved": True},
                )
                continue
            successes = [record for record in verified if record.success is True]
            if len(successes) < 2:
                continue
            evidence_ids = sorted(record.memory_id for record in successes)
            excerpt = " | ".join(record.content[:240] for record in sorted(successes, key=lambda item: item.memory_id)[:3])
            content = (
                f"Derived verified gist for task {task_id}: {excerpt}. "
                "This is a consolidated historical pattern, not a current observation."
            )
            target = memory_store.find_exact("semantic", content)
            created_now = False
            if target is None:
                target = memory_store.add(
                    "semantic",
                    content,
                    importance=0.75,
                    source="consolidation_gist",
                    task_id=task_id,
                    tags=("gist", "verified_history", *[f"evidence:{item}" for item in evidence_ids]),
                    outcome="derived_historical_pattern",
                    success=True,
                )
                created += 1
                created_now = True
            for record in successes:
                memory_store.link_consolidation(record.memory_id, target.memory_id, relation="consolidated_into")
            self._event(
                run_id,
                "gist_improved",
                subject_id=task_id,
                status="created" if created_now else "existing",
                detail={"gist_memory_id": target.memory_id, "supporting_memory_ids": evidence_ids},
            )
        return created

    def _refresh_calibration(self, run_id: str, calibrator: Any) -> bool:
        if calibrator is None:
            self._event(run_id, "calibration_refresh", status="unavailable", detail={"reason": "no calibrator"})
            return False
        report = calibrator.longitudinal_report()
        self._event(
            run_id,
            "calibration_refresh",
            status="refreshed",
            detail={
                "total_records": report.get("total_records", 0),
                "ece": report.get("ece"),
                "trend": report.get("trend"),
                "evidence_sufficient": report.get("evidence_sufficient", False),
                "note": "recalculated from recorded predictions and verified outcomes; no outcomes invented",
            },
        )
        return True

    def run(
        self,
        memory_store: Any,
        *,
        calibrator: Any = None,
        max_tasks: int = 50,
    ) -> Dict[str, Any]:
        """Run a bounded consolidation pass and return auditable telemetry."""
        run_id = self._start()
        errors: List[str] = []
        conflicts = 0
        gists = 0
        calibration = False
        try:
            conflicts = self._replay_conflicts(run_id, memory_store, limit=max_tasks)
        except Exception as exc:
            errors.append(f"conflict_replay: {exc}")
            self._event(run_id, "stage_error", status="error", detail={"stage": "conflict_replay", "error": str(exc)})
        try:
            gists = self._improve_gists(run_id, memory_store, limit=max_tasks)
        except Exception as exc:
            errors.append(f"gist_improvement: {exc}")
            self._event(run_id, "stage_error", status="error", detail={"stage": "gist_improvement", "error": str(exc)})
        try:
            calibration = self._refresh_calibration(run_id, calibrator)
        except Exception as exc:
            errors.append(f"calibration_refresh: {exc}")
            self._event(run_id, "stage_error", status="error", detail={"stage": "calibration_refresh", "error": str(exc)})
        status = "completed_with_errors" if errors else "completed"
        finished = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE consolidation_runs SET status=?, finished_at=?, conflicts_replayed=?, gists_created=?, "
                "calibration_refreshed=?, errors_json=? WHERE run_id=?",
                (status, finished, conflicts, gists, int(calibration), json.dumps(errors), run_id),
            )
            conn.commit()
        return {
            "run_id": run_id,
            "status": status,
            "conflicts_replayed": conflicts,
            "gists_created": gists,
            "calibration_refreshed": calibration,
            "errors": errors,
        }

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT run_id, status, started_at, finished_at, conflicts_replayed, gists_created, "
                "calibration_refreshed, errors_json FROM consolidation_runs ORDER BY started_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "run_id": row[0], "status": row[1], "started_at": row[2], "finished_at": row[3],
                "conflicts_replayed": row[4], "gists_created": row[5],
                "calibration_refreshed": bool(row[6]), "errors": json.loads(row[7]),
            }
            for row in rows
        ]

    def events(self, run_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, subject_id, status, detail_json, created_at "
                "FROM consolidation_events WHERE run_id=? ORDER BY created_at ASC LIMIT ?",
                (run_id, max(1, min(int(limit), 2000))),
            ).fetchall()
        return [
            {
                "event_id": row[0], "event_type": row[1], "subject_id": row[2],
                "status": row[3], "detail": json.loads(row[4]), "created_at": row[5],
            }
            for row in rows
        ]
