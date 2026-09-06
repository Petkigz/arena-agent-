"""Local calendar / reminders — a native coworker tool (browser-free).

Stores events and reminders in a local JSON file under DATA_DIR. No external
services. Provides add / list / upcoming / due-reminders.
"""

from __future__ import annotations

import json
import threading
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
    _lock = threading.RLock()

    @classmethod
    def _empty_store(cls) -> Dict[str, Any]:
        return {"events": [], "reminders": [], "turn_counters": {}}

    @classmethod
    def _load(cls) -> Dict[str, Any]:
        if cls.STORE_PATH.exists():
            try:
                data = json.loads(cls.STORE_PATH.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return cls._empty_store()
                # Preserve the existing wall-clock calendar format while
                # adding durable per-session turn counters for prospective
                # reminders. Older stores migrate in memory without loss.
                data.setdefault("events", [])
                data.setdefault("reminders", [])
                data.setdefault("turn_counters", {})
                if not isinstance(data["events"], list):
                    data["events"] = []
                if not isinstance(data["reminders"], list):
                    data["reminders"] = []
                if not isinstance(data["turn_counters"], dict):
                    data["turn_counters"] = {}
                return data
            except (json.JSONDecodeError, OSError):
                return cls._empty_store()
        return cls._empty_store()

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
    def add_turn_reminder(
        cls,
        title: str,
        turns: int,
        *,
        session_id: str = "default",
        note: str = "",
        expiry_turns: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a reminder delivered after a number of conversation turns.

        Turn reminders are scoped to a conversation session, not to its topic.
        Delivery is claimed durably by :meth:`advance_turn`, so a reminder is
        delivered at most once. ``expiry_turns`` prevents an abandoned
        reminder from remaining pending forever; it is measured from creation.
        When omitted, the reminder expires ten turns after its due turn.
        """
        try:
            turns = int(turns)
        except (TypeError, ValueError):
            return {"success": False, "error": "turns must be a positive integer"}
        if turns < 1:
            return {"success": False, "error": "turns must be a positive integer"}
        session_id = str(session_id or "default")[:200]
        title = str(title or "Follow up on this conversation").strip()[:500]
        if not title:
            title = "Follow up on this conversation"
        try:
            expiry_turns = int(expiry_turns) if expiry_turns is not None else turns + 10
        except (TypeError, ValueError):
            return {"success": False, "error": "expiry_turns must be a positive integer"}
        if expiry_turns < 1:
            return {"success": False, "error": "expiry_turns must be a positive integer"}

        with cls._lock:
            data = cls._load()
            current_turn = int(data["turn_counters"].get(session_id, 0))
            reminder = {
                "id": uuid4().hex[:12],
                "title": title,
                "due": "",
                "note": str(note or "")[:1000],
                "done": False,
                "created": _now_iso(),
                "condition_type": "conversation_turn",
                "session_id": session_id,
                "created_turn": current_turn,
                "due_turn": current_turn + turns,
                "expires_turn": current_turn + expiry_turns,
                "delivery_condition": {
                    "type": "conversation_turn",
                    "session_id": session_id,
                    "due_turn": current_turn + turns,
                },
                "status": "pending",
                "owner_visible": True,
                "delivered": False,
                "delivered_at": None,
                "delivered_turn": None,
            }
            data["reminders"].append(reminder)
            cls._save(data)
        audit_logger.info(
            "Added turn reminder '%s' for session %s at turn %s",
            title, session_id, reminder["due_turn"],
        )
        return {"success": True, "reminder": reminder}

    @classmethod
    def advance_turn(cls, session_id: str = "default") -> Dict[str, Any]:
        """Advance one conversation turn and claim newly due reminders.

        The returned reminders are already marked ``delivered`` in the local
        store. Repeating the call for the same later turn cannot deliver them
        a second time. Expired reminders are marked explicitly rather than
        silently disappearing.
        """
        session_id = str(session_id or "default")[:200]
        with cls._lock:
            data = cls._load()
            current_turn = int(data["turn_counters"].get(session_id, 0)) + 1
            data["turn_counters"][session_id] = current_turn
            delivered: List[Dict[str, Any]] = []
            changed = True
            now = _now_iso()
            for reminder in data["reminders"]:
                if reminder.get("condition_type") != "conversation_turn":
                    continue
                if str(reminder.get("session_id", "default")) != session_id:
                    continue
                if reminder.get("done") or reminder.get("delivered"):
                    continue
                expires_turn = reminder.get("expires_turn")
                if expires_turn is not None and current_turn >= int(expires_turn):
                    reminder["status"] = "expired"
                    reminder["expired_at"] = now
                    continue
                if current_turn >= int(reminder.get("due_turn", 0)):
                    reminder["status"] = "delivered"
                    reminder["delivered"] = True
                    reminder["delivered_at"] = now
                    reminder["delivered_turn"] = current_turn
                    delivered.append(dict(reminder))
            if changed:
                cls._save(data)
        return {"session_id": session_id, "turn": current_turn, "reminders": delivered}

    @classmethod
    def list_turn_reminders(
        cls,
        session_id: Optional[str] = None,
        *,
        include_completed: bool = False,
    ) -> List[Dict[str, Any]]:
        """List durable turn reminders, including explicit expiry status."""
        reminders = [
            dict(item)
            for item in cls._load()["reminders"]
            if item.get("condition_type") == "conversation_turn"
            and (session_id is None or str(item.get("session_id")) == str(session_id))
            and (include_completed or not item.get("done"))
        ]
        return reminders

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
        with cls._lock:
            data = cls._load()
            for r in data["reminders"]:
                if r["id"] == reminder_id:
                    r["done"] = True
                    if r.get("condition_type") == "conversation_turn":
                        r["status"] = "completed"
                        r["completed_at"] = _now_iso()
                    cls._save(data)
                    return {"success": True, "reminder": r}
        return {"success": False, "error": f"Reminder '{reminder_id}' not found."}
