"""The owner model: counted patterns from the owner's own decisions.

Personalization without mind-reading: this module counts what the owner has
actually done — approvals and denials per action type (from the approval
store and uncertainty-question answers), active-hours histograms (when the
owner acts), and goal decisions — and surfaces those counts to reasoning.

Honesty rules: every entry carries evidence (action ids, question ids);
rates are Wilson-bounded like the action-outcome store; the report is
labeled as counted observations, never claims about the owner's intent.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wilson(successes: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class OwnerObservation:
    observation_id: str
    kind: str  # action_preference | active_hour
    subject: str
    detail: str
    evidence: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OwnerModelStore:
    """Persistent counted owner patterns (append-only observations)."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "owner_model.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS owner_observations (
                observation_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                subject TEXT NOT NULL,
                detail TEXT NOT NULL,
                evidence TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_owner_obs_kind ON owner_observations(kind, subject)")
            conn.commit()

    # ── intake ──────────────────────────────────────────────────────────────
    def record_action_preference(self, action_type: str, approved: bool, evidence: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO owner_observations VALUES (?,?,?,?,?,?)",
                (f"om_{uuid4().hex[:14]}", "action_preference", str(action_type),
                 "approved" if approved else "denied", evidence, _now()),
            )
            conn.commit()

    def record_active_hour(self, hour_utc: int, evidence: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO owner_observations VALUES (?,?,?,?,?,?)",
                (f"om_{uuid4().hex[:14]}", "active_hour", str(int(hour_utc)), "owner_action", evidence, _now()),
            )
            conn.commit()

    def ingest_from_sources(self, approval_store=None, question_store=None) -> Dict[str, int]:
        """Count existing owner decisions (idempotent by evidence marker)."""
        imported = {"approvals": 0, "questions": 0, "hours": 0}
        with self._lock, sqlite3.connect(self.db_path) as conn:
            seen = {row[0] for row in conn.execute("SELECT evidence FROM owner_observations").fetchall()}
        if approval_store is not None:
            try:
                for request in approval_store.list_all(limit=2000):
                    marker = f"approval:{request.action_id}"
                    if marker in seen:
                        continue
                    decided = request.status in ("approved", "denied", "rejected")
                    if not decided:
                        continue
                    self.record_action_preference(
                        request.action_type, request.status == "approved", marker)
                    self.record_active_hour(
                        datetime.fromisoformat(request.created_at).hour, f"{marker}:hour")
                    imported["approvals"] += 1
                    imported["hours"] += 1
            except Exception as exc:
                app_logger.warning(f"Owner model approval ingest failed: {exc}")
        if question_store is not None:
            try:
                for question in question_store.list(status=None, limit=2000):
                    if question.status != "answered" or not question.answered_at:
                        continue
                    marker = f"question:{question.question_id}"
                    if marker in seen:
                        continue
                    self.record_action_preference(
                        question.action_type, question.answer == "approve", marker)
                    self.record_active_hour(
                        datetime.fromisoformat(question.answered_at).hour, f"{marker}:hour")
                    imported["questions"] += 1
                    imported["hours"] += 1
            except Exception as exc:
                app_logger.warning(f"Owner model question ingest failed: {exc}")
        return imported

    # ── reports ─────────────────────────────────────────────────────────────
    def action_preferences(self, min_n: int = 1) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT subject, detail, COUNT(*) FROM owner_observations "
                "WHERE kind='action_preference' GROUP BY subject, detail"
            ).fetchall()
        preferences = []
        by_action: Dict[str, Dict[str, int]] = {}
        for action_type, detail, n in rows:
            by_action.setdefault(action_type, {})[detail] = int(n)
        for action_type, counts in sorted(by_action.items()):
            approved = counts.get("approved", 0)
            denied = counts.get("denied", 0)
            n = approved + denied
            if n < min_n:
                continue
            low, high = _wilson(approved, n)
            preferences.append({
                "action_type": action_type, "approved": approved, "denied": denied, "n": n,
                "approval_rate": round(approved / n, 4),
                "wilson_low": round(low, 4), "wilson_high": round(high, 4),
            })
        return preferences

    def active_hours(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT subject, COUNT(*) FROM owner_observations "
                "WHERE kind='active_hour' GROUP BY subject"
            ).fetchall()
        hours = [{"hour_utc": int(h), "actions": int(n)} for h, n in rows]
        return sorted(hours, key=lambda x: -x["actions"])

    def report(self) -> Dict[str, Any]:
        preferences = self.action_preferences()
        favorite = [p for p in preferences if p["n"] >= 3 and p["approval_rate"] >= 0.7]
        avoids = [p for p in preferences if p["n"] >= 3 and p["approval_rate"] <= 0.3]
        peak = self.active_hours()[:3]
        return {
            "success": True,
            "counted_preferences": preferences,
            "consistently_approves": [p["action_type"] for p in favorite],
            "consistently_denies": [p["action_type"] for p in avoids],
            "peak_activity_hours_utc": peak,
            "note": "Counted observations of past owner decisions — not claims about intent.",
        }

    def compact_context(self, max_chars: int = 400) -> str:
        report = self.report()
        lines = []
        if report["consistently_approves"]:
            lines.append("Owner consistently approves: " + ", ".join(report["consistently_approves"][:5]))
        if report["consistently_denies"]:
            lines.append("Owner consistently denies: " + ", ".join(report["consistently_denies"][:5]))
        if report["peak_activity_hours_utc"]:
            hours = ", ".join(f"{h['hour_utc']:02d}:00 ({h['actions']})" for h in report["peak_activity_hours_utc"])
            lines.append(f"Peak owner activity (UTC): {hours}")
        return "\n".join(lines)[:max_chars]


# Module-level singleton.
owner_model_store = OwnerModelStore()
