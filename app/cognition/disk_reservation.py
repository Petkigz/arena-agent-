"""Persistent free-disk reservations for bounded browser transfers.

A transfer quota alone cannot protect the workspace: two concurrent downloads
that each fit inside the quota can together exhaust the disk. This ledger takes
measured reservations before any byte is fetched, accumulates in-flight
reservations, keeps an owner-configurable safety margin free, and releases or
consumes them on completion, removal, or cancellation.

Honesty rules:
  * Free space is re-measured (``shutil.disk_usage``) at every reserve attempt;
    numbers in the result are observations, not assumptions.
  * A refused reservation returns typed measurements (free, already reserved,
    margin) instead of attempting the transfer.
  * Reservations left ``active`` by a crashed process go ``stale`` on the next
    start (bounded horizon); they are never silently treated as released.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DiskReservation:
    reservation_id: str
    purpose: str
    expected_bytes: int
    target_root: str
    status: str  # active | consumed | released | stale
    created_at: str
    released_at: Optional[str] = None
    actual_bytes: Optional[int] = None
    execution_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DiskReservationLedger:
    """Thread-safe SQLite ledger of in-flight disk-space reservations."""

    stale_after_seconds = 6 * 3600

    def __init__(self, db_path: Optional[str | Path] = None, *, stale_after_seconds: Optional[int] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "disk_reservations.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        horizon = int(stale_after_seconds if stale_after_seconds is not None else self.stale_after_seconds)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS disk_reservations (
                reservation_id TEXT PRIMARY KEY,
                purpose TEXT NOT NULL,
                expected_bytes INTEGER NOT NULL,
                target_root TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                released_at TEXT,
                actual_bytes INTEGER,
                execution_id TEXT
            )""")
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=horizon)).isoformat()
            conn.execute(
                "UPDATE disk_reservations SET status='stale', released_at=? WHERE status='active' AND created_at < ?",
                (_now(), cutoff),
            )
            conn.commit()

    def _row(self, row: sqlite3.Row) -> DiskReservation:
        return DiskReservation(*tuple(row))

    def probe(self, target_root: str | Path) -> Dict[str, Any]:
        """Measure current free/total bytes on the filesystem holding target_root."""
        usage = shutil.disk_usage(str(target_root))
        return {
            "target_root": str(target_root),
            "free_bytes": int(usage.free),
            "total_bytes": int(usage.total),
        }

    def safety_margin_bytes(self) -> int:
        return max(0, int(getattr(settings, "BROWSER_DISK_SAFETY_MARGIN_MB", 512))) * 1024 * 1024

    def active_bytes(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(expected_bytes),0) FROM disk_reservations WHERE status='active'"
            ).fetchone()
        return int(row[0] if row else 0)

    def list_active(self) -> List[DiskReservation]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM disk_reservations WHERE status='active' ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        return [self._row(r) for r in rows]

    def reserve(
        self,
        purpose: str,
        expected_bytes: int,
        *,
        target_root: str | Path,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reserve expected_bytes or refuse with measured evidence.

        When the transfer size is unknown ahead of time, callers must reserve
        their worst-case bound (the owner transfer quota), never zero.
        """
        expected = int(expected_bytes)
        if expected < 1:
            return {
                "success": False,
                "refused": True,
                "error": "Reservation requires a positive expected size; unknown sizes must reserve the worst-case quota.",
            }
        with self._lock:
            measured = self.probe(target_root)
            free = int(measured["free_bytes"])
            already_reserved = self.active_bytes()
            margin = self.safety_margin_bytes()
            available = free - already_reserved - margin
            if expected > available:
                audit_logger.warning(
                    f"Disk reservation refused for {purpose}: need {expected}, available {available} "
                    f"(free {free}, reserved {already_reserved}, margin {margin})"
                )
                return {
                    "success": False,
                    "refused": True,
                    "error": "insufficient_disk_space",
                    "detail": (
                        f"Refusing transfer: expected {expected} bytes but only {max(0, available)} bytes "
                        f"unreserved (free {free}, already reserved {already_reserved}, safety margin {margin})."
                    ),
                    "expected_bytes": expected,
                    "free_bytes": free,
                    "already_reserved_bytes": already_reserved,
                    "safety_margin_bytes": margin,
                    "available_after_reservation": max(0, available - expected),
                    "measured": measured,
                }
            reservation = DiskReservation(
                reservation_id=f"dres_{uuid4().hex[:14]}",
                purpose=str(purpose),
                expected_bytes=expected,
                target_root=str(target_root),
                status="active",
                created_at=_now(),
                execution_id=execution_id,
            )
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO disk_reservations VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        reservation.reservation_id, reservation.purpose, reservation.expected_bytes,
                        reservation.target_root, reservation.status, reservation.created_at,
                        reservation.released_at, reservation.actual_bytes, reservation.execution_id,
                    ),
                )
                conn.commit()
            audit_logger.info(
                f"Disk reservation {reservation.reservation_id} granted for {purpose}: "
                f"{expected} bytes (free {free}, previously reserved {already_reserved})"
            )
            return {
                "success": True,
                "reservation": reservation.to_dict(),
                "free_bytes": free,
                "already_reserved_bytes": already_reserved,
                "safety_margin_bytes": margin,
                "available_after_reservation": available - expected,
            }

    def _finish(self, reservation_id: str, status: str, *, actual_bytes: Optional[int], reason: str) -> Optional[DiskReservation]:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT * FROM disk_reservations WHERE reservation_id=?", (reservation_id,)
                ).fetchone()
                if row is None:
                    return None
                current = self._row(row)
                if current.status != "active":
                    return current
                conn.execute(
                    "UPDATE disk_reservations SET status=?, released_at=?, actual_bytes=? WHERE reservation_id=?",
                    (status, _now(), actual_bytes, reservation_id),
                )
                conn.commit()
            audit_logger.info(f"Disk reservation {reservation_id} → {status} ({reason})")
            with sqlite3.connect(self.db_path) as conn:
                return self._row(conn.execute(
                    "SELECT * FROM disk_reservations WHERE reservation_id=?", (reservation_id,)
                ).fetchone())

    def consume(self, reservation_id: str, actual_bytes: int, *, reason: str = "transfer completed") -> Optional[DiskReservation]:
        """Mark completed: the artifact now physically occupies the space."""
        return self._finish(reservation_id, "consumed", actual_bytes=int(actual_bytes), reason=reason)

    def release(self, reservation_id: str, *, reason: str = "released") -> Optional[DiskReservation]:
        """Free a reservation whose transfer never materialized."""
        return self._finish(reservation_id, "released", actual_bytes=None, reason=reason)


# Module-level singleton, mirroring the other persistent stores.
disk_reservation_ledger = DiskReservationLedger()
