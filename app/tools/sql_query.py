"""Read-only SQL query tool for local SQLite databases and CSV files.

Read-only by design (only SELECT / PRAGMA allowed) — no INSERT/UPDATE/DELETE/DDL.
This makes it a safe capability for the agent to use autonomously (Level 0).

Uses the Python stdlib (sqlite3 / csv). Degrades gracefully.
"""

from __future__ import annotations

import csv
import sqlite3
from typing import Dict, Any, List

from app.utils.logger import app_logger


class SQLQueryTool:
    @classmethod
    def is_read_only(cls, sql: str) -> bool:
        """Reject anything that mutates data or schema."""
        first = sql.strip().lstrip("(").strip().split(None, 1)
        if not first:
            return False
        keyword = first[0].upper()
        return keyword in ("SELECT", "PRAGMA", "WITH", "EXPLAIN")

    @classmethod
    def query_sqlite(cls, db_path: str, sql: str, limit: int = 100) -> Dict[str, Any]:
        """Run a read-only query against a local SQLite database."""
        if not cls.is_read_only(sql):
            return {"success": False, "error": "Only read-only SQL (SELECT/PRAGMA) is allowed."}

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql)
            rows = [dict(r) for r in cur.fetchmany(limit + 1)]
            truncated = len(rows) > limit
            rows = rows[:limit]
            conn.close()
            return {"success": True, "rows": rows, "count": len(rows), "truncated": truncated}
        except Exception as e:
            app_logger.warning(f"SQLite query failed: {e}")
            return {"success": False, "error": f"SQLite query failed: {e}"}

    @staticmethod
    def _coerce(value: str):
        """Coerce a CSV string cell to int/float if it looks numeric, else string."""
        v = value.strip()
        try:
            return int(v)
        except (ValueError, TypeError):
            pass
        try:
            return float(v)
        except (ValueError, TypeError):
            pass
        return value

    @classmethod
    def query_csv(cls, csv_path: str, sql: str, limit: int = 100) -> Dict[str, Any]:
        """Query a CSV file using SQL (loaded into an in-memory SQLite table 'data')."""
        if not cls.is_read_only(sql):
            return {"success": False, "error": "Only read-only SQL (SELECT/PRAGMA) is allowed."}

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames or []
                rows = list(reader)

            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            cols = ", ".join(f'"{c}"' for c in columns) if columns else "col0"
            conn.execute(f"CREATE TABLE data ({cols})")
            for row in rows:
                placeholders = ", ".join("?" for _ in columns)
                # Coerce numeric-looking cells so numeric SQL comparisons work
                # (CSV has no column types; SQLite would otherwise store TEXT).
                values = [cls._coerce(row.get(c, "")) for c in columns]
                conn.execute(
                    f"INSERT INTO data ({cols}) VALUES ({placeholders})",
                    values,
                )
            cur = conn.execute(sql)
            out = [dict(r) for r in cur.fetchmany(limit + 1)]
            truncated = len(out) > limit
            conn.close()
            return {"success": True, "rows": out[:limit], "count": len(out[:limit]), "truncated": truncated}
        except Exception as e:
            app_logger.warning(f"CSV query failed: {e}")
            return {"success": False, "error": f"CSV query failed: {e}"}
