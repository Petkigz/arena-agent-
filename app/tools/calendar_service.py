"""Local calendar / reminders — a native secretary tool (browser-free).

Stores events and reminders in a local JSON file under DATA_DIR. No external
services. Provides add / list / upcoming / due-reminders.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CalendarService:
    STORE_PATH = settings.DATA_DIR / "calendar.json"

    @classmethod
    def _load(cls) -> Dict[str, Any]:
        if cls.STORE_PATH.exists():
            try:
                return json.loads(cls.STORE_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"events": [], "reminders": []}
        return {"events": [], "reminders": []}

    @classmethod
    def _save(cls, data: Dict[str, Any]) -> None:
        cls.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def add_event(cls, title: str, start: str, end: Optional[str] = None, location: str = "") -> Dict[str, Any]:
        data = cls._load()
        event = {
            "id": uuid4().hex[:12],
            "title": title,
            "start": start,
            "end": end or start,
            "location": location,
            "created": _now_iso(),
        }
        data["events"].append(event)
        cls._save(data)
        audit_logger.info(f"Added calendar event '{title}' at {start}")
        return {"success": True, "event": event}

    @classmethod
    def add_reminder(cls, title: str, due: str, note: str = "") -> Dict[str, Any]:
        data = cls._load()
        reminder = {
            "id": uuid4().hex[:12],
            "title": title,
            "due": due,
            "note": note,
            "done": False,
            "created": _now_iso(),
        }
        data["reminders"].append(reminder)
        cls._save(data)
        return {"success": True, "reminder": reminder}

    @classmethod
    def list_events(cls) -> List[Dict[str, Any]]:
        return cls._load()["events"]

    @classmethod
    def list_reminders(cls, only_pending: bool = True) -> List[Dict[str, Any]]:
        reminders = cls._load()["reminders"]
        if only_pending:
            reminders = [r for r in reminders if not r.get("done")]
        return reminders

    @classmethod
    def due_reminders(cls) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        due = []
        for r in cls._load()["reminders"]:
            if r.get("done"):
                continue
            try:
                due_dt = datetime.fromisoformat(r["due"])
                if due_dt <= now:
                    due.append(r)
            except (ValueError, KeyError):
                continue
        return due

    @classmethod
    def complete_reminder(cls, reminder_id: str) -> Dict[str, Any]:
        data = cls._load()
        for r in data["reminders"]:
            if r["id"] == reminder_id:
                r["done"] = True
                cls._save(data)
                return {"success": True, "reminder": r}
        return {"success": False, "error": f"Reminder '{reminder_id}' not found."}
