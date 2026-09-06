"""Bounded prospective-memory helpers for conversation-turn reminders.

This module parses only an explicit, narrow request shape. It does not infer a
reminder from arbitrary prose: scheduling remains owner-directed and the
underlying durable store is CalendarService.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _turn_count(value: str) -> Optional[int]:
    value = str(value or "").strip().lower()
    if value.isdigit():
        count = int(value)
    else:
        count = _NUMBER_WORDS.get(value)
    return count if count and count > 0 else None


def parse_turn_reminder_request(text: str) -> Optional[Dict[str, Any]]:
    """Parse an explicit ``remind me in N turns`` request.

    Supported examples include:
    - ``Remind me in three turns to review the deployment``
    - ``remind me in 2 turns about the report``
    - ``remind me in five turns`` (uses a neutral follow-up title)

    Ambiguous language returns ``None`` and remains on the normal cognitive
    route rather than creating an unrequested commitment.
    """
    match = re.search(
        r"\bremind\s+me\s+in\s+(?P<count>\d+|[a-z]+)\s+turns?\b"
        r"(?:\s+(?P<connector>to|about|that)\s+(?P<title>[^\n.!?]+))?",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    turns = _turn_count(match.group("count"))
    if turns is None:
        return None
    title = str(match.group("title") or "Follow up on this conversation").strip()
    title = re.sub(r"\s+", " ", title).strip(" ,:;")
    if not title:
        title = "Follow up on this conversation"
    return {
        "turns": turns,
        "title": title[:500],
        "connector": match.group("connector") or "",
    }
