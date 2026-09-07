"""Signed owner decisions binding expected system-state changes to authority.

Declaring a change "expected" suppresses identity-discontinuity findings, so a
bare assertion must never be enough: expected changes are only honored when
they reference a valid owner decision. A decision is content-bound
(SHA-256 digest over its canonical type+payload), revocable, and single-use by
default — mirroring the sovereign-grant discipline. The digest is a
tamper-evident binding of this decision to its content, not a cryptographic
signature by a human; "owner" means it is issued through owner-only authority
surfaces.
"""
from __future__ import annotations

import hashlib
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


DECISION_EXPECTED_IDENTITY_CHANGE = "expected_identity_change"
DECISION_ONTOLOGY_SCHEMA_CHANGE = "ontology_schema_change"
DECISION_INCUBATION_AUTHORIZATION = "incubation_authorization"
DECISION_IDENTITY_ADAPTATION = "identity_adaptation"
DECISION_PURPOSE_ADOPTION = "purpose_adoption"
DECISION_TYPES = {
    DECISION_EXPECTED_IDENTITY_CHANGE,
    DECISION_ONTOLOGY_SCHEMA_CHANGE,
    DECISION_INCUBATION_AUTHORIZATION,
    DECISION_IDENTITY_ADAPTATION,
    DECISION_PURPOSE_ADOPTION,
}


def _digest(decision_type: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {"decision_type": decision_type, "payload": payload},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class OwnerDecision:
    decision_id: str
    decision_type: str
    payload: Dict[str, Any]
    status: str  # active | used | revoked
    content_digest: str
    created_at: str
    used_at: Optional[str] = None
    used_by: Optional[str] = None
    revoked_at: Optional[str] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OwnerDecisionStore:
    """Persistent, thread-safe registry of signed owner decisions."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "owner_decisions.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS owner_decisions (
                decision_id TEXT PRIMARY KEY,
                decision_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT,
                used_by TEXT,
                revoked_at TEXT,
                note TEXT NOT NULL DEFAULT ''
            )""")
            conn.commit()

    def _row(self, row: sqlite3.Row) -> OwnerDecision:
        return OwnerDecision(
            decision_id=row[0], decision_type=row[1], payload=json.loads(row[2]),
            status=row[3], content_digest=row[4], created_at=row[5],
            used_at=row[6], used_by=row[7], revoked_at=row[8], note=row[9],
        )

    def _get(self, decision_id: str) -> Optional[OwnerDecision]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM owner_decisions WHERE decision_id=?", (decision_id,)
            ).fetchone()
        return self._row(row) if row else None

    def issue(self, decision_type: str, payload: Dict[str, Any], *, note: str = "") -> OwnerDecision:
        if decision_type not in DECISION_TYPES:
            raise ValueError(f"Unknown decision type: {decision_type}")
        decision = OwnerDecision(
            decision_id=f"od_{uuid4().hex[:16]}",
            decision_type=decision_type,
            payload=dict(payload),
            status="active",
            content_digest=_digest(decision_type, dict(payload)),
            created_at=_now(),
            note=str(note or ""),
        )
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO owner_decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        decision.decision_id, decision.decision_type,
                        json.dumps(decision.payload, default=str), decision.status,
                        decision.content_digest, decision.created_at,
                        None, None, None, decision.note,
                    ),
                )
                conn.commit()
        audit_logger.info(
            f"Owner decision issued: {decision.decision_id} type={decision_type} "
            f"digest={decision.content_digest[:12]}"
        )
        return decision

    def revoke(self, decision_id: str) -> OwnerDecision:
        with self._lock:
            current = self._get(decision_id)
            if current is None:
                raise KeyError(decision_id)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE owner_decisions SET status='revoked', revoked_at=? WHERE decision_id=?",
                    (_now(), decision_id),
                )
                conn.commit()
        audit_logger.warning(f"Owner decision revoked: {decision_id}")
        return self._get(decision_id)  # type: ignore[return-value]

    def validate(
        self,
        decision_id: str,
        *,
        decision_type: str,
        claimed_change_types: Optional[List[str]] = None,
        consume: bool = True,
    ) -> Dict[str, Any]:
        """Validate a decision reference; consume=True marks single-use."""
        result: Dict[str, Any] = {"valid": False, "decision_id": decision_id, "reasons": []}
        reasons: List[str] = result["reasons"]
        with self._lock:
            decision = self._get(decision_id)
            if decision is None:
                reasons.append("unknown_decision")
                return result
            result["decision"] = decision.to_dict()
            if decision.decision_type != decision_type:
                reasons.append("decision_type_mismatch")
            recomputed = _digest(decision.decision_type, decision.payload)
            if recomputed != decision.content_digest:
                reasons.append("content_digest_mismatch")
                return result
            if decision.status == "revoked":
                reasons.append("decision_revoked")
            elif decision.status == "used":
                reasons.append("decision_already_used")
            authorized = decision.payload.get("expected_change_types") or []
            for change_type in claimed_change_types or []:
                if change_type not in authorized:
                    reasons.append(f"change_type_not_authorized:{change_type}")
            if reasons:
                return result
            if consume:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE owner_decisions SET status='used', used_at=? WHERE decision_id=?",
                        (_now(), decision_id),
                    )
                    conn.commit()
            result["valid"] = True
            result["single_use_consumed"] = bool(consume)
            return result

    def list(self, limit: int = 200) -> List[OwnerDecision]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM owner_decisions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [self._row(r) for r in rows]


# Module-level singleton, mirroring the other owner-authority stores.
owner_decision_store = OwnerDecisionStore()
