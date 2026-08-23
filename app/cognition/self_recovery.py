"""Persistent, advisory-only recovery for functional identity discontinuities.

Recovery analysis grants no authority. An owner may dismiss/acknowledge an
assessment or submit an exact recovery action into the normal approval queue;
execution remains a later, separately authorized stage.
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SelfRecoveryProtocol:
    @staticmethod
    def assess(
        report: Dict[str, Any], *, owner_change_evidence: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        owner_change_evidence = owner_change_evidence or []
        recommendations, causes = [], []
        for issue in report.get("issues", []):
            kind = issue.get("type")
            if owner_change_evidence:
                cause = "owner_approved_change"
            elif kind in ("missing_interfaces", "capability_count_decreased"):
                cause = "dependency_or_hardware_loss"
            elif kind == "owner_policy_revision_rollback":
                cause = "state_rollback_or_corruption"
            else:
                cause = "unknown"
            causes.append({
                "issue": kind,
                "cause": cause,
                "confidence": 0.9 if owner_change_evidence else 0.6,
                "evidence": list(owner_change_evidence),
            })
            recommendations.append({
                "issue": kind,
                "recommendation": (
                    "Re-probe and compare evidence; request owner approval before "
                    "reinstalling, restoring, or changing policy."
                ),
                "execution_authorized": False,
                "action_type": None,
                "payload": None,
            })
        return {
            "continuous": report.get("continuous", False),
            "checkpoint_id": report.get("checkpoint_id"),
            "causes": causes,
            "recommendations": recommendations,
            "automatic_actions": [],
            "requires_owner_authorization": bool(recommendations),
            "note": (
                "Advisory recovery only; no authority, package, policy, or state "
                "is restored automatically."
            ),
        }


@dataclass(frozen=True)
class RecoveryAssessment:
    assessment_id: str
    checkpoint_id: str
    status: str
    report: Dict[str, Any]
    created_at: str
    decided_at: Optional[str]
    owner_note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfRecoveryStore:
    STATUSES = {"pending", "acknowledged", "dismissed", "action_requested"}

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS recovery_assessments (
                assessment_id TEXT PRIMARY KEY,
                checkpoint_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                owner_note TEXT NOT NULL
            )""")
            conn.commit()

    @staticmethod
    def _from_row(row) -> RecoveryAssessment:
        return RecoveryAssessment(
            assessment_id=row[0], checkpoint_id=row[1], status=row[2],
            report=json.loads(row[3]), created_at=row[4], decided_at=row[5],
            owner_note=row[6],
        )

    def save(self, continuity_report: Dict[str, Any], *, owner_evidence=None) -> RecoveryAssessment:
        checkpoint_id = str(continuity_report.get("checkpoint_id") or "").strip()
        if not checkpoint_id:
            raise ValueError("Continuity checkpoint id is required")
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM recovery_assessments WHERE checkpoint_id=?",
                (checkpoint_id,),
            ).fetchone()
            if row:
                return self._from_row(row)
            report = SelfRecoveryProtocol.assess(
                continuity_report, owner_change_evidence=owner_evidence
            )
            item = RecoveryAssessment(
                assessment_id=f"recovery_{uuid4().hex[:16]}",
                checkpoint_id=checkpoint_id, status="pending", report=report,
                created_at=_now(), decided_at=None, owner_note="",
            )
            conn.execute(
                "INSERT INTO recovery_assessments VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item.assessment_id, item.checkpoint_id, item.status,
                 json.dumps(item.report), item.created_at, None, ""),
            )
            conn.commit()
            return item

    def decide(self, assessment_id: str, status: str, note: str = "") -> RecoveryAssessment:
        if status not in ("acknowledged", "dismissed"):
            raise ValueError("Recovery review status must be acknowledged or dismissed")
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM recovery_assessments WHERE assessment_id=?",
                (assessment_id,),
            ).fetchone()
            if not row:
                raise KeyError(assessment_id)
            current = self._from_row(row)
            if current.status != "pending":
                raise ValueError(f"Recovery assessment is already {current.status}")
            decided_at = _now()
            conn.execute(
                "UPDATE recovery_assessments SET status=?, decided_at=?, owner_note=? "
                "WHERE assessment_id=?",
                (status, decided_at, note, assessment_id),
            )
            conn.commit()
        return RecoveryAssessment(
            current.assessment_id, current.checkpoint_id, status, current.report,
            current.created_at, decided_at, note,
        )

    def mark_action_requested(self, assessment_id: str, note: str) -> RecoveryAssessment:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM recovery_assessments WHERE assessment_id=?",
                (assessment_id,),
            ).fetchone()
            if not row:
                raise KeyError(assessment_id)
            current = self._from_row(row)
            decided_at = _now()
            conn.execute(
                "UPDATE recovery_assessments SET status='action_requested', "
                "decided_at=?, owner_note=? WHERE assessment_id=?",
                (decided_at, note, assessment_id),
            )
            conn.commit()
        return RecoveryAssessment(
            current.assessment_id, current.checkpoint_id, "action_requested",
            current.report, current.created_at, decided_at, note,
        )

    def list(self, status: Optional[str] = None, limit: int = 200) -> List[RecoveryAssessment]:
        bounded = max(1, min(limit, 1000))
        with sqlite3.connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM recovery_assessments WHERE status=? "
                    "ORDER BY created_at DESC LIMIT ?", (status, bounded),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM recovery_assessments ORDER BY created_at DESC LIMIT ?",
                    (bounded,),
                ).fetchall()
        return [self._from_row(row) for row in rows]
