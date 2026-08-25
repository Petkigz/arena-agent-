"""Phase 4: lightweight persistent episodic, semantic, and procedural memory."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_CONCEPT_ALIASES = {
    "chrome": "browser",
    "firefox": "browser",
    "edge": "browser",
    "crash": "failure",
    "crashed": "failure",
    "failed": "failure",
    "error": "failure",
    "opened": "launch",
    "open": "launch",
    "started": "launch",
    "find": "search",
    "located": "search",
    "document": "file",
    "documents": "file",
    "files": "file",
}


def _memory_terms(text: str) -> set[str]:
    """Deterministic low-cost concept normalization for local retrieval."""
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) > 4:
            for suffix in ("ing", "ed", "es", "s"):
                if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                    token = token[:-len(suffix)]
                    break
        terms.add(token)
        alias = _CONCEPT_ALIASES.get(token)
        if alias:
            terms.add(alias)
    return terms


def _character_ngrams(text: str, size: int = 3) -> set[str]:
    compact = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index:index + size] for index in range(len(compact) - size + 1)}


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    kind: str
    content: str
    importance: float
    created_at: str
    last_accessed: str
    access_count: int
    source: Optional[str] = None
    task_id: Optional[str] = None
    tags: tuple[str, ...] = ()
    outcome: Optional[str] = None
    success: Optional[bool] = None


class MemoryStore:
    """SQLite-backed memory with bounded retrieval and explicit maintenance."""
    VALID_KINDS = {"episodic", "semantic", "procedural", "lesson"}

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._init_db()
        self._associative = None  # opt-in vector index (enable_associative)

    def enable_associative(self, index=None, backfill_limit: int = 20000) -> bool:
        """Layer vector-associative recall over lexical search (best-effort).

        Backfills existing records and indexes new ones on add(). Failures are
        logged and leave lexical search fully functional — never fatal.
        """
        try:
            from app.cognition.associative_memory import MemoryVectorIndex
            if index is None:
                index = MemoryVectorIndex(
                    Path(self.db_path).parent / "memory_vectors.npz"
                )
            self._associative = index
            # Re-embedding every record on every boot is wasteful: rebuild only
            # when the persisted index is empty or the provider changed (the
            # index refuses to load foreign vectors). Otherwise keep the
            # persisted index and index new records incrementally on add().
            if index.count() == 0:
                with self._connect() as conn:
                    rows = conn.execute(
                        "SELECT memory_id, content, tags_json FROM cognitive_memory "
                        "ORDER BY last_accessed DESC LIMIT ?",
                        (max(1, int(backfill_limit)),),
                    ).fetchall()
                records = [
                    (row["memory_id"], row["content"] + " " + (row["tags_json"] or ""))
                    for row in rows
                ]
                indexed = index.rebuild(records)
                app_logger.info(f"Associative memory backfilled ({indexed} vectors)")
            else:
                app_logger.info(
                    f"Associative memory resumed from persisted index ({index.count()} vectors)"
                )
            return True
        except Exception as exc:
            self._associative = None
            app_logger.warning(f"Associative memory unavailable; lexical search only: {exc}")
            return False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS cognitive_memory (
                memory_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                task_id TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                outcome TEXT,
                success INTEGER
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_kind ON cognitive_memory(kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_task ON cognitive_memory(task_id)")
            conn.execute("""CREATE TABLE IF NOT EXISTS memory_consolidation_links (
                source_memory_id TEXT NOT NULL,
                target_memory_id TEXT NOT NULL,
                relation TEXT NOT NULL DEFAULT 'consolidated_into',
                created_at TEXT NOT NULL,
                PRIMARY KEY (source_memory_id, target_memory_id, relation)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_consolidation_source ON memory_consolidation_links(source_memory_id)")

    def add(self, kind: str, content: str, *, importance: float = 0.5, source: str | None = None,
            task_id: str | None = None, tags: list[str] | tuple[str, ...] = (),
            outcome: str | None = None, success: bool | None = None) -> MemoryRecord:
        if kind not in self.VALID_KINDS:
            raise ValueError(f"unsupported memory kind: {kind}")
        importance = max(0.0, min(1.0, importance))
        now = _now()
        record = MemoryRecord(uuid4().hex, kind, content, importance, now, now, 0,
                              source, task_id, tuple(tags), outcome, success)
        with self._connect() as conn:
            conn.execute("""INSERT INTO cognitive_memory
                (memory_id, kind, content, importance, created_at, last_accessed,
                 access_count, source, task_id, tags_json, outcome, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.memory_id, record.kind, record.content, record.importance,
                 record.created_at, record.last_accessed, record.access_count,
                 record.source, record.task_id, json.dumps(record.tags), record.outcome,
                 None if record.success is None else int(record.success)))
        if self._associative is not None:
            try:
                self._associative.add(record.memory_id, record.content + " " + json.dumps(record.tags))
            except Exception as exc:
                app_logger.warning(f"Associative index add failed (non-fatal): {exc}")
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cognitive_memory WHERE memory_id = ?", (memory_id,)).fetchone()
            if row is None:
                return None
            accessed_at = _now()
            conn.execute("UPDATE cognitive_memory SET access_count = access_count + 1, last_accessed = ? WHERE memory_id = ?", (accessed_at, memory_id))
            refreshed = conn.execute("SELECT * FROM cognitive_memory WHERE memory_id = ?", (memory_id,)).fetchone()
            return self._row(refreshed) if refreshed is not None else None

    def search(self, query: str, *, kinds: set[str] | None = None, limit: int = 8) -> list[MemoryRecord]:
        """Hybrid lexical/concept/character retrieval with no network dependency.

        This is intentionally deterministic and lightweight for local hardware.
        Exact token coverage dominates; normalized concepts and character n-gram
        similarity recover modest paraphrases and morphology. Importance is only
        a tie-breaker, so a popular unrelated memory cannot outrank relevant text.
        """
        query_terms = _memory_terms(query)
        query_ngrams = _character_ngrams(query)
        limit = max(1, min(limit, 50))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_memory ORDER BY importance DESC, last_accessed DESC LIMIT 1000"
            ).fetchall()
            selected = []
            for row in rows:
                if kinds and row["kind"] not in kinds:
                    continue
                haystack = row["content"] + " " + row["tags_json"]
                if not query_terms and not query_ngrams:
                    score = float(row["importance"])
                    selected.append((score, row))
                    continue

                memory_terms = _memory_terms(haystack)
                overlap = len(query_terms & memory_terms)
                token_coverage = overlap / max(1, len(query_terms))
                memory_ngrams = _character_ngrams(haystack)
                ngram_overlap = len(query_ngrams & memory_ngrams)
                ngram_cosine = ngram_overlap / math.sqrt(
                    max(1, len(query_ngrams)) * max(1, len(memory_ngrams))
                )
                exact_phrase = 1.0 if query.strip().lower() in haystack.lower() else 0.0
                relevance = token_coverage * 0.7 + ngram_cosine * 0.2 + exact_phrase * 0.1
                if relevance >= 0.12:
                    durable_boost = {
                        "semantic": 0.04,
                        "procedural": 0.04,
                        "lesson": 0.03,
                        "episodic": 0.0,
                    }.get(row["kind"], 0.0)
                    score = relevance + float(row["importance"]) * 0.05 + durable_boost
                    selected.append((score, row))

            selected.sort(key=lambda item: item[0], reverse=True)
            result = self._fuse_associative(query, kinds, limit, selected, conn) or \
                [self._row(row) for _, row in selected[:limit]]
            now = _now()
            for item in result:
                conn.execute(
                    "UPDATE cognitive_memory SET access_count = access_count + 1, last_accessed = ? WHERE memory_id = ?",
                    (now, item.memory_id),
                )
            return result

    def _fuse_associative(self, query, kinds, limit, lexical_selected, conn):
        """Merge lexical ranking with vector-associative recall (RRF, k=60).

        Returns None when associative memory is disabled or fails, leaving the
        lexical ranking untouched. Paraphrases that the lexical 0.12 gate
        filtered out are recovered here by their vector rank.
        """
        if self._associative is None or not query.strip():
            return None
        try:
            vector_hits = self._associative.search(query, k=limit * 4)
            if not vector_hits:
                return None
            # Only STRONG lexical matches vote in fusion: near-gate char-gram
            # noise ("morning"≈"meeting") would otherwise accumulate with a
            # weak vector rank through RRF and bury true vector-only recalls.
            lexical_ids = []
            for score, row in lexical_selected[: limit * 2]:
                if float(score) < 0.3:
                    continue
                if kinds is None or row["kind"] in kinds:
                    lexical_ids.append(str(row["memory_id"]))
            rrf: dict[str, float] = {}
            for rank, memory_id in enumerate(lexical_ids):
                rrf[memory_id] = rrf.get(memory_id, 0.0) + 1.0 / (60 + rank)
            for rank, (memory_id, similarity) in enumerate(vector_hits):
                # Kind filtering happens at row fetch below; rank fusion stays simple.
                rrf[memory_id] = rrf.get(memory_id, 0.0) + 1.0 / (60 + rank)
            top_ids = [memory_id for memory_id, _ in
                       sorted(rrf.items(), key=lambda item: item[1], reverse=True)[:limit]]
            rows_by_id = {}
            for memory_id in top_ids:
                row = conn.execute(
                    "SELECT * FROM cognitive_memory WHERE memory_id = ?", (memory_id,)
                ).fetchone()
                if row is not None and (kinds is None or row["kind"] in kinds):
                    rows_by_id[memory_id] = row
            return [self._row(rows_by_id[memory_id]) for memory_id in top_ids if memory_id in rows_by_id]
        except Exception as exc:
            app_logger.warning(f"Associative fusion failed; lexical ranking kept: {exc}")
            return None

    def list_by_task(self, task_id: str, *, limit: int = 50) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cognitive_memory WHERE task_id = ? ORDER BY created_at DESC LIMIT ?", (task_id, max(1, min(limit, 200)))).fetchall()
            return [self._row(row) for row in rows]

    def unconsolidated_episodes(self, *, limit: int = 100) -> list[MemoryRecord]:
        """Return episodes that have no durable consolidation target yet."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT memory.* FROM cognitive_memory AS memory
                WHERE memory.kind = 'episodic'
                  AND NOT EXISTS (
                    SELECT 1 FROM memory_consolidation_links AS links
                    WHERE links.source_memory_id = memory.memory_id
                      AND links.relation IN ('consolidated_into', 'not_promoted')
                  )
                ORDER BY memory.created_at ASC
                LIMIT ?
            """, (max(1, min(limit, 500)),)).fetchall()
            return [self._row(row) for row in rows]

    def link_consolidation(
        self,
        source_memory_id: str,
        target_memory_id: str,
        relation: str = "consolidated_into",
    ) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO memory_consolidation_links
                (source_memory_id, target_memory_id, relation, created_at)
                VALUES (?, ?, ?, ?)
            """, (source_memory_id, target_memory_id, relation, _now()))

    def consolidation_targets(self, source_memory_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT target_memory_id FROM memory_consolidation_links
                WHERE source_memory_id = ? AND relation = 'consolidated_into'
                ORDER BY created_at
            """, (source_memory_id,)).fetchall()
            return [str(row["target_memory_id"]) for row in rows]

    def verified_success_episodes_for_action(
        self, action_type: str, *, limit: int = 500
    ) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM cognitive_memory
                WHERE kind = 'episodic' AND source = 'goal_verifier' AND success = 1
                ORDER BY created_at DESC LIMIT ?
            """, (max(1, min(limit, 1000)),)).fetchall()
            records = [self._row(row) for row in rows]
            return [
                record for record in records
                if len(record.tags) > 1 and record.tags[1] == action_type
            ]

    def find_exact(self, kind: str, content: str) -> MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM cognitive_memory WHERE kind = ? AND content = ? LIMIT 1",
                (kind, content),
            ).fetchone()
            return self._row(row) if row is not None else None

    def prune(self, *, max_records: int = 5000, minimum_importance: float = 0.05) -> int:
        """Bound storage by removing the least valuable memories first.

        Semantic/procedural/lesson memories are protected from this generic
        cleanup unless they fall below the explicit importance floor.
        """
        max_records = max(100, max_records)
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM cognitive_memory").fetchone()[0]
            if count <= max_records:
                return 0
            excess = count - max_records
            rows = conn.execute("""SELECT memory_id FROM cognitive_memory
                WHERE importance <= ? ORDER BY importance ASC, access_count ASC, last_accessed ASC LIMIT ?""",
                (max(0.0, min(1.0, minimum_importance)), excess)).fetchall()
            ids = [row["memory_id"] for row in rows]
            for memory_id in ids:
                conn.execute(
                    "DELETE FROM memory_consolidation_links WHERE source_memory_id = ? OR target_memory_id = ?",
                    (memory_id, memory_id),
                )
                conn.execute("DELETE FROM cognitive_memory WHERE memory_id = ?", (memory_id,))
            return len(ids)

    def apply_memory_decay_and_prune(self, decay_rate: float = 0.05, max_records: int = 5000) -> int:
        """
        Applies mathematical time-decay to memory importance scores based on age,
        and automatically prunes stale, low-importance memories to maintain sub-millisecond retrieval speeds.
        """
        with self._connect() as conn:
            # Apply decay factor to old un-accessed memories
            conn.execute("""
                UPDATE cognitive_memory
                SET importance = MAX(0.01, importance * (1.0 - ?))
                WHERE access_count = 0 AND kind NOT IN ('lesson', 'procedural')
            """, (decay_rate,))
            conn.commit()

        # Prune stale memories below importance threshold
        return self.prune(max_records=max_records, minimum_importance=0.1)

    def _row(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            row["memory_id"], row["kind"], row["content"], row["importance"], row["created_at"],
            row["last_accessed"], row["access_count"],
            row["source"], row["task_id"], tuple(json.loads(row["tags_json"] or "[]")), row["outcome"],
            None if row["success"] is None else bool(row["success"]),
        )
