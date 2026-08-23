"""Owner-reviewed continual-learning examples from verified outcomes.

Verified success may propose a candidate, but it never enters a LoRA dataset
until the owner reviews and approves the exact redacted prompt/response pair.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrainingExampleStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"


@dataclass
class TrainingExampleCandidate:
    candidate_id: str
    skill_name: str
    prompt: str
    response: str
    action_type: str
    status: TrainingExampleStatus
    source_type: str
    source_session_id: str
    source_trace_id: str
    verification_reason: str
    evidence: List[str]
    redactions: List[str]
    content_hash: str
    created_at: str
    updated_at: str
    review_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


_SECRET_PATTERNS = [
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}")),
    (
        "named_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|password|passwd|secret)\b"
            r"\s*[:=]\s*([^\s,;]+)"
        ),
    ),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("home_path", re.compile(r"(?i)(?:/home/|[a-z]:\\users\\)[^/\\\s]+")),
    ("phone", re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")),
]


def redact_training_text(text: str) -> tuple[str, List[str]]:
    redacted = str(text or "")[:8000]
    applied: List[str] = []
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(redacted):
            applied.append(name)
            if name == "named_secret":
                redacted = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
            elif name == "home_path":
                redacted = pattern.sub("/home/<user>", redacted)
            else:
                redacted = pattern.sub(f"<{name}_redacted>", redacted)
    return redacted.strip(), sorted(set(applied))


def _safe_skill(value: str) -> str:
    cleaned = "".join(
        character for character in str(value).strip().lower()
        if character.isalnum() or character in ("_", "-")
    ).strip("_-")
    return cleaned or "general"


def _content_hash(skill: str, prompt: str, response: str) -> str:
    canonical = json.dumps(
        {"skill": skill, "prompt": prompt, "response": response},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TrainingExampleStore:
    MIN_APPROVED_FOR_EXPORT = 5

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "training_examples.db"))
        self._lock = threading.RLock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_example_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    skill_name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_session_id TEXT NOT NULL DEFAULT '',
                    source_trace_id TEXT NOT NULL DEFAULT '',
                    verification_reason TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    redactions_json TEXT NOT NULL DEFAULT '[]',
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    review_note TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_training_candidates_status_skill "
                "ON training_example_candidates(status, skill_name)"
            )
            conn.commit()

    @staticmethod
    def _row(row: sqlite3.Row) -> TrainingExampleCandidate:
        return TrainingExampleCandidate(
            candidate_id=row[0], skill_name=row[1], prompt=row[2], response=row[3],
            action_type=row[4], status=TrainingExampleStatus(row[5]), source_type=row[6],
            source_session_id=row[7], source_trace_id=row[8], verification_reason=row[9],
            evidence=list(json.loads(row[10] or "[]")),
            redactions=list(json.loads(row[11] or "[]")), content_hash=row[12],
            created_at=row[13], updated_at=row[14], review_note=row[15],
        )

    def _count_status(self, status: TrainingExampleStatus) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM training_example_candidates WHERE status = ?",
                (status.value,),
            ).fetchone()[0])

    def _get_by_hash(self, content_hash: str) -> Optional[TrainingExampleCandidate]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM training_example_candidates WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            return self._row(row) if row else None

    def get(self, candidate_id: str) -> Optional[TrainingExampleCandidate]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM training_example_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            return self._row(row) if row else None

    def propose_verified(
        self,
        *,
        prompt: str,
        response: str,
        action_type: str,
        verification_result: Any,
        source_session_id: str = "",
        source_trace_id: str = "",
        skill_name: Optional[str] = None,
    ) -> Optional[TrainingExampleCandidate]:
        if getattr(verification_result, "verified_success", False) is not True:
            return None
        if str(response).startswith("[Simulated Response"):
            return None
        prompt_clean, prompt_redactions = redact_training_text(prompt)
        response_clean, response_redactions = redact_training_text(response)
        if len(prompt_clean) < 3 or len(response_clean) < 3:
            return None
        skill = _safe_skill(skill_name or action_type)
        digest = _content_hash(skill, prompt_clean, response_clean)
        existing = self._get_by_hash(digest)
        if existing:
            return existing
        if self._count_status(TrainingExampleStatus.PENDING) >= 500:
            audit_logger.warning("LoRA candidate queue is full (500 pending); skipping proposal")
            return None

        evidence = [str(item) for item in getattr(verification_result, "met_conditions", [])]
        reason = str(getattr(verification_result, "verification_reason", ""))[:1000]
        now = _now()
        candidate = TrainingExampleCandidate(
            candidate_id=f"train_{uuid4().hex[:12]}",
            skill_name=skill,
            prompt=prompt_clean,
            response=response_clean,
            action_type=str(action_type),
            status=TrainingExampleStatus.PENDING,
            source_type="verified_outcome",
            source_session_id=source_session_id,
            source_trace_id=source_trace_id,
            verification_reason=reason,
            evidence=evidence,
            redactions=sorted(set(prompt_redactions + response_redactions)),
            content_hash=digest,
            created_at=now,
            updated_at=now,
        )
        self._save(candidate)
        audit_logger.info(
            f"LoRA candidate proposed from verified outcome: {candidate.candidate_id} "
            f"skill={candidate.skill_name} redactions={candidate.redactions}"
        )
        return candidate

    def propose_owner_correction(
        self,
        *,
        prompt: str,
        response: str,
        skill_name: str,
        note: str = "",
    ) -> Optional[TrainingExampleCandidate]:
        prompt_clean, prompt_redactions = redact_training_text(prompt)
        response_clean, response_redactions = redact_training_text(response)
        if len(prompt_clean) < 3 or len(response_clean) < 3:
            return None
        skill = _safe_skill(skill_name)
        digest = _content_hash(skill, prompt_clean, response_clean)
        existing = self._get_by_hash(digest)
        if existing:
            return existing
        now = _now()
        candidate = TrainingExampleCandidate(
            candidate_id=f"train_{uuid4().hex[:12]}",
            skill_name=skill,
            prompt=prompt_clean,
            response=response_clean,
            action_type="owner_correction",
            status=TrainingExampleStatus.PENDING,
            source_type="owner_correction",
            source_session_id="",
            source_trace_id="",
            verification_reason="Explicit owner-provided correction",
            evidence=["owner_correction"],
            redactions=sorted(set(prompt_redactions + response_redactions)),
            content_hash=digest,
            created_at=now,
            updated_at=now,
            review_note=note,
        )
        self._save(candidate)
        return candidate

    def _save(self, candidate: TrainingExampleCandidate) -> None:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO training_example_candidates VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                candidate.candidate_id, candidate.skill_name, candidate.prompt,
                candidate.response, candidate.action_type, candidate.status.value,
                candidate.source_type, candidate.source_session_id,
                candidate.source_trace_id, candidate.verification_reason,
                json.dumps(candidate.evidence), json.dumps(candidate.redactions),
                candidate.content_hash, candidate.created_at, candidate.updated_at,
                candidate.review_note,
            ))
            conn.commit()

    def list(
        self,
        *,
        status: Optional[TrainingExampleStatus] = None,
        skill_name: Optional[str] = None,
        limit: int = 200,
    ) -> List[TrainingExampleCandidate]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM training_example_candidates ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        candidates = [self._row(row) for row in rows]
        if status:
            candidates = [item for item in candidates if item.status == status]
        if skill_name:
            skill = _safe_skill(skill_name)
            candidates = [item for item in candidates if item.skill_name == skill]
        return candidates

    def edit(
        self,
        candidate_id: str,
        *,
        prompt: str,
        response: str,
        skill_name: str,
        note: str = "",
    ) -> TrainingExampleCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate.status not in (TrainingExampleStatus.PENDING, TrainingExampleStatus.REJECTED):
            raise ValueError(f"Cannot edit a {candidate.status.value} candidate")
        prompt_clean, prompt_redactions = redact_training_text(prompt)
        response_clean, response_redactions = redact_training_text(response)
        if len(prompt_clean) < 3 or len(response_clean) < 3:
            raise ValueError("Prompt and response must each contain at least 3 characters")
        candidate.prompt = prompt_clean
        candidate.response = response_clean
        candidate.skill_name = _safe_skill(skill_name)
        candidate.redactions = sorted(set(prompt_redactions + response_redactions))
        candidate.content_hash = _content_hash(
            candidate.skill_name, candidate.prompt, candidate.response
        )
        duplicate = self._get_by_hash(candidate.content_hash)
        if duplicate and duplicate.candidate_id != candidate.candidate_id:
            raise ValueError(f"Duplicate of candidate {duplicate.candidate_id}")
        candidate.status = TrainingExampleStatus.PENDING
        candidate.updated_at = _now()
        candidate.review_note = note
        self._save(candidate)
        return candidate

    def decide(
        self, candidate_id: str, approved: bool, note: str = ""
    ) -> TrainingExampleCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate.status != TrainingExampleStatus.PENDING:
            raise ValueError(f"Candidate is already {candidate.status.value}")
        candidate.status = (
            TrainingExampleStatus.APPROVED if approved else TrainingExampleStatus.REJECTED
        )
        candidate.review_note = note
        candidate.updated_at = _now()
        self._save(candidate)
        audit_logger.info(
            f"Owner {candidate.status.value} LoRA candidate {candidate.candidate_id}"
        )
        return candidate

    def export_approved(self, skill_name: str) -> Dict[str, Any]:
        skill = _safe_skill(skill_name)
        approved = [
            item for item in self.list(skill_name=skill, limit=1000)
            if item.status in (
                TrainingExampleStatus.APPROVED,
                TrainingExampleStatus.EXPORTED,
            )
        ]
        if len(approved) < self.MIN_APPROVED_FOR_EXPORT:
            return {
                "success": False,
                "error": (
                    f"At least {self.MIN_APPROVED_FOR_EXPORT} approved unique examples are required; "
                    f"found {len(approved)} for skill '{skill}'."
                ),
                "approved_count": len(approved),
            }
        from app.tools.lora_manager import LoraManagerTool
        result = LoraManagerTool.prepare_dataset(
            skill,
            [
                {
                    "prompt": item.prompt,
                    "response": item.response,
                    "candidate_id": item.candidate_id,
                    "source_type": item.source_type,
                }
                for item in approved
            ],
        )
        if result.get("success"):
            for candidate in approved:
                candidate.status = TrainingExampleStatus.EXPORTED
                candidate.updated_at = _now()
                self._save(candidate)
            result["candidate_ids"] = [item.candidate_id for item in approved]
        return result


training_example_store = TrainingExampleStore()
