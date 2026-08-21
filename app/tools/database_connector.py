"""Read-only database connector (SQLite / PostgreSQL / MySQL).

Extends the SQLite/CSV coverage of `sql_query` to server databases, using the
same read-only guarantee: only SELECT / PRAGMA / WITH / EXPLAIN are ever run,
enforced by `SQLQueryTool.is_read_only` before anything touches a connection.

Deterministic and typed: every method returns `{"success": bool, ...}` and never
raises. Drivers are optional — psycopg2 (Postgres) and pymysql (MySQL) are
imported lazily; if missing, the call degrades to a clear "install this driver"
error instead of crashing.

Credentials can come from the call (user/password/host/…) or fall back to env
vars (ARENA_DB_HOST / ARENA_DB_PORT / ARENA_DB_NAME / ARENA_DB_USER /
ARENA_DB_PASSWORD) so secrets can live in `.env` rather than in tool payloads.

Safety model (manifest authoritative): Level 0 (read-only).
"""

from __future__ import annotations

import os
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

    # ── internals ───────────────────────────────────────────────────────────
    @classmethod
    def _engine(cls, engine: str) -> Optional[str]:
        e = (engine or "").strip().lower()
        return e if e in cls.ENGINES else None

    @classmethod
    def _connect(cls, engine: str, host, port, database, user, password):
        if engine == "sqlite":
            db_path = database or host or os.environ.get("ARENA_DB_NAME", "")
            if not db_path:
                raise ValueError("SQLite requires a 'database' file path.")
            path = db_path
            if not os.path.isabs(path):
                from app.config import settings
                path = str(settings.BASE_DIR / path)
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
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
