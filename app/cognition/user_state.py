"""Versioned owner state with explicit provenance.

This store keeps personalization separate from world observations. A value is
never treated as an owner preference merely because a model inferred it:
explicit owner statements take precedence over inferred values, retain their
provenance, and are preserved in append-only history.
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

from app.config import settings
from app.utils.logger import audit_logger


SOURCE_TYPES = frozenset({
    "explicit_owner",
    "owner_observed",
    "inferred",
    "recalled",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_evidence(items: Optional[List[Any]]) -> List[str]:
    result: List[str] = []
    for item in items or []:
        value = str(item).strip()
        if value and value not in result:
            result.append(value[:240])
    return result[:50]


@dataclass(frozen=True)
class UserStateAttribute:
    key: str
    value: Any
    source_type: str
    confidence: float
    evidence_ids: List[str]
    version: int
    updated_at: str
    expires_at: Optional[str] = None
    affects_action_selection: bool = False
    state_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UserStateStore:
    """SQLite-backed, versioned user-state attributes."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "user_state.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS user_state_current (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                affects_action_selection INTEGER NOT NULL DEFAULT 0,
                state_id TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS user_state_history (
                key TEXT NOT NULL,
                version INTEGER NOT NULL,
                state_id TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                affects_action_selection INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key, version)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_state_history_key ON user_state_history(key, version DESC)")
            conn.commit()

    @staticmethod
    def _validate_key(key: str) -> str:
        value = str(key or "").strip().lower()
        if not value or len(value) > 160:
            raise ValueError("user state key must be 1-160 characters")
        return value

    @staticmethod
    def _validate_source(source_type: str) -> str:
        value = str(source_type or "").strip().lower()
        if value not in SOURCE_TYPES:
            raise ValueError(f"unsupported user state source_type: {value or '<empty>'}")
        return value

    @staticmethod
    def _record_from_row(row: sqlite3.Row | tuple) -> UserStateAttribute:
        # Works with the default tuple row factory and keeps this store easy to
        # inspect from small local scripts.
        return UserStateAttribute(
            key=row[0],
            value=json.loads(row[1]),
            source_type=row[2],
            confidence=float(row[3]),
            evidence_ids=list(json.loads(row[4]) or []),
            version=int(row[5]),
            updated_at=row[6],
            expires_at=row[7],
            affects_action_selection=bool(row[8]),
            state_id=row[9],
        )

    @staticmethod
    def _expired(record: UserStateAttribute, now: Optional[datetime] = None) -> bool:
        if not record.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(record.expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            return current >= expiry
        except (TypeError, ValueError, OverflowError):
            # A malformed expiry must not silently extend a belief's life.
            return True

    def get(self, key: str, *, include_expired: bool = True) -> Optional[Dict[str, Any]]:
        key = self._validate_key(key)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT key, value_json, source_type, confidence, evidence_json, version, "
                "updated_at, expires_at, affects_action_selection, state_id "
                "FROM user_state_current WHERE key=?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        record = self._record_from_row(row)
        expired = self._expired(record)
        if expired and not include_expired:
            return None
        payload = record.to_dict()
        payload["is_expired"] = expired
        return payload

    def set_attribute(
        self,
        key: str,
        value: Any,
        *,
        source_type: str,
        confidence: float = 1.0,
        evidence_ids: Optional[List[Any]] = None,
        expires_at: Optional[str] = None,
        affects_action_selection: bool = False,
    ) -> Dict[str, Any]:
        """Set a state value or preserve a stronger explicit owner value."""
        key = self._validate_key(key)
        source_type = self._validate_source(source_type)
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("user state confidence must be between 0 and 1")
        evidence = _normalise_evidence(evidence_ids)
        if not evidence:
            raise ValueError("user state updates require evidence_ids")
        if expires_at:
            # Validate at write time; malformed expiry is unsafe for a state
            # value that may affect future tone or action selection.
            datetime.fromisoformat(str(expires_at))

        with self._lock, sqlite3.connect(self.db_path) as conn:
            current_row = conn.execute(
                "SELECT key, value_json, source_type, confidence, evidence_json, version, "
                "updated_at, expires_at, affects_action_selection, state_id "
                "FROM user_state_current WHERE key=?",
                (key,),
            ).fetchone()
            current = self._record_from_row(current_row) if current_row else None
            if (
                current
                and current.source_type == "explicit_owner"
                and source_type != "explicit_owner"
                and not self._expired(current)
            ):
                return {
                    "success": False,
                    "updated": False,
                    "reason": "explicit owner state takes precedence over inferred or recalled state",
                    "current": current.to_dict(),
                }

            version = (current.version + 1) if current else 1
            state_id = f"user_state_{uuid4().hex[:14]}"
            updated_at = _now()
            value_json = json.dumps(value, ensure_ascii=False, default=str)
            evidence_json = json.dumps(evidence, ensure_ascii=False)
            row_values = (
                key, value_json, source_type, confidence, evidence_json,
                version, updated_at, expires_at, int(bool(affects_action_selection)), state_id,
            )
            conn.execute(
                "INSERT OR REPLACE INTO user_state_current VALUES (?,?,?,?,?,?,?,?,?,?)",
                row_values,
            )
            conn.execute(
                "INSERT INTO user_state_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    key, version, state_id, value_json, source_type, confidence,
                    evidence_json, updated_at, expires_at, int(bool(affects_action_selection)),
                ),
            )
            conn.commit()

        record = UserStateAttribute(
            key=key,
            value=value,
            source_type=source_type,
            confidence=confidence,
            evidence_ids=evidence,
            version=version,
            updated_at=updated_at,
            expires_at=expires_at,
            affects_action_selection=bool(affects_action_selection),
            state_id=state_id,
        )
        audit_logger.info(
            "User state updated: key=%s version=%d source=%s",
            key, version, source_type,
        )
        return {"success": True, "updated": True, "state": record.to_dict()}

    def history(self, key: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        params: List[Any] = []
        query = (
            "SELECT key, value_json, source_type, confidence, evidence_json, version, "
            "updated_at, expires_at, affects_action_selection, state_id "
            "FROM user_state_history"
        )
        if key is not None:
            query += " WHERE key=?"
            params.append(self._validate_key(key))
        query += " ORDER BY updated_at DESC, version DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._record_from_row(row).to_dict() for row in rows]

    def snapshot(self, *, include_expired: bool = False) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT key, value_json, source_type, confidence, evidence_json, version, "
                "updated_at, expires_at, affects_action_selection, state_id "
                "FROM user_state_current ORDER BY key"
            ).fetchall()
        attributes = []
        for row in rows:
            record = self._record_from_row(row)
            if self._expired(record) and not include_expired:
                continue
            payload = record.to_dict()
            payload["is_expired"] = self._expired(record)
            attributes.append(payload)
        return {
            "success": True,
            "state_version": max((item["version"] for item in attributes), default=0),
            "attributes": attributes,
            "note": "User state is evidence-linked; explicit owner statements outrank inference.",
        }

    def compact_context(self, max_chars: int = 700) -> str:
        """Render only non-expired state as bounded reasoning context."""
        attributes = self.snapshot()["attributes"]
        attributes.sort(key=lambda item: (item["source_type"] != "explicit_owner", item["key"]))
        lines = []
        for item in attributes:
            value = json.dumps(item["value"], ensure_ascii=False, default=str)
            source = item["source_type"]
            lines.append(f"{item['key']}={value} [{source}; confidence={item['confidence']:.2f}]")
        return "OWNER STATE (evidence-linked):\n" + "\n".join(lines)[:max_chars] if lines else ""


# Shared local-first store for the runtime and owner-control API.
user_state_store = UserStateStore()
