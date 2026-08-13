"""Phase 4: lightweight persistent episodic, semantic, and procedural memory."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    """SQLite-backed memory with bounded retrieval; no embedding model required."""
    VALID_KINDS = {"episodic", "semantic", "procedural", "lesson"}

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._init_db()

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
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cognitive_memory WHERE memory_id = ?", (memory_id,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE cognitive_memory SET access_count = access_count + 1, last_accessed = ? WHERE memory_id = ?", (_now(), memory_id))
            return self._row(row, accessed=True)

    def search(self, query: str, *, kinds: set[str] | None = None, limit: int = 8) -> list[MemoryRecord]:
        """Cheap lexical retrieval; semantic/vector retrieval can be layered later."""
        terms = [term.lower() for term in query.split() if term.strip()]
        limit = max(1, min(limit, 50))
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cognitive_memory ORDER BY importance DESC, last_accessed DESC LIMIT 500").fetchall()
            selected = []
            for row in rows:
                if kinds and row["kind"] not in kinds:
                    continue
                haystack = (row["content"] + " " + row["tags_json"]).lower()
                matches = sum(term in haystack for term in terms) if terms else 0
                if matches or not terms:
                    score = matches + float(row["importance"]) * 0.5
                    selected.append((score, row))
            selected.sort(key=lambda item: item[0], reverse=True)
            result = [self._row(row) for _, row in selected[:limit]]
            now = _now()
            for item in result:
                conn.execute("UPDATE cognitive_memory SET access_count = access_count + 1, last_accessed = ? WHERE memory_id = ?", (now, item.memory_id))
            return result

    def list_by_task(self, task_id: str, *, limit: int = 50) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cognitive_memory WHERE task_id = ? ORDER BY created_at DESC LIMIT ?", (task_id, max(1, min(limit, 200)))).fetchall()
            return [self._row(row) for row in rows]

    def _row(self, row: sqlite3.Row, accessed: bool = False) -> MemoryRecord:
        return MemoryRecord(
            row["memory_id"], row["kind"], row["content"], row["importance"], row["created_at"],
            _now() if accessed else row["last_accessed"], row["access_count"] + (1 if accessed else 0),
            row["source"], row["task_id"], tuple(json.loads(row["tags_json"] or "[]")), row["outcome"],
            None if row["success"] is None else bool(row["success"]),
        )
