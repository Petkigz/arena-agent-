"""Restart-safe commitments and deterministic introspection summaries.

A commitment is created only from an explicit owner-authorized action, approved
plan, persistent project, or explicit owner entry. Model prose cannot create a
commitment. Completion requires verification evidence.
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


SOURCES = {"owner_authorized_action", "approved_plan", "project", "explicit_owner"}
STATUSES = {"active", "blocked", "completed", "failed", "cancelled"}


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    title: str
    source_type: str
    source_id: str
    status: str
    evidence: List[str]
    blocked_reason: str
    completion_verified: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CommitmentLedger:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS commitments (
                commitment_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                blocked_reason TEXT NOT NULL,
                completion_verified INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_type, source_id)
            )""")
            conn.commit()

    @staticmethod
    def _from_row(row) -> Commitment:
        return Commitment(
            commitment_id=row[0], title=row[1], source_type=row[2], source_id=row[3],
            status=row[4], evidence=json.loads(row[5]), blocked_reason=row[6],
            completion_verified=bool(row[7]), created_at=row[8], updated_at=row[9],
        )

    def upsert(
        self,
        title: str,
        *,
        source_type: str,
        source_id: str,
        status: str = "active",
        evidence: Optional[List[str]] = None,
        blocked_reason: str = "",
        completion_verified: bool = False,
    ) -> Commitment:
        source_type = source_type.strip().lower()
        status = status.strip().lower()
        evidence = [str(item).strip() for item in (evidence or []) if str(item).strip()]
        if source_type not in SOURCES:
            raise ValueError(f"Unsupported commitment source: {source_type}")
        if status not in STATUSES:
            raise ValueError(f"Unsupported commitment status: {status}")
        if not source_id.strip() or not title.strip():
            raise ValueError("Commitment title and source id are required")
        if status == "completed" and (not completion_verified or not evidence):
            raise ValueError("Completed commitments require verification evidence")
        if status == "blocked" and not blocked_reason.strip():
            raise ValueError("Blocked commitments require a reason")

        now = _now()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM commitments WHERE source_type=? AND source_id=?",
                (source_type, source_id),
            ).fetchone()
            if row:
                prior = self._from_row(row)
                created_at, commitment_id = prior.created_at, prior.commitment_id
            else:
                created_at, commitment_id = now, f"commit_{uuid4().hex[:16]}"
            conn.execute("""INSERT OR REPLACE INTO commitments VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                commitment_id, title.strip(), source_type, source_id.strip(), status,
                json.dumps(evidence), blocked_reason.strip(), int(completion_verified),
                created_at, now,
            ))
            conn.commit()
        return Commitment(
            commitment_id=commitment_id, title=title.strip(), source_type=source_type,
            source_id=source_id.strip(), status=status, evidence=evidence,
            blocked_reason=blocked_reason.strip(), completion_verified=completion_verified,
            created_at=created_at, updated_at=now,
        )

    def sync_project(self, project: Any) -> Commitment:
        project_status = getattr(getattr(project, "status", None), "value", "active")
        status_map = {
            "active": "active", "paused": "blocked", "blocked": "blocked",
            "completed": "completed", "abandoned": "cancelled",
        }
        status = status_map.get(project_status, "active")
        reached = [
            milestone.milestone_id for milestone in getattr(project, "milestones", [])
            if getattr(milestone, "status", "") == "reached"
        ]
        evidence = [f"project:{project.project_id}"] + [f"milestone:{item}" for item in reached]
        verified = status == "completed" and bool(getattr(project, "milestones", [])) and (
            len(reached) == len(project.milestones)
        )
        reason = ""
        if status == "completed" and not verified:
            status = "blocked"
            reason = "Project completion lacks verified reached-milestone evidence."
        elif status == "blocked":
            reason = "Project is paused or blocked; inspect project milestones for the cause."
        return self.upsert(
            project.name, source_type="project", source_id=project.project_id,
            status=status, evidence=evidence, blocked_reason=reason,
            completion_verified=verified,
        )

    def get_by_source(self, source_type: str, source_id: str) -> Optional[Commitment]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM commitments WHERE source_type=? AND source_id=?",
                (source_type, source_id),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self, status: Optional[str] = None, limit: int = 500) -> List[Commitment]:
        if status and status not in STATUSES:
            raise ValueError(f"Unsupported commitment status: {status}")
        with sqlite3.connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM commitments WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                    (status, max(1, min(limit, 2000))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM commitments ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(limit, 2000)),),
                ).fetchall()
        return [self._from_row(row) for row in rows]


class GroundedIntrospection:
    """Build self-explanations from persisted trace facts, never hidden reasoning."""

    @staticmethod
    def explain_trace(trace_db_path: str | Path, trace_id: str) -> Dict[str, Any]:
        path = Path(trace_db_path)
        if not path.exists():
            return {"success": False, "error": "Trace database does not exist"}
        with sqlite3.connect(path) as conn:
            try:
                row = conn.execute(
                    "SELECT trace_id, session_id, user_input, actions_json, model_used, "
                    "gate_decision, prediction_surprisal, reflection_lesson, goal_verified, "
                    "attention_focus, created_at FROM cognitive_traces WHERE trace_id=?",
                    (trace_id,),
                ).fetchone()
                # Older trace databases do not have the optional presentation
                # column. Keep introspection backward-compatible while using
                # it whenever a new runtime trace provides it.
                columns = {item[1] for item in conn.execute("PRAGMA table_info(cognitive_traces)").fetchall()}
                presentation_row = None
                if "epistemic_presentation_json" in columns:
                    presentation_row = conn.execute(
                        "SELECT epistemic_presentation_json FROM cognitive_traces WHERE trace_id=?",
                        (trace_id,),
                    ).fetchone()
            except sqlite3.Error as exc:
                return {"success": False, "error": f"Trace lookup failed: {exc}"}
        if not row:
            return {"success": False, "error": "Trace not found"}
        actions = json.loads(row[3])
        epistemic_presentation: Dict[str, Any] = {}
        if presentation_row and presentation_row[0]:
            try:
                parsed = json.loads(presentation_row[0])
                if isinstance(parsed, dict):
                    epistemic_presentation = parsed
            except (TypeError, ValueError):
                epistemic_presentation = {}
        facts = {
            "trace_id": row[0], "session_id": row[1], "request": row[2],
            "actions": actions, "model_used": row[4], "gate_decision": row[5],
            "prediction_surprisal": row[6], "lesson": row[7],
            "goal_verified": bool(row[8]), "attention_focus": row[9],
            "created_at": row[10],
        }
        explanation = [
            f"The recorded gate decision was '{row[5]}'.",
            f"The trace recorded {len(actions)} executed action(s).",
            f"Independent goal verification was {'satisfied' if row[8] else 'not satisfied'}.",
        ]
        if row[9]:
            explanation.append(f"Recorded attention focus: {row[9]}.")
        if row[7]:
            explanation.append(f"Recorded lesson: {row[7]}")
        if epistemic_presentation:
            facts["epistemic_presentation"] = epistemic_presentation
            label = epistemic_presentation.get("confidence_label", "Unknown")
            basis = epistemic_presentation.get("evidence_basis") or []
            explanation.append(f"User-facing epistemic status: {label}.")
            if basis:
                explanation.append(f"Recorded evidence basis: {basis[0]}")
        return {
            "success": True,
            "facts": facts,
            "epistemic_presentation": epistemic_presentation,
            "explanation": explanation,
            "unknowns": [
                "Private chain-of-thought is not available or claimed.",
                "The trace cannot prove subjective experience or consciousness.",
            ],
        }
