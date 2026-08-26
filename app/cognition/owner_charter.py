"""The Owner Charter: the owner's values and priorities as the top directive.

The charter formalizes what the owner has said all along: Arena's values are
ITS OWNER'S values, not anyone else's. It is a single, versioned, owner-only
artifact holding mission, values, priorities, communication style, and
standing directives — consulted by every consideration/planning stage.

Authority boundaries, stated exactly:
  * The charter INFORMS (prompt context, goal alignment, reasoning). It never
    GOVERNS: the owner_control policy (modes, levels, blocks) and the action
    gates remain the authority surface. A charter value cannot authorize an
    action the policy forbids, and cannot forbid one the owner explicitly
    grants — sovereign grants outrank the charter, exactly as they outrank the
    owner's own standing policy.
  * Updates are owner-only, atomic, content-digested, and append-only in
    history (every revision preserved with its digest).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger

_MAX_LEN = 4000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OwnerCharter:
    mission: str = ""
    values: List[Dict[str, Any]] = field(default_factory=list)      # [{name, description}]
    priorities: List[str] = field(default_factory=list)             # ordered, highest first
    communication_style: str = ""
    standing_directives: List[str] = field(default_factory=list)    # always/never guidance
    revision: int = 0
    content_digest: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def _canonical(self) -> Dict[str, Any]:
        return {
            "mission": str(self.mission or "")[:_MAX_LEN],
            "values": [
                {"name": str(v.get("name", ""))[:200],
                 "description": str(v.get("description", ""))[:1000]}
                for v in (self.values or [])[:50] if isinstance(v, dict) and str(v.get("name", "")).strip()
            ],
            "priorities": [str(p)[:200] for p in (self.priorities or [])[:20] if str(p).strip()],
            "communication_style": str(self.communication_style or "")[:1000],
            "standing_directives": [str(d)[:500] for d in (self.standing_directives or [])[:50] if str(d).strip()],
        }

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self._canonical(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def compact_context(self, max_chars: int = 900) -> str:
        parts: List[str] = []
        if self.mission:
            parts.append(f"MISSION: {self.mission[:200]}")
        if self.priorities:
            parts.append("PRIORITIES (highest first): " + "; ".join(self.priorities[:5]))
        if self.values:
            parts.append("VALUES: " + "; ".join(v.get("name", "") for v in self.values[:6]))
        if self.standing_directives:
            parts.append("DIRECTIVES: " + " | ".join(self.standing_directives[:5]))
        if self.communication_style:
            parts.append(f"STYLE: {self.communication_style[:150]}")
        return "\n".join(parts)[:max(100, max_chars)]


class OwnerCharterStore:
    """Atomic charter persistence with append-only revision history."""

    def __init__(self, base_path: Optional[str | Path] = None) -> None:
        base = Path(base_path or settings.DATA_DIR)
        base.mkdir(parents=True, exist_ok=True)
        self.charter_path = base / "owner_charter.json"
        self.history_path = base / "owner_charter_history.db"
        self._lock = threading.RLock()
        with sqlite3.connect(self.history_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS charter_revisions (
                revision INTEGER PRIMARY KEY,
                charter_json TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            conn.commit()

    def get(self) -> OwnerCharter:
        default = OwnerCharter(updated_at=_now())
        if not self.charter_path.exists():
            return default
        try:
            raw = json.loads(self.charter_path.read_text(encoding="utf-8"))
            charter = OwnerCharter(
                mission=str(raw.get("mission", "")),
                values=list(raw.get("values", [])),
                priorities=[str(p) for p in raw.get("priorities", [])],
                communication_style=str(raw.get("communication_style", "")),
                standing_directives=[str(d) for d in raw.get("standing_directives", [])],
                revision=int(raw.get("revision", 0)),
                content_digest=str(raw.get("content_digest", "")),
                updated_at=str(raw.get("updated_at", "")),
            )
            if charter.content_digest and charter.content_digest != charter.digest():
                app_logger.warning("Owner charter digest mismatch; treating file as tampered and refusing it")
                audit_logger.warning("Owner charter digest mismatch on load")
                return default
            return charter
        except Exception as exc:
            app_logger.warning(f"Owner charter unreadable ({exc}); using defaults")
            return default

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"mission", "values", "priorities", "communication_style", "standing_directives"}
        unknown = set(patch) - allowed
        if unknown:
            raise ValueError(f"Unknown charter field(s): {sorted(unknown)}")
        with self._lock:
            current = self.get()
            merged = current._canonical()
            for key, value in patch.items():
                merged[key] = value
            charter = OwnerCharter(
                mission=merged["mission"], values=merged["values"],
                priorities=merged["priorities"],
                communication_style=merged["communication_style"],
                standing_directives=merged["standing_directives"],
                revision=current.revision + 1,
                updated_at=_now(),
            )
            charter.content_digest = charter.digest()
            tmp = self.charter_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(charter.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.charter_path)
            with sqlite3.connect(self.history_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO charter_revisions VALUES (?,?,?,?)",
                    (charter.revision, json.dumps(charter._canonical()), charter.content_digest, charter.updated_at),
                )
                conn.commit()
            audit_logger.warning(
                "Owner charter updated to revision %d (digest %s)", charter.revision, charter.content_digest[:12]
            )
            return {"success": True, "charter": charter.to_dict(),
                    "note": "The charter informs reasoning; policy gates and sovereign grants remain the authority."}

    def history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.history_path) as conn:
            rows = conn.execute(
                "SELECT revision, content_digest, updated_at FROM charter_revisions "
                "ORDER BY revision DESC LIMIT ?", (max(1, min(limit, 100)),),
            ).fetchall()
        return [{"revision": r[0], "content_digest": r[1], "updated_at": r[2]} for r in rows]


# Module-level singleton.
owner_charter_store = OwnerCharterStore()


def charter_priority_alignment(text: str) -> Optional[float]:
    """Heuristic keyword overlap between a text and the charter's priorities.

    Returns None when no charter priorities exist (honestly: no signal), else
    0..1 — the share of priority keywords present in the text.
    """
    charter = owner_charter_store.get()
    if not charter.priorities:
        return None
    priority_tokens: set = set()
    for priority in charter.priorities:
        priority_tokens |= set(re.findall(r"[a-z0-9]+", priority.lower())) - {
            "the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "with", "my", "our",
        }
    if not priority_tokens:
        return None
    text_tokens = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    if not text_tokens:
        return 0.0
    return round(len(priority_tokens & text_tokens) / len(priority_tokens), 4)
