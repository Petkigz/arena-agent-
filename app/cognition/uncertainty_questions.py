"""Uncertainty-driven owner questions: ask instead of acting on weak evidence.

A human who is 40% sure asks; an agent that is 40% sure and acts anyway is
just noisy. When an action proposal's CALIBRATED confidence is below the
owner's threshold, the gate does not execute it — it formulates a precise,
evidence-bound question and records it for the owner.

Stage separation is preserved end to end:
  * The question is a CONSIDERATION-stage artifact (what am I unsure about?).
  * Answering "approve" creates an exact authorization-stage approval in the
    approval store — it does NOT execute anything.
  * Execution remains a separate explicit action, exactly as before.

Honesty rules: confidence numbers come from calibration history, not vibes;
the question states why confidence is low; unanswered questions expire (TTL)
rather than silently lingering; UNKNOWN never becomes an excuse ("I don't
know" produces an observation request, not a guess).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger

_ANSWERS = {"approve", "deny", "observe"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_digest(action_type: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps({"a": action_type, "p": payload}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


@dataclass
class OwnerQuestion:
    question_id: str
    proposal_id: str
    action_type: str
    payload: Dict[str, Any]
    question_text: str
    options: List[str]
    reason: str
    raw_confidence: float
    calibrated_confidence: float
    threshold: float
    status: str  # pending | answered | cancelled | expired
    answer: Optional[str] = None
    answered_at: Optional[str] = None
    approval_action_id: Optional[str] = None
    payload_digest: str = ""
    created_at: str = field(default_factory=_now)
    expires_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def formulate_question_text(action_type: str, payload: Dict[str, Any],
                            calibrated_confidence: float, reason: str) -> str:
    key_fields = ", ".join(f"{k}={str(v)[:40]!r}" for k, v in list(payload.items())[:3]) or "no payload"
    return (
        f"I am only {int(round(calibrated_confidence * 100))}% confident about executing "
        f"'{action_type}' ({key_fields}). {reason} "
        "Should I proceed?"
    )


class OwnerQuestionStore:
    """Persistent, TTL-bound owner questions with dedup by exact action+payload."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "owner_questions.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS owner_questions (
                question_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                question_text TEXT NOT NULL,
                options_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                raw_confidence REAL NOT NULL,
                calibrated_confidence REAL NOT NULL,
                threshold REAL NOT NULL,
                status TEXT NOT NULL,
                answer TEXT,
                answered_at TEXT,
                approval_action_id TEXT,
                payload_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )""")
            conn.commit()

    def _row(self, row: sqlite3.Row) -> OwnerQuestion:
        return OwnerQuestion(
            question_id=row[0], proposal_id=row[1], action_type=row[2],
            payload=json.loads(row[3]), question_text=row[4],
            options=json.loads(row[5]), reason=row[6],
            raw_confidence=float(row[7]), calibrated_confidence=float(row[8]),
            threshold=float(row[9]), status=row[10], answer=row[11],
            answered_at=row[12], approval_action_id=row[13],
            payload_digest=row[14], created_at=row[15], expires_at=row[16],
        )

    def ask(
        self,
        *,
        proposal_id: str,
        action_type: str,
        payload: Dict[str, Any],
        raw_confidence: float,
        calibrated_confidence: float,
        threshold: float,
        reason: str,
        ttl_hours: Optional[int] = None,
    ) -> OwnerQuestion:
        """Record a question; a pending question for the exact same action+payload is returned as-is (dedup)."""
        digest = _payload_digest(action_type, payload)
        ttl = int(ttl_hours if ttl_hours is not None else getattr(settings, "ARENA_QUESTION_TTL_HOURS", 72))
        expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, ttl))).isoformat()
        with self._lock:
            self.expire_stale()
            with sqlite3.connect(self.db_path) as conn:
                existing = conn.execute(
                    "SELECT * FROM owner_questions WHERE payload_digest=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
                    (digest,),
                ).fetchone()
                if existing:
                    return self._row(existing)
            question = OwnerQuestion(
                question_id=f"oq_{uuid4().hex[:14]}",
                proposal_id=proposal_id,
                action_type=action_type,
                payload=dict(payload),
                question_text=formulate_question_text(action_type, payload, calibrated_confidence, reason),
                options=["approve", "deny", "observe"],
                reason=reason,
                raw_confidence=round(float(raw_confidence), 4),
                calibrated_confidence=round(float(calibrated_confidence), 4),
                threshold=round(float(threshold), 4),
                status="pending",
                payload_digest=digest,
                expires_at=expires,
            )
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO owner_questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        question.question_id, question.proposal_id, question.action_type,
                        json.dumps(question.payload, default=str), question.question_text,
                        json.dumps(question.options), question.reason,
                        question.raw_confidence, question.calibrated_confidence, question.threshold,
                        question.status, None, None, None, question.payload_digest,
                        question.created_at, question.expires_at,
                    ),
                )
                conn.commit()
            audit_logger.info(
                "Uncertainty question raised: %s action=%s calibrated=%.2f threshold=%.2f",
                question.question_id, action_type, question.calibrated_confidence, question.threshold,
            )
            return question

    def get(self, question_id: str) -> Optional[OwnerQuestion]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM owner_questions WHERE question_id=?", (question_id,)
            ).fetchone()
        return self._row(row) if row else None

    def list(self, status: Optional[str] = "pending", limit: int = 100) -> List[OwnerQuestion]:
        self.expire_stale()
        q = "SELECT * FROM owner_questions"
        params: List[Any] = []
        if status:
            q += " WHERE status=?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row(r) for r in rows]

    def answer(self, question_id: str, answer: str, note: str = "") -> Dict[str, Any]:
        if answer not in _ANSWERS:
            return {"success": False, "error": f"answer must be one of {sorted(_ANSWERS)}"}
        with self._lock:
            question = self.get(question_id)
            if question is None:
                return {"success": False, "error": "Question not found"}
            if question.status == "expired":
                return {"success": False, "error": "Question expired; re-observation is needed, not an answer"}
            if question.status != "pending":
                return {"success": False, "error": f"Question already {question.status}"}
            approval_action_id = None
            if answer == "approve":
                # Authorization stage ONLY: an exact approval is created; nothing executes.
                from app.cognition.approval_store import approval_store
                request = approval_store.add(
                    conversation_id=f"question:{question.question_id}",
                    action_type=question.action_type,
                    payload=question.payload,
                    reason=f"Owner approved uncertain action via question {question.question_id}: {note or question.reason}",
                    goal_text=f"Uncertain action approved: {question.action_type}",
                )
                approval_action_id = request.action_id
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE owner_questions SET status='answered', answer=?, answered_at=?, approval_action_id=? WHERE question_id=?",
                    (answer, _now(), approval_action_id, question_id),
                )
                conn.commit()
            audit_logger.info(
                "Uncertainty question answered: %s -> %s (approval=%s)",
                question_id, answer, approval_action_id,
            )
            result: Dict[str, Any] = {
                "success": True,
                "question_id": question_id,
                "answer": answer,
                "approval_action_id": approval_action_id,
            }
            if answer == "approve":
                result["note"] = "An exact approval was created; execution remains a separate action."
            elif answer == "observe":
                result["note"] = "Recorded: gather more evidence instead of acting."
            else:
                result["note"] = "Recorded: the action will not proceed from this question."
            return result

    def cancel(self, question_id: str) -> Dict[str, Any]:
        with self._lock:
            question = self.get(question_id)
            if question is None:
                return {"success": False, "error": "Question not found"}
            if question.status != "pending":
                return {"success": False, "error": f"Question already {question.status}"}
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE owner_questions SET status='cancelled' WHERE question_id=?", (question_id,)
                )
                conn.commit()
            return {"success": True, "cancelled": question_id}

    def expire_stale(self) -> int:
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE owner_questions SET status='expired' WHERE status='pending' AND expires_at < ?",
                (now,),
            )
            conn.commit()
        return cursor.rowcount


# Module-level singleton, mirroring the other owner stores.
owner_question_store = OwnerQuestionStore()


def should_ask(
    action_type: str,
    raw_confidence: float,
    *,
    calibrator: Optional[Any] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, float, float]:
    """Decide whether low calibrated confidence should become an owner question.

    Returns (should_ask, calibrated_confidence, threshold).
    """
    enabled = str(getattr(settings, "ARENA_ASK_QUESTIONS_ENABLED", "1")) == "1"
    threshold = float(getattr(settings, "ARENA_ASK_CONFIDENCE_THRESHOLD", 0.45))
    calibrated = float(raw_confidence)
    if calibrator is not None:
        try:
            calibrated = float(calibrator.calibrate(action_type, float(raw_confidence), context))
        except Exception as exc:
            app_logger.warning(f"Confidence calibration unavailable; using raw confidence: {exc}")
    return (enabled and calibrated < threshold), calibrated, threshold
