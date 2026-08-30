"""Persistent filename index — the agent's own mini search index.

Everything (voidtools) reads the NTFS master file table, which needs admin
rights; this module is the no-admin equivalent: a SQLite cache of every
filename the walk-based search has ever seen, stored at
``data/file_index.db``.

Correctness model (why the index can never cause a false 'not there'):

  * Cache HITS are existence-verified with ``os.path.exists`` before being
    returned — deleted/moved files drop out.
  * Cache MISSES always fall through to a live walk (which refreshes the
    index as a side effect), so a file created a second after indexing is
    still found.
  * A freshness TTL bounds staleness for 'list all' style queries.

The index is purely an accelerator: if the database is missing, corrupted,
or unwritable, search degrades to the plain walk without error.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    root       TEXT    NOT NULL,
    name       TEXT    NOT NULL,
    name_lower TEXT    NOT NULL,
    path       TEXT    NOT NULL,
    is_dir     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS roots (
    root        TEXT PRIMARY KEY,
    indexed_at  REAL NOT NULL,
    complete    INTEGER NOT NULL DEFAULT 0,
    entry_count INTEGER NOT NULL DEFAULT 0
);
"""


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class FileIndex:
    """Thread-safe, failure-safe SQLite filename cache."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else Path(settings.DATA_DIR) / "file_index.db"
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._disabled = False
        self.stats: Dict[str, int] = {"hits": 0, "misses": 0, "walks": 0}

    # ── plumbing ──────────────────────────────────────────────────────────
    def _connection(self) -> Optional[sqlite3.Connection]:
        if self._disabled:
            return None
        if self._conn is None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self.path), check_same_thread=False)
                conn.execute("PRAGMA journal_mode=OFF")
                conn.execute("PRAGMA synchronous=OFF")
                conn.executescript(_SCHEMA)
                conn.commit()
                self._conn = conn
            except Exception as exc:
                app_logger.warning(f"File index disabled (db error: {exc}); search falls back to walk.")
                self._disabled = True
                return None
        return self._conn

    # ── queries ───────────────────────────────────────────────────────────
    def root_age(self, root: str) -> float:
        """Seconds since the root was last indexed; infinity if never."""
        with self._lock:
            conn = self._connection()
            if conn is None:
                return float("inf")
            try:
                row = conn.execute(
                    "SELECT indexed_at FROM roots WHERE root = ?", (root,)
                ).fetchone()
            except Exception:
                return float("inf")
            if not row:
                return float("inf")
            return max(0.0, time.time() - float(row[0]))

    def lookup_exact(self, query: str, roots: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Exact-substring matches from the cache (NOT existence-verified —
        the caller must verify before trusting)."""
        with self._lock:
            conn = self._connection()
            if conn is None or not query.strip():
                return []
            try:
                placeholders = ",".join("?" for _ in roots)
                rows = conn.execute(
                    f"SELECT name, path, is_dir FROM files "
                    f"WHERE root IN ({placeholders}) AND name_lower LIKE ? ESCAPE '\\' "
                    f"ORDER BY rowid LIMIT ?",
                    [str(r) for r in roots] + [f"%{_like_escape(query.lower())}%", int(limit)],
                ).fetchall()
            except Exception as exc:
                app_logger.warning(f"File index lookup failed: {exc}")
                return []
        return [
            {"file_name": r[0], "file_path": r[1], "type": "directory" if r[2] else "file", "match": "exact"}
            for r in rows
        ]

    # ── maintenance ───────────────────────────────────────────────────────
    def begin_root(self, root: str) -> None:
        """Start a fresh index for a root (drops its previous rows)."""
        with self._lock:
            conn = self._connection()
            if conn is None:
                return
            try:
                conn.execute("DELETE FROM files WHERE root = ?", (root,))
                conn.execute(
                    "INSERT INTO roots (root, indexed_at, complete, entry_count) "
                    "VALUES (?, ?, 0, 0) "
                    "ON CONFLICT(root) DO UPDATE SET indexed_at = excluded.indexed_at, complete = 0",
                    (root, time.time()),
                )
                conn.commit()
            except Exception as exc:
                app_logger.warning(f"File index begin_root failed: {exc}")

    def add_entries(self, root: str, entries: List[tuple]) -> None:
        """Insert (name, path, is_dir) tuples recorded during a walk."""
        if not entries:
            return
        with self._lock:
            conn = self._connection()
            if conn is None:
                return
            try:
                conn.executemany(
                    "INSERT INTO files (root, name, name_lower, path, is_dir) VALUES (?, ?, ?, ?, ?)",
                    [(root, n, str(n).lower(), p, d) for (n, p, d) in entries],
                )
                conn.commit()
            except Exception as exc:
                app_logger.warning(f"File index insert failed: {exc}")

    def finish_root(self, root: str, complete: bool) -> None:
        with self._lock:
            conn = self._connection()
            if conn is None:
                return
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM files WHERE root = ?", (root,)
                ).fetchone()[0]
                conn.execute(
                    "UPDATE roots SET complete = ?, entry_count = ? WHERE root = ?",
                    (1 if complete else 0, int(count), root),
                )
                conn.commit()
                app_logger.info(
                    f"File index: root '{root}' now holds {count} entries "
                    f"({'complete' if complete else 'partial — walk hit the time budget'})."
                )
            except Exception as exc:
                app_logger.warning(f"File index finish_root failed: {exc}")

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None


_index: Optional[FileIndex] = None
_index_lock = threading.Lock()


def get_file_index() -> FileIndex:
    """Process-wide index instance (lazy)."""
    global _index
    with _index_lock:
        if _index is None:
            _index = FileIndex()
        return _index


def reset_file_index(path: Optional[str] = None) -> FileIndex:
    """Testing hook: fresh index instance at an explicit path."""
    global _index
    with _index_lock:
        if _index is not None:
            _index.close()
        _index = FileIndex(path)
        return _index
