"""Phase 4C: Anticipatory Action Engine.

Predicts what the user will need next based on historical task patterns.
Analyzes task sequences (time of day, task ordering, frequency) to
anticipate needs and prepare resources proactively.

Anticipations require approval for sensitive actions.
"""

from __future__ import annotations

import sqlite3
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hour_of_day(timestamp: Optional[str] = None) -> int:
    """Extract hour of day (0-23) from ISO timestamp."""
    try:
        dt = datetime.fromisoformat(timestamp or _now())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.hour
    except Exception:
        return datetime.now().hour


def _day_of_week(timestamp: Optional[str] = None) -> int:
    """Extract day of week (0=Monday, 6=Sunday) from ISO timestamp."""
    try:
        dt = datetime.fromisoformat(timestamp or _now())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.weekday()
    except Exception:
        return datetime.now().weekday()


# ── Task Sequence Tracking ───────────────────────────────────────────

@dataclass(frozen=True)
class TaskEvent:
    """A recorded task execution event with temporal context."""
    event_id: str
    action_type: str
    goal_text: str
    intent_type: str
    timestamp: str
    hour_of_day: int
    day_of_week: int
    success: bool


@dataclass(frozen=True)
class Anticipation:
    """A predicted future need."""
    anticipation_id: str
    predicted_action: str
    confidence: float           # 0.0-1.0
    reason: str                 # why this was predicted
    suggested_preparation: str  # what to prepare
    requires_approval: bool     # whether this needs user approval
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)


# ── Anticipation Engine ──────────────────────────────────────────────

class AnticipationEngine:
    """
    Predicts user needs based on historical task patterns.

    Patterns analyzed:
    1. Sequential: "After task A, user usually does task B"
    2. Temporal: "At this time of day, user usually does X"
    3. Frequency: "User does X every N hours/days"
    """

    # Minimum occurrences before making predictions
    MIN_OCCURRENCES = 3
    # Minimum confidence to surface an anticipation
    MIN_CONFIDENCE = 0.3
    # Sensitive action types that always require approval
    SENSITIVE_ACTIONS = {
        "send_sms", "make_phone_call", "run_command",
        "delete_file", "send_email", "trade_action"
    }

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._events: List[TaskEvent] = []
        self._transitions: Dict[str, Counter] = defaultdict(Counter)  # action → Counter(next_actions)
        self._temporal: Dict[Tuple[int, int], Counter] = defaultdict(Counter)  # (hour, dow) → Counter(actions)
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                event_id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                goal_text TEXT NOT NULL DEFAULT '',
                intent_type TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL,
                hour_of_day INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                success INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_events_time
            ON task_events(timestamp)
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""SELECT event_id, action_type, goal_text, intent_type,
            timestamp, hour_of_day, day_of_week, success
            FROM task_events ORDER BY timestamp""")
        for row in cursor.fetchall():
            event = TaskEvent(
                event_id=row[0], action_type=row[1], goal_text=row[2],
                intent_type=row[3], timestamp=row[4], hour_of_day=row[5],
                day_of_week=row[6], success=bool(row[7])
            )
            self._events.append(event)
        conn.close()
        self._rebuild_models()

    def _save_to_db(self, event: TaskEvent) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO task_events
            (event_id, action_type, goal_text, intent_type, timestamp,
             hour_of_day, day_of_week, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (event.event_id, event.action_type, event.goal_text,
              event.intent_type, event.timestamp, event.hour_of_day,
              event.day_of_week, int(event.success)))
        conn.commit()
        conn.close()

    def _rebuild_models(self) -> None:
        """Rebuild transition and temporal models from event history."""
        self._transitions.clear()
        self._temporal.clear()

        for i, event in enumerate(self._events):
            # Temporal model
            key = (event.hour_of_day, event.day_of_week)
            self._temporal[key][event.action_type] += 1

            # Sequential model (what follows what)
            if i > 0:
                prev_action = self._events[i - 1].action_type
                self._transitions[prev_action][event.action_type] += 1

    def record_task(
        self,
        action_type: str,
        goal_text: str = "",
        intent_type: str = "",
        success: bool = True,
        timestamp: Optional[str] = None
    ) -> TaskEvent:
        """Record a completed task for pattern learning."""
        ts = timestamp or _now()
        event = TaskEvent(
            event_id=uuid4().hex[:12],
            action_type=action_type,
            goal_text=goal_text[:200],
            intent_type=intent_type,
            timestamp=ts,
            hour_of_day=_hour_of_day(ts),
            day_of_week=_day_of_week(ts),
            success=success
        )
        self._events.append(event)
        self._save_to_db(event)

        # Update models incrementally
        key = (event.hour_of_day, event.day_of_week)
        self._temporal[key][event.action_type] += 1
        if len(self._events) >= 2:
            prev_action = self._events[-2].action_type
            self._transitions[prev_action][event.action_type] += 1

        return event

    def predict_next(
        self,
        last_action: Optional[str] = None,
        current_hour: Optional[int] = None,
        current_dow: Optional[int] = None,
        limit: int = 5
    ) -> List[Anticipation]:
        """
        Predict what the user will need next based on:
        1. Sequential patterns (what usually follows last_action)
        2. Temporal patterns (what usually happens at this time)

        Returns anticipations sorted by confidence (highest first).
        """
        hour = current_hour if current_hour is not None else _hour_of_day()
        dow = current_dow if current_dow is not None else _day_of_week()

        candidates: Dict[str, Dict[str, Any]] = {}

        # 1. Sequential prediction: what follows last_action?
        if last_action and last_action in self._transitions:
            transitions = self._transitions[last_action]
            total = sum(transitions.values())
            if total >= self.MIN_OCCURRENCES:
                for action, count in transitions.most_common(10):
                    conf = count / total
                    if conf >= self.MIN_CONFIDENCE:
                        if action not in candidates or candidates[action]["confidence"] < conf:
                            candidates[action] = {
                                "confidence": conf,
                                "reason": f"After '{last_action}', '{action}' follows {count}/{total} times ({conf:.0%})",
                                "source": "sequential",
                            }

        # 2. Temporal prediction: what usually happens at this hour/dow?
        time_key = (hour, dow)
        if time_key in self._temporal:
            temporal = self._temporal[time_key]
            total = sum(temporal.values())
            if total >= self.MIN_OCCURRENCES:
                for action, count in temporal.most_common(10):
                    conf = (count / total) * 0.7  # Temporal patterns weighted lower
                    if conf >= self.MIN_CONFIDENCE:
                        if action not in candidates or candidates[action]["confidence"] < conf:
                            day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                                       "Friday", "Saturday", "Sunday"][dow]
                            candidates[action] = {
                                "confidence": conf,
                                "reason": f"At {hour}:00 on {day_name}, '{action}' occurs {count}/{total} times",
                                "source": "temporal",
                            }

        # Build anticipations
        anticipations: List[Anticipation] = []
        for action, info in candidates.items():
            requires_approval = action in self.SENSITIVE_ACTIONS
            anticipations.append(Anticipation(
                anticipation_id=uuid4().hex[:12],
                predicted_action=action,
                confidence=round(info["confidence"], 3),
                reason=info["reason"],
                suggested_preparation=self._suggest_preparation(action),
                requires_approval=requires_approval,
                context={"source": info["source"], "hour": hour, "dow": dow}
            ))

        anticipations.sort(key=lambda a: a.confidence, reverse=True)
        return anticipations[:limit]

    def _suggest_preparation(self, action_type: str) -> str:
        """Suggest what to prepare for an anticipated action."""
        preparations = {
            "web_search": "Pre-warm browser and search index",
            "search_files": "Index recent filesystem changes",
            "open_application": "Pre-check application availability",
            "diagnostic": "Pre-collect system health metrics",
            "formulate_answer": "Pre-fetch relevant memory context",
            "daily_briefing": "Pre-aggregate news and calendar events",
            "screen_capture": "Verify screen capture tool availability",
        }
        return preparations.get(action_type, f"Prepare resources for {action_type}")

    def frequent_actions(self, hour: Optional[int] = None,
                          min_count: int = MIN_OCCURRENCES) -> List[Dict[str, Any]]:
        """List frequently performed actions, optionally filtered by hour."""
        action_counts: Counter = Counter()
        for event in self._events:
            if hour is None or event.hour_of_day == hour:
                action_counts[event.action_type] += 1

        return [
            {"action_type": action, "count": count}
            for action, count in action_counts.most_common()
            if count >= min_count
        ]

    def total_events(self) -> int:
        return len(self._events)
