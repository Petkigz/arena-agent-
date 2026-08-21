"""Database connector (SQLite / PostgreSQL / MySQL) — read AND write.

Two distinct paths, mirroring the owner's permissions model ("nothing off-limits,
but sensitive/irreversible actions need explicit approval"):

- `query` / `list_tables` → **read-only** (only SELECT/PRAGMA/WITH/EXPLAIN, enforced
  by `SQLQueryTool.is_read_only`). Level 0: the agent may run these autonomously.
- `execute` → **write** (INSERT/UPDATE/DELETE/DDL). Level 3: requires explicit
  owner approval. Two minimal foot-gun rails on top of that gate:
    1. `DROP DATABASE` / `DROP SCHEMA` requires `allow_destructive=True`.
    2. unfiltered `DELETE`/`UPDATE` (no WHERE) requires `allow_unfiltered=True`.
  These don't forbid anything — they just force an explicit second confirmation
  for the two most catastrophic typos.

Deterministic and typed: every method returns `{"success": bool, ...}` and never
raises. Drivers are optional — psycopg2 (Postgres) and pymysql (MySQL) are
imported lazily; if missing, the call degrades to a clear "install this driver"
error instead of crashing.

Credentials can come from the call (user/password/host/…) or fall back to env
vars (ARENA_DB_HOST / ARENA_DB_PORT / ARENA_DB_NAME / ARENA_DB_USER /
ARENA_DB_PASSWORD) so secrets can live in `.env` rather than in tool payloads.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from app.tools.sql_query import SQLQueryTool
from app.utils.logger import app_logger, audit_logger


class DatabaseConnector:
    ENGINES = ("sqlite", "postgres", "mysql")

    # ── public API ──────────────────────────────────────────────────────────
    @classmethod
    def query(
        cls,
        engine: str,
        sql: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Run a read-only SQL query against the given database."""
        if not sql or not sql.strip():
            return {"success": False, "error": "A SQL query is required."}
        if not SQLQueryTool.is_read_only(sql):
            return {"success": False, "error": "Only read-only SQL (SELECT/PRAGMA) is allowed."}
        engine = cls._engine(engine)
        if engine is None:
            return {"success": False, "error": f"Unsupported engine. Use one of {list(cls.ENGINES)}."}
        limit = max(1, min(int(limit), 1000))

        try:
            conn = cls._connect(engine, host, port, database, user, password)
        except Exception as e:
            return {"success": False, "error": f"Could not connect: {e}"}

        try:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchmany(limit + 1)
            truncated = len(rows) > limit
            rows = rows[:limit]
            if rows and isinstance(rows[0], (list, tuple)):
                cols = [d[0] for d in (cur.description or [])]
                rows = [dict(zip(cols, r)) for r in rows]
            conn.commit()  # no-op for SELECT; safe close for read-only servers
            audit_logger.info(f"Ran read-only {engine} query ({len(rows)} rows)")
            return {"success": True, "rows": rows, "count": len(rows), "truncated": truncated}
        except Exception as e:
            app_logger.warning(f"Query failed on {engine}: {e}")
            return {"success": False, "error": f"Query failed: {e}"}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @classmethod
    def list_tables(
        cls,
        engine: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List table names in the database (read-only metadata query)."""
        engine = cls._engine(engine)
        if engine is None:
            return {"success": False, "error": f"Unsupported engine. Use one of {list(cls.ENGINES)}."}

        try:
            conn = cls._connect(engine, host, port, database, user, password)
        except Exception as e:
            return {"success": False, "error": f"Could not connect: {e}"}

        try:
            cur = conn.cursor()
            if engine == "sqlite":
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            elif engine == "postgres":
                cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
            else:  # mysql
                cur.execute("SHOW TABLES")
            rows = [r[0] for r in cur.fetchall()]
            return {"success": True, "tables": rows, "count": len(rows)}
        except Exception as e:
            app_logger.warning(f"list_tables failed on {engine}: {e}")
            return {"success": False, "error": f"list_tables failed: {e}"}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @classmethod
    def execute(
        cls,
        engine: str,
        sql: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        allow_unfiltered: bool = False,
        allow_destructive: bool = False,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Run a write (or read) SQL statement. Level 3: requires owner approval.

        Writes are committed in a transaction and rolled back on any error.
        Returns the affected row count (DML) or fetched rows (SELECT).
        """
        if not sql or not sql.strip():
            return {"success": False, "error": "A SQL statement is required."}

        guard = cls._write_guard(sql, allow_unfiltered, allow_destructive)
        if guard:
            return {"success": False, "error": guard}

        engine = cls._engine(engine)
        if engine is None:
            return {"success": False, "error": f"Unsupported engine. Use one of {list(cls.ENGINES)}."}
        limit = max(1, min(int(limit), 1000))

        try:
            conn = cls._connect(engine, host, port, database, user, password, read_only=False)
        except Exception as e:
            return {"success": False, "error": f"Could not connect: {e}"}

        try:
            cur = conn.cursor()
            cur.execute(sql)
            if SQLQueryTool.is_read_only(sql):
                rows = cur.fetchmany(limit + 1)
                truncated = len(rows) > limit
                rows = rows[:limit]
                if rows and isinstance(rows[0], (list, tuple)):
                    cols = [d[0] for d in (cur.description or [])]
                    rows = [dict(zip(cols, r)) for r in rows]
                conn.commit()
                return {"success": True, "rows": rows, "count": len(rows), "truncated": truncated}
            rowcount = cur.rowcount
            conn.commit()
            audit_logger.info(f"Executed write on {engine} (rowcount={rowcount})")
            return {"success": True, "rowcount": rowcount if rowcount is not None and rowcount >= 0 else 0}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            app_logger.warning(f"Execute failed on {engine}: {e}")
            return {"success": False, "error": f"Statement failed: {e}"}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── internals ───────────────────────────────────────────────────────────
    @staticmethod
    def _write_guard(sql: str, allow_unfiltered: bool, allow_destructive: bool) -> Optional[str]:
        """Return an error string for the two most catastrophic typos, else None."""
        stripped = re.sub(r"--.*?(\n|$)", " ", sql, flags=re.IGNORECASE)
        stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.DOTALL)
        upper = stripped.upper()

        if re.search(r"\bDROP\s+(DATABASE|SCHEMA)\b", upper) and not allow_destructive:
            return "DROP DATABASE/SCHEMA requires allow_destructive=True."

        is_mutation = re.search(r"\b(DELETE|UPDATE)\b", upper)
        has_where = re.search(r"\bWHERE\b", upper)
        if is_mutation and not has_where and not allow_unfiltered:
            return "Unfiltered DELETE/UPDATE (no WHERE clause) requires allow_unfiltered=True."
        return None

    @classmethod
    def _engine(cls, engine: str) -> Optional[str]:
        e = (engine or "").strip().lower()
        return e if e in cls.ENGINES else None

    @classmethod
    def _connect(cls, engine: str, host, port, database, user, password, read_only: bool = True):
        if engine == "sqlite":
            db_path = database or host or os.environ.get("ARENA_DB_NAME", "")
            if not db_path:
                raise ValueError("SQLite requires a 'database' file path.")
            path = db_path
            if not os.path.isabs(path):
                from app.config import settings
                path = str(settings.BASE_DIR / path)
            uri = f"file:{path}?mode=ro" if read_only else path
            conn = sqlite3.connect(uri, uri=read_only)
            conn.row_factory = sqlite3.Row
            return conn

        # Server databases: driver is optional and imported lazily.
        if engine == "postgres":
            try:
                import psycopg2
            except ImportError:
                raise RuntimeError("Postgres support requires 'psycopg2-binary'. Install it to use engine='postgres'.")
            host = host or os.environ.get("ARENA_DB_HOST", "localhost")
            port = port or int(os.environ.get("ARENA_DB_PORT", "5432"))
            database = database or os.environ.get("ARENA_DB_NAME", "")
            user = user or os.environ.get("ARENA_DB_USER", "")
            password = password or os.environ.get("ARENA_DB_PASSWORD", "")
            return psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password)

        # mysql
        try:
            import pymysql
        except ImportError:
            raise RuntimeError("MySQL support requires 'pymysql'. Install it to use engine='mysql'.")
        host = host or os.environ.get("ARENA_DB_HOST", "localhost")
        port = port or int(os.environ.get("ARENA_DB_PORT", "3306"))
        database = database or os.environ.get("ARENA_DB_NAME", "")
        user = user or os.environ.get("ARENA_DB_USER", "")
        password = password or os.environ.get("ARENA_DB_PASSWORD", "")
        return pymysql.connect(host=host, port=port, database=database, user=user, password=password)
