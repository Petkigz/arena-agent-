"""CuriosityEngine — Phase 9 (Beanie AGI roadmap): the internal UNKNOWN
system.

The roadmap behavior: she encounters something unfamiliar — "I don't
understand X" — and instead of immediately asking the owner, she registers
the UNKNOWN and tries to close it herself first: revisit previous memories,
compare what she finds, and only then surface it to the owner. Uncertainty
goes down, knowledge goes up — and both movements are COUNTED, not claimed.

Where unknowns come from (all deterministic):
- world-first briefs already compute gaps ("not yet in world model") at the
  door — every gap is registered here automatically;
- the owner (or any surface) can register one explicitly;
- knowledge arriving through the Phase-6 door (BeanieMind.learn) is checked
  against open unknowns and RESOLVES them when it actually overlaps —
  uncertainty ↓ measured as ledger state, not vibes.

Resolution paths (each counted separately):
- ``knowledge``   — new experience/knowledge matched the unknown;
- ``investigation`` — she searched her own memory and found real evidence;
- ``owner``       — the owner answered.

Honesty rules:
- an unknown with no memory evidence stays OPEN — it is never wished away;
  the engine then says the next honest move is to ask the owner;
- encounters compound: meeting the same unknown again raises its priority
  (repeated ignorance matters more than one-off ignorance);
- every counter is a ledger fact, inspectable by the owner.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(topic: str) -> str:
    """Normalize a topic so 'The Document' and 'the document' are ONE
    unknown."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(topic).lower())).strip()


# question words / adverbs / pronouns are not unknowns — gap extraction can
# emit them, and registering them would turn noise into "curiosity"
_FILLER = frozenset({
    "really", "just", "very", "quite", "actually", "where", "what", "when",
    "which", "who", "whom", "how", "why", "is", "are", "was", "were", "be",
    "been", "my", "your", "me", "it", "its", "do", "does", "did", "there",
    "here", "now", "then", "so", "if", "of", "to", "in", "on", "at", "by",
    "about", "as", "or", "no", "yes", "please", "some", "any",
})


class CuriosityEngine:
    """The UNKNOWN ledger and its deterministic resolution paths."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_unknowns (
                    unknown_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    topic_key TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    context TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    times_encountered INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'open',
                    resolution_path TEXT,
                    resolution TEXT,
                    resolved_at TEXT
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Unknown ledger unavailable: {exc}")

    # ── registration: ignorance becomes a record ─────────────────────────
    def register(self, topic: str, source: str = "unspecified",
                 context: str = "") -> Dict[str, Any]:
        topic = str(topic or "").strip()
        source = str(source or "unspecified").strip() or "unspecified"
        if not topic:
            return {"success": False, "reason": "unknown has no topic"}
        key = _key(topic)
        if not key:
            return {"success": False, "reason": "unknown has no topic"}
        substantive = [t for t in _terms(topic) if t not in _FILLER]
        if not substantive:
            return {"success": False,
                    "reason": f"topic '{topic[:60]}' has no substantive "
                              "content — noise is not curiosity"}
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=5)
                try:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM beanie_unknowns WHERE topic_key=?",
                        (key,)).fetchone()
                    if row and row["status"] == "open":
                        # encounters compound: repeated ignorance matters more
                        conn.execute(
                            "UPDATE beanie_unknowns SET times_encountered = "
                            "times_encountered + 1, last_seen=?, context=?"
                            " WHERE topic_key=?",
                            (_now_iso(), str(context or "")[:200], key))
                        conn.commit()
                        fresh = conn.execute(
                            "SELECT * FROM beanie_unknowns WHERE topic_key=?",
                            (key,)).fetchone()
                        return {"success": True, "registered": False,
                                "encounter": True, **dict(fresh)}
                    if row:  # resolved before → re-encountering reopens it
                        conn.execute(
                            "UPDATE beanie_unknowns SET status='open',"
                            " resolution_path=NULL, resolution=NULL,"
                            " resolved_at=NULL, times_encountered = "
                            "times_encountered + 1, last_seen=?"
                            " WHERE topic_key=?", (_now_iso(), key))
                        conn.commit()
                        return {"success": True, "registered": False,
                                "reopened": True, "topic": row["topic"]}
                    conn.execute(
                        """INSERT INTO beanie_unknowns
                           (topic, topic_key, source, context, first_seen,
                            last_seen) VALUES (?, ?, ?, ?, ?, ?)""",
                        (topic[:200], key, source[:120],
                         str(context or "")[:200], _now_iso(), _now_iso()))
                    conn.commit()
                    return {"success": True, "registered": True,
                            "topic": topic, "source": source}
                finally:
                    conn.close()
            except Exception as exc:
                return {"success": False,
                        "reason": f"unknown ledger unavailable: {exc}"}

    # ── knowledge arriving through the door can close unknowns ───────────
    def notify_knowledge(self, content: str) -> List[Dict[str, Any]]:
        """Deterministic match: an open unknown resolves only when the new
        knowledge actually overlaps it (≥2 shared terms for multi-word
        topics, ≥1 for single-word topics, or the full topic phrase present).
        Never wished away."""
        content_l = str(content or "").lower()
        content_terms = set(_terms(content_l))
        resolved: List[Dict[str, Any]] = []
        for row in self._rows(
                "SELECT * FROM beanie_unknowns WHERE status='open'"):
            topic_terms = set(_terms(row["topic"]))
            if not topic_terms:
                continue
            overlap = topic_terms & content_terms
            need = 1 if len(topic_terms) == 1 else 2
            if len(overlap) < need and \
                    row["topic"].lower() not in content_l:
                continue
            self._set_resolved(row["topic_key"], "knowledge",
                               f"matched incoming knowledge: "
                               f"{str(content)[:160]}")
            resolved.append({"topic": row["topic"],
                             "path": "knowledge",
                             "times_encountered": row["times_encountered"]})
        return resolved

    # ── investigate: revisit her own memory FIRST ────────────────────────
    def investigate(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """The roadmap's first move: before asking, search what she already
        knows. Real evidence closes the unknown; no evidence keeps it OPEN
        with the next honest step named."""
        with self._lock:
            if topic:
                row = self._find_open(topic)
            else:
                row = self._top_open()
            if row is None:
                return {"success": False,
                        "reason": "nothing open to investigate"}
            evidence = self._memory_evidence(row["topic"])
            if evidence:
                self._set_resolved(row["topic_key"], "investigation",
                                   "memory evidence: " +
                                   " | ".join(e["content"][:80]
                                              for e in evidence[:2]))
                return {"success": True, "topic": row["topic"],
                        "resolved": True, "path": "investigation",
                        "evidence": evidence[:3]}
            return {"success": True, "topic": row["topic"],
                    "resolved": False, "evidence": [],
                    "next_honest_step":
                        "no memory evidence — ask the owner when convenient"}

    def _memory_evidence(self, topic: str) -> List[Dict[str, Any]]:
        """Same evidence gate as the learning loop: search is recall-broad,
        verdicts need real term overlap (or the exact topic phrase)."""
        memory = getattr(self.mind.memory, "memory", None)
        if memory is None:
            return []
        try:
            records = memory.search(topic, limit=5)
        except Exception:
            return []
        topic_terms = set(_terms(topic))
        out: List[Dict[str, Any]] = []
        for r in records:
            rec_content = str(getattr(r, "content", ""))
            rec_terms = set(_terms(rec_content))
            if not (topic_terms & rec_terms
                    or topic.lower() in rec_content.lower()):
                continue
            out.append({"memory_id": getattr(r, "memory_id", None),
                        "kind": getattr(r, "kind", None),
                        "content": rec_content[:160]})
        return out

    # ── owner answers ────────────────────────────────────────────────────
    def resolve(self, topic: str, answer: str,
                source: str = "owner") -> Dict[str, Any]:
        topic = str(topic or "").strip()
        answer = str(answer or "").strip()
        if not topic or not answer:
            return {"success": False,
                    "reason": "resolving needs both topic and answer"}
        row = self._find_open(topic)
        if row is None:
            return {"success": False,
                    "reason": f"no open unknown matching '{topic[:80]}'"}
        self._set_resolved(row["topic_key"], source, answer[:400])
        return {"success": True, "topic": row["topic"], "path": source}

    # ── surfaces ─────────────────────────────────────────────────────────
    def curiosities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Open unknowns by priority: encounters first, recency second."""
        return self._rows(
            "SELECT unknown_id, topic, source, context, first_seen,"
            " last_seen, times_encountered FROM beanie_unknowns"
            " WHERE status='open' ORDER BY times_encountered DESC,"
            " last_seen DESC LIMIT ?", (int(limit),))

    def stats(self) -> Dict[str, Any]:
        total = open_n = resolved_n = 0
        by_path: Dict[str, int] = {}
        for row in self._rows(
                "SELECT status, resolution_path FROM beanie_unknowns"):
            total += 1
            if row["status"] == "open":
                open_n += 1
            else:
                resolved_n += 1
                path = row["resolution_path"] or "unknown"
                by_path[path] = by_path.get(path, 0) + 1
        return {"total_unknowns": total, "open": open_n,
                "resolved": resolved_n, "resolved_by": by_path,
                "policy": "unknown → investigate memory → ask owner "
                          "(never guess, never hide)"}

    # ── internals ────────────────────────────────────────────────────────
    def _set_resolved(self, topic_key: str, path: str, resolution: str) -> None:
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=5) as conn:
                    conn.execute(
                        "UPDATE beanie_unknowns SET status='resolved',"
                        " resolution_path=?, resolution=?, resolved_at=?"
                        " WHERE topic_key=?",
                        (path, resolution, _now_iso(), topic_key))
                    conn.commit()
            except Exception as exc:
                app_logger.warning(f"Could not record resolution: {exc}")

    def _find_open(self, topic: str) -> Optional[Dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM beanie_unknowns WHERE status='open' AND topic_key=?",
            (_key(topic),))
        return rows[0] if rows else None

    def _top_open(self) -> Optional[Dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM beanie_unknowns WHERE status='open'"
            " ORDER BY times_encountered DESC, last_seen DESC LIMIT 1")
        return rows[0] if rows else None

    def _rows(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception:
            return []
