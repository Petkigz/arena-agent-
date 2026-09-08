"""UnifiedMemory — Phase 5 (Beanie AGI roadmap): one memory system, many kinds.

The roadmap's target::

    MEMORY
    ├── Working          (runtime.working_memory)
    ├── Episodic         (MemoryStore kind=episodic — experiences)
    ├── Semantic         (MemoryStore kind=semantic — facts/concepts)
    ├── Procedural       (MemoryStore kind=procedural — how to do things)
    ├── Social           (NEW: SocialMemoryStore — people/relationships)
    ├── Preference       (runtime.phase7_preferences + user_state — owner prefs)
    ├── Autobiographical (BeanieIdentity milestones — Beanie's own history)
    └── Meta-memory      (NEW: MetaMemory — what she knows about what she knows)

Nothing here replaces the existing stores — the facade is the ONE view over
them, plus the two stores the roadmap says are missing (social, meta).

Meta-memory is the roadmap's key distinction:

    "I remember doing this."            → remembered_done (episodic + success)
    "I think I know how, never did it." → knows_how (procedural/lesson only)
    "I've heard of this."               → heard_about (semantic only)
    "I don't know."                     → unknown — stays unknown honestly
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── SOCIAL MEMORY (people / relationships) ──────────────────────────────────
class SocialMemoryStore:
    """People and relationships as first-class memory (roadmap Phases 5/16).

    Owner-taught and probe-fed; provenance is recorded on every entry.
    Forget is explicit and owner-only (the flag exists so a conversation can
    never erase a person by accident).
    """

    VALID_KINDS = {"person", "organization", "relationship"}

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS beanie_social_memory (
                name TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                relationship TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                provenance TEXT NOT NULL DEFAULT '',
                interactions INTEGER NOT NULL DEFAULT 0,
                last_interaction TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, name: str, kind: str = "person", relationship: str = "",
                 notes: str = "", provenance: str = "owner_taught") -> Dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            return {"success": False, "reason": "empty name"}
        if kind not in self.VALID_KINDS:
            return {"success": False, "reason": f"unknown kind '{kind}'",
                    "valid_kinds": sorted(self.VALID_KINDS)}
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("""INSERT INTO beanie_social_memory
                (name, kind, relationship, notes, provenance, interactions,
                 last_interaction, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  kind = excluded.kind,
                  relationship = excluded.relationship,
                  notes = excluded.notes,
                  provenance = excluded.provenance,
                  updated_at = excluded.updated_at""",
                (name, kind, relationship, notes, provenance, now, now))
            conn.commit()
        return {"success": True, "name": name, "kind": kind}

    def recall(self, name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM beanie_social_memory WHERE name = ?", (str(name).strip(),)
            ).fetchone()
        return dict(row) if row else None

    def list_people(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM beanie_social_memory ORDER BY updated_at DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def record_interaction(self, name: str) -> Dict[str, Any]:
        """Count an interaction and mark its time (relationship maintenance)."""
        now = _now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE beanie_social_memory
                   SET interactions = interactions + 1, last_interaction = ?, updated_at = ?
                   WHERE name = ?""", (now, now, str(name).strip()))
            conn.commit()
            found = cur.rowcount > 0
        return {"success": found,
                **({"reason": f"no social memory of '{name}' — remember them first"} if not found else {"name": name})}

    def forget(self, name: str, confirm_owner: bool = False) -> Dict[str, Any]:
        """Explicit removal. Requires the owner flag — never implicit."""
        if not confirm_owner:
            return {"success": False,
                    "reason": "forgetting a person requires explicit owner confirmation"}
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM beanie_social_memory WHERE name = ?", (str(name).strip(),))
            conn.commit()
        return {"success": True, "name": name}

    def count(self) -> int:
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM beanie_social_memory").fetchone()[0]
        except Exception:
            return 0


# ── META-MEMORY (what she knows about what she knows) ───────────────────────
class MetaMemory:
    """Deterministic classification of her own knowledge state for a query.

    Evidence-based, never fabricated: the classification cites the memory
    records that produced it (content excerpt + provenance), and 'unknown'
    means the stores genuinely returned nothing relevant.
    """

    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def ask(self, query: str, limit: int = 5) -> Dict[str, Any]:
        if self.memory is None:
            return {"status": "unknown", "query": query,
                    "reason": "no memory store wired", "evidence": []}
        hits: Dict[str, List[Dict[str, Any]]] = {
            "episodic_success": [], "procedural": [], "semantic": [], "other": [],
        }
        try:
            records = self.memory.search(str(query), limit=max(limit, 5))
        except Exception as exc:
            return {"status": "unknown", "query": query,
                    "reason": f"memory search failed: {type(exc).__name__}: {exc}",
                    "evidence": []}
        for rec in records:
            excerpt = {
                "memory_id": getattr(rec, "memory_id", None),
                "kind": getattr(rec, "kind", None),
                "content": str(getattr(rec, "content", ""))[:160],
                "source": getattr(rec, "source", None),
                "success": getattr(rec, "success", None),
                "created_at": getattr(rec, "created_at", None),
            }
            kind = getattr(rec, "kind", None)
            if kind == "episodic" and getattr(rec, "success", None) is True:
                hits["episodic_success"].append(excerpt)
            elif kind in ("procedural", "lesson"):
                hits["procedural"].append(excerpt)
            elif kind == "semantic":
                hits["semantic"].append(excerpt)
            else:
                hits["other"].append(excerpt)

        if hits["episodic_success"]:
            status, statement = "remembered_done", "I remember doing this."
        elif hits["procedural"]:
            status, statement = "knows_how", "I think I know how to do this, but I have not actually done it."
        elif hits["semantic"]:
            status, statement = "heard_about", "I have heard of this, but I have no experience with it."
        else:
            status, statement = "unknown", "I don't know."

        evidence = (hits["episodic_success"] + hits["procedural"]
                    + hits["semantic"] + hits["other"])[:limit]
        return {"status": status, "query": str(query), "statement": statement,
                "evidence": evidence,
                "counts": {k: len(v) for k, v in hits.items()}}


# ── THE UNIFIED FACADE ──────────────────────────────────────────────────────
class UnifiedMemory:
    """One view over every memory kind. Stores are injected — the mind wires
    the runtime's real organs; tests wire isolated stores."""

    KINDS = ("working", "episodic", "semantic", "procedural", "lesson",
             "social", "preference", "autobiographical")

    def __init__(self, memory: Any = None, working: Any = None,
                 social: Optional[SocialMemoryStore] = None,
                 identity: Any = None, preferences: Any = None) -> None:
        self.memory = memory          # episodic/semantic/procedural/lesson
        self.working = working        # scratchpad
        self.social = social          # people/relationships
        self.identity = identity      # autobiographical
        self.preferences = preferences  # owner preference engine
        self.meta = MetaMemory(memory)

    # ── typed remembering (single write surface) ─────────────────────────
    def remember(self, kind: str, content: str, *, importance: float = 0.5,
                 source: Optional[str] = None, task_id: Optional[str] = None,
                 tags: Optional[List[str]] = None, outcome: Optional[str] = None,
                 success: Optional[bool] = None) -> Dict[str, Any]:
        """Store a memory through the authoritative store. Unknown kinds are
        rejected typed (the store's own contract surfaces)."""
        if kind == "social":
            return self.social.remember(content, provenance=source or "owner_taught") if self.social else {
                "success": False, "reason": "social store not wired"}
        if self.memory is None:
            return {"success": False, "reason": "memory store not wired"}
        try:
            rec = self.memory.add(kind, content, importance=importance, source=source,
                                  task_id=task_id, tags=tags or [], outcome=outcome,
                                  success=success)
        except ValueError as exc:
            return {"success": False, "reason": str(exc)}
        except Exception as exc:
            return {"success": False, "reason": f"{type(exc).__name__}: {exc}"}
        return {"success": True, "memory_id": getattr(rec, "memory_id", None),
                "kind": kind}

    # ── counts (honest, fail-open per store) ─────────────────────────────
    def _kind_counts(self) -> Dict[str, int]:
        counts = {"episodic": 0, "semantic": 0, "procedural": 0, "lesson": 0}
        if self.memory is None:
            return counts
        try:
            conn = sqlite3.connect(self.memory.db_path, timeout=5)
            try:
                rows = conn.execute(
                    "SELECT kind, COUNT(*) FROM cognitive_memory GROUP BY kind").fetchall()
            finally:
                conn.close()
            counts.update({k: n for k, n in rows})
        except Exception:
            pass
        return counts

    def counts(self) -> Dict[str, Any]:
        kind_counts = self._kind_counts()
        working_items = None
        if self.working is not None:
            try:
                working_items = len(self.working.snapshot(limit=100))
            except Exception:
                working_items = None
        autobiographical = None
        if self.identity is not None:
            try:
                autobiographical = len(self.identity.milestones(limit=1000))
            except Exception:
                autobiographical = None
        return {
            "episodic": kind_counts.get("episodic", 0),
            "semantic": kind_counts.get("semantic", 0),
            "procedural": kind_counts.get("procedural", 0),
            "lesson": kind_counts.get("lesson", 0),
            "working_items": working_items,
            "social": self.social.count() if self.social else None,
            "preference": "wired" if self.preferences is not None else "unwired",
            "autobiographical_milestones": autobiographical,
        }

    def overview(self) -> Dict[str, Any]:
        """The full memory landscape — what exists, where, and how much."""
        return {
            "success": True,
            "stores": {
                "working": "capacity-limited scratchpad (runtime.working_memory)",
                "episodic/semantic/procedural/lesson": "MemoryStore (app/cognition/memory.py)",
                "social": "SocialMemoryStore (people/relationships)",
                "preference": "Phase7PreferenceEngine + owner model",
                "autobiographical": "BeanieIdentity milestones",
                "meta": "MetaMemory — classification of her own knowledge",
            },
            "counts": self.counts(),
        }
