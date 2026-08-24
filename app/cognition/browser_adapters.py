"""Owner-configured, service-specific browser adapters for receipts and deletes.

Remote uploads are honest about their limits: "rollback unsupported unless a
service-specific delete API exists." This registry holds the owner's declared
knowledge of such services — a URL pattern that identifies the service, a
receipt selector/attribute for extracting the service's own upload receipt ID,
and optionally a delete URL template plus confirmation selector implementing a
delete flow.

Everything here is owner-declared configuration, not discovered capability:
a missing adapter honestly means "no service-specific knowledge", and a
configured delete flow still requires separate Level-3 authorization to run.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BrowserServiceAdapter:
    adapter_id: str
    service_id: str
    url_pattern: str
    receipt_selector: str = ""
    receipt_attribute: str = "text"  # "text" or an attribute name (href, data-id, ...)
    delete_url_template: str = ""    # must contain {receipt_id} when set
    confirm_selector: str = ""       # required when delete_url_template is set
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def delete_supported(self) -> bool:
        return bool(self.delete_url_template and self.confirm_selector)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["delete_supported"] = self.delete_supported
        return data


class BrowserAdapterStore:
    """Persistent registry of the owner's service-specific browser adapters."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "browser_service_adapters.db"))
        import pathlib
        pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS browser_service_adapters (
                adapter_id TEXT PRIMARY KEY,
                service_id TEXT UNIQUE NOT NULL,
                url_pattern TEXT NOT NULL,
                receipt_selector TEXT NOT NULL DEFAULT '',
                receipt_attribute TEXT NOT NULL DEFAULT 'text',
                delete_url_template TEXT NOT NULL DEFAULT '',
                confirm_selector TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            conn.commit()

    def _row(self, row: sqlite3.Row) -> BrowserServiceAdapter:
        adapter = BrowserServiceAdapter(*tuple(row[:9]))
        return adapter

    def upsert(self, data: Dict[str, Any]) -> BrowserServiceAdapter:
        service_id = str(data.get("service_id", "")).strip()
        url_pattern = str(data.get("url_pattern", "")).strip()
        if not service_id or not url_pattern:
            raise ValueError("service_id and url_pattern are required")
        try:
            re.compile(url_pattern)
        except re.error as exc:
            raise ValueError(f"url_pattern is not a valid regex: {exc}")
        receipt_selector = str(data.get("receipt_selector", "") or "").strip()
        receipt_attribute = str(data.get("receipt_attribute", "text") or "text").strip() or "text"
        delete_url_template = str(data.get("delete_url_template", "") or "").strip()
        confirm_selector = str(data.get("confirm_selector", "") or "").strip()
        if delete_url_template:
            if "{receipt_id}" not in delete_url_template:
                raise ValueError("delete_url_template must contain {receipt_id}")
            if not confirm_selector:
                raise ValueError("confirm_selector is required when delete_url_template is set")
        now = _now()
        with self._lock:
            existing = self.get_by_service(service_id)
            adapter = BrowserServiceAdapter(
                adapter_id=existing.adapter_id if existing else f"bsa_{uuid4().hex[:14]}",
                service_id=service_id,
                url_pattern=url_pattern,
                receipt_selector=receipt_selector,
                receipt_attribute=receipt_attribute,
                delete_url_template=delete_url_template,
                confirm_selector=confirm_selector,
                note=str(data.get("note", "") or ""),
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""INSERT OR REPLACE INTO browser_service_adapters
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                    adapter.adapter_id, adapter.service_id, adapter.url_pattern,
                    adapter.receipt_selector, adapter.receipt_attribute,
                    adapter.delete_url_template, adapter.confirm_selector,
                    adapter.note, adapter.created_at, adapter.updated_at,
                ))
                conn.commit()
        audit_logger.info(f"Browser service adapter saved: {service_id} (delete_supported={adapter.delete_supported})")
        return adapter

    def get_by_service(self, service_id: str) -> Optional[BrowserServiceAdapter]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM browser_service_adapters WHERE service_id=?", (str(service_id),)
            ).fetchone()
        return self._row(row) if row else None

    def match(self, url: str) -> Optional[BrowserServiceAdapter]:
        """First adapter whose url_pattern matches the given page URL."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM browser_service_adapters ORDER BY created_at ASC"
            ).fetchall()
        for row in rows:
            adapter = self._row(row)
            try:
                if re.search(adapter.url_pattern, url or ""):
                    return adapter
            except re.error:
                app_logger.warning(f"Adapter {adapter.service_id} has an invalid url_pattern; skipping")
        return None

    def list(self) -> List[BrowserServiceAdapter]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM browser_service_adapters ORDER BY created_at ASC"
            ).fetchall()
        return [self._row(r) for r in rows]

    def remove(self, service_id: str) -> bool:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM browser_service_adapters WHERE service_id=?", (str(service_id),)
                )
                conn.commit()
        removed = cursor.rowcount > 0
        if removed:
            audit_logger.warning(f"Browser service adapter removed: {service_id}")
        return removed


# Module-level singleton, mirroring the other owner stores.
browser_adapter_store = BrowserAdapterStore()
