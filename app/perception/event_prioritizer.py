"""Phase 4B: Event-Driven Cognition.

Prioritizes environment events and determines which ones should trigger
cognitive evaluation. Events are classified as:
  - urgent: requires immediate attention (process crash, device disconnect)
  - actionable: may enable pending goals (printer online, file appeared)
  - informational: recorded but doesn't trigger action

Also handles event deduplication and throttling.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Event Priority Classification ────────────────────────────────────

PRIORITY_LEVELS = {
    "urgent": 3,
    "actionable": 2,
    "informational": 1,
}

# Rules for automatic priority classification
_URGENT_PATTERNS = [
    "crashed", "error", "failed", "disconnect", "offline",
    "permission_denied", "segfault", "killed", "oom",
]

_ACTIONABLE_PATTERNS = [
    "appeared", "connected", "online", "available", "ready",
    "completed", "finished", "done",
]


def classify_priority(change_type: str, subject: str, current_state: Any = None) -> str:
    """Classify event priority based on change type and subject."""
    text = f"{change_type} {subject} {current_state}".lower()

    for pattern in _URGENT_PATTERNS:
        if pattern in text:
            return "urgent"

    for pattern in _ACTIONABLE_PATTERNS:
        if pattern in text:
            return "actionable"

    return "informational"


# ── Cognitive Trigger Rules ──────────────────────────────────────────

@dataclass(frozen=True)
class TriggerRule:
    """Rule that determines when an event should trigger cognitive evaluation."""
    event_pattern: str     # glob-like pattern: "process.*", "device.*"
    min_priority: str = "informational"
    description: str = ""


DEFAULT_TRIGGER_RULES = [
    TriggerRule("process.disappeared", "actionable", "Process stopped — may affect pending goals"),
    TriggerRule("process.appeared", "informational", "New process — may indicate successful launch"),
    TriggerRule("device.disconnected", "urgent", "Device lost — affects device-dependent goals"),
    TriggerRule("device.connected", "actionable", "Device available — may enable pending goals"),
    TriggerRule("file.appeared", "actionable", "File appeared — may satisfy pending file goals"),
    TriggerRule("resource.*", "informational", "Resource change — informational"),
]


# ── Event Prioritizer ────────────────────────────────────────────────

class EventPrioritizer:
    """
    Manages event prioritization, deduplication, and cognitive trigger decisions.

    Usage:
        prioritizer = EventPrioritizer()
        decision = prioritizer.evaluate(change)
        if decision.should_trigger:
            # Run cognitive evaluation
    """

    # Minimum seconds between processing duplicate events for the same subject
    DEDUP_WINDOW = 5.0

    def __init__(
        self,
        trigger_rules: Optional[List[TriggerRule]] = None,
        pending_goals: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        self._rules = trigger_rules or list(DEFAULT_TRIGGER_RULES)
        self._pending_goals = pending_goals or []
        self._recent_events: Dict[str, float] = {}  # subject → last_event_time
        self._stats: Dict[str, int] = defaultdict(int)

    def set_pending_goals(self, goals: List[Dict[str, Any]]) -> None:
        """Update the list of pending (unfulfilled) goals for relevance matching."""
        self._pending_goals = goals

    def evaluate(self, change: Any) -> 'EventDecision':
        """
        Evaluate an environment change and decide what to do.
        Returns an EventDecision with priority, should_trigger, and reason.
        """
        change_type = getattr(change, "change_type", "unknown")
        subject = getattr(change, "subject", "unknown")
        priority = getattr(change, "priority", None) or classify_priority(change_type, subject)

        # Deduplication
        dedup_key = f"{change_type}:{subject}"
        now = time.time()
        last_time = self._recent_events.get(dedup_key, 0)
        if now - last_time < self.DEDUP_WINDOW:
            self._stats["deduplicated"] += 1
            return EventDecision(
                priority=priority,
                should_trigger=False,
                reason="deduplicated",
                relevant_goals=[]
            )
        self._recent_events[dedup_key] = now

        # Check trigger rules
        event_key = f"{change.source}.{change_type}" if hasattr(change, "source") else change_type
        matched_rule = self._match_rule(event_key, priority)

        # Check relevance to pending goals
        relevant_goals = self._find_relevant_goals(subject, change_type)

        # Decision
        should_trigger = False
        reason = "informational"

        if priority == "urgent":
            should_trigger = True
            reason = f"Urgent: {change_type} on {subject}"
        elif relevant_goals:
            should_trigger = True
            reason = f"Relevant to {len(relevant_goals)} pending goal(s): {change_type} on {subject}"
        elif matched_rule and PRIORITY_LEVELS.get(priority, 0) >= PRIORITY_LEVELS.get(matched_rule.min_priority, 0):
            should_trigger = True
            reason = matched_rule.description or f"Trigger rule matched: {event_key}"

        self._stats[priority] += 1

        return EventDecision(
            priority=priority,
            should_trigger=should_trigger,
            reason=reason,
            relevant_goals=relevant_goals,
            matched_rule=matched_rule
        )

    def _match_rule(self, event_key: str, priority: str) -> Optional[TriggerRule]:
        """Find the first matching trigger rule for an event."""
        for rule in self._rules:
            # Simple pattern matching: "process.*" matches "process.disappeared"
            if rule.event_pattern.endswith(".*"):
                prefix = rule.event_pattern[:-2]
                if event_key.startswith(prefix) or event_key.split(".")[-1] == rule.event_pattern.split(".")[-1]:
                    return rule
            elif rule.event_pattern == event_key:
                return rule
        return None

    def _find_relevant_goals(self, subject: str, change_type: str) -> List[Dict[str, Any]]:
        """Find pending goals that might be affected by this change."""
        relevant = []
        subject_lower = subject.lower()

        for goal in self._pending_goals:
            goal_entities = [e.lower() for e in goal.get("entities", [])]
            goal_text = goal.get("goal_text", "").lower()

            # Check if the changed subject matches any goal entity
            if any(subject_lower in ent or ent in subject_lower for ent in goal_entities):
                relevant.append(goal)
            # Check if subject appears in goal text
            elif subject_lower in goal_text:
                relevant.append(goal)

        return relevant

    def get_stats(self) -> Dict[str, int]:
        """Return event processing statistics."""
        return dict(self._stats)


@dataclass
class EventDecision:
    """Result of event prioritization evaluation."""
    priority: str           # "urgent", "actionable", "informational"
    should_trigger: bool    # whether this should trigger cognitive evaluation
    reason: str             # why this decision was made
    relevant_goals: List[Dict[str, Any]] = field(default_factory=list)
    matched_rule: Optional[TriggerRule] = None

    @property
    def priority_level(self) -> int:
        return PRIORITY_LEVELS.get(self.priority, 0)
