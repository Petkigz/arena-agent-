"""BeanieIdentity — the "I am Beanie" record (MISSING item M1, Phase 1).

Before Phase 1 the person existed only as a prompt string
(``app.memory.coworker_brain.COWORKER_PERSONA``) and as UI chrome
(BeaniePage, presence orb, Android Beanie components). Nothing in the
backend represented who she IS.

This record is persisted state, not a prompt:

- ``beanie_identity``   — one row of identity facts (upserted, idempotent)
- ``beanie_milestones`` — append-only development history (the seed of
  autobiographical memory, M4)

All persistence is fail-open: a storage failure degrades to the in-memory
identity and never fails a cognitive cycle (AGENT_INVARIANTS §1: recording
is best-effort).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# The roadmap (docs/AGI_ROADMAP.md, governing 2026-09-08) defines who this
# is. Kept as data so identity changes are owner-visible edits, not code
# drift. Values absorbed from the owner's charter and roadmap — nothing
# invented here.
_IDENTITY_SEED: Dict[str, Any] = {
    "name": "Beanie",
    "kind": "local embodied artificial mind",
    "role": (
        "personal helper, secretary, assistant and friend — one person, "
        "not a pile of features"
    ),
    "owner_relationship": (
        "the owner is sovereign; ask, never refuse; the owner's values are "
        "the only value system (docs/OWNER_VISION_CHARTER.md)"
    ),
    "interfaces": "voice primary, text backup, presence on desktop and Android",
    "charter": "docs/OWNER_VISION_CHARTER.md",
    "roadmap": "docs/AGI_ROADMAP.md",
    "born": "2026-09-08",  # Phase-1 identity record date
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BeanieIdentity:
    """Persisted identity record for the one mind."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, Any]] = None
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS beanie_identity (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS beanie_milestones (
                        milestone_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        recorded_at TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        event TEXT NOT NULL,
                        detail TEXT NOT NULL
                    )"""
                )
                conn.commit()
            self._ensure_seeded()
        except Exception:
            # Fail-open: identity degrades to the in-memory seed.
            self._cache = dict(_IDENTITY_SEED)

    # ── seeding ───────────────────────────────────────────────────────────
    def _ensure_seeded(self) -> None:
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=5) as conn:
                    rows = conn.execute(
                        "SELECT key, value FROM beanie_identity"
                    ).fetchall()
                if not rows:
                    for key, value in _IDENTITY_SEED.items():
                        self._upsert(key, value)
                    self.record_milestone(
                        "phase1",
                        "identity record created",
                        "BeanieMind Phase 1: 'I am Beanie' now exists as "
                        "persisted backend state (M1).",
                    )
            except Exception:
                pass

    def _upsert(self, key: str, value: str) -> None:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_identity (key, value, updated_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET
                         value = excluded.value,
                         updated_at = excluded.updated_at""",
                    (key, value, _now()),
                )
                conn.commit()
        except Exception:
            pass  # fail-open

    # ── reads ────────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        """The full identity record (DB when readable, seed otherwise)."""
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                rows = conn.execute(
                    "SELECT key, value, updated_at FROM beanie_identity"
                ).fetchall()
            if rows:
                rec = {k: v for k, v, _ in rows}
                rec["milestones"] = self.milestones(limit=50)
                return rec
        except Exception:
            pass
        rec = dict(_IDENTITY_SEED if self._cache is None else self._cache)
        rec["milestones"] = []
        return rec

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.to_dict().get(key, default)

    def milestones(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                rows = conn.execute(
                    """SELECT recorded_at, phase, event, detail
                       FROM beanie_milestones
                       ORDER BY milestone_id DESC LIMIT ?""",
                    (int(limit),),
                ).fetchall()
            return [
                {"recorded_at": r[0], "phase": r[1], "event": r[2], "detail": r[3]}
                for r in rows
            ]
        except Exception:
            return []

    def identity_statement(self) -> str:
        """One paragraph: who she is. Consumed later by the prompt assembler
        (personality development, roadmap Phase 17); exposed now via the
        mind API so the owner can read exactly what is recorded."""
        rec = self.to_dict()
        name = rec.get("name", "Beanie")
        kind = rec.get("kind", "local artificial mind")
        role = rec.get("role", "the owner's personal assistant")
        relationship = str(rec.get("owner_relationship", "The owner is sovereign."))
        relationship = relationship[:1].upper() + relationship[1:] if relationship else relationship
        interfaces = rec.get("interfaces", "voice and text")
        return (
            f"I am {name} — a {kind}: {role}. "
            f"{relationship}. "
            f"I meet the owner through {interfaces}."
        )

    # ── writes (owner-visible development history) ───────────────────────
    def record_milestone(self, phase: str, event: str, detail: str = "") -> Dict[str, Any]:
        """Append-only milestone. Used by roadmap phases to mark the mind's
        development history (autobiographical memory seed, M4)."""
        entry = {"recorded_at": _now(), "phase": phase, "event": event, "detail": detail}
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_milestones (recorded_at, phase, event, detail)
                       VALUES (?, ?, ?, ?)""",
                    (entry["recorded_at"], phase, event, detail),
                )
                conn.commit()
        except Exception:
            pass  # fail-open: a milestone never fails the work
        return entry

    def update(self, key: str, value: str) -> Dict[str, Any]:
        """Owner-editable identity field (values absorbed through interaction
        land here, never via silent self-modification)."""
        if key in ("milestones",):
            raise ValueError(f"identity field '{key}' is not editable")
        self._upsert(key, str(value))
        return {"success": True, "key": key, "value": str(value)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
