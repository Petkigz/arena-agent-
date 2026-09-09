"""Live-server heartbeat file — filesystem-visible proof that Arena runs.

Audit 2026-09-09: ``scripts/reset_learning.py`` detected a live server
ONLY by probing ``http://127.0.0.1:8000/health``. A server on any other
port was invisible to it (it could reset a database under an active
server), and any unrelated process answering on 8000 could block a
legitimate reset. The server now touches ``<data>/server.heartbeat.json``
every 10 seconds while it lives; the reset script refuses to run while
that file is fresh (its own stdlib check — the script stays
dependency-free; the shared contract is the filename and the 45-second
freshness window, documented in both places).

Fail-open: every write error is swallowed (a heartbeat must never take
the server down), and ``ARENA_SERVER_HEARTBEAT=0`` disables the writer.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

HEARTBEAT_FILENAME = "server.heartbeat.json"
HEARTBEAT_INTERVAL_S = 10.0
HEARTBEAT_FRESH_S = 45.0  # > 4x the interval: missed beats stay fresh-safe


def heartbeat_path(db_path: Optional[str] = None) -> Path:
    """The heartbeat file lives beside the server's own database."""
    if db_path is None:
        from app.database import db
        db_path = db.db_path
    return Path(db_path).resolve().parent / HEARTBEAT_FILENAME


def write_server_heartbeat(db_path: Optional[str] = None) -> Optional[Path]:
    """Touch the heartbeat file once. Returns the path, or None when
    disabled/unwritable (fail-open: never raises)."""
    if os.environ.get("ARENA_SERVER_HEARTBEAT", "1") == "0":
        return None
    try:
        path = heartbeat_path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "pid": os.getpid(),
            "ts": time.time(),
        }), encoding="utf-8")
        return path
    except Exception:
        return None


def remove_server_heartbeat(db_path: Optional[str] = None) -> None:
    """Best-effort cleanup at shutdown."""
    try:
        heartbeat_path(db_path).unlink(missing_ok=True)
    except Exception:
        pass
