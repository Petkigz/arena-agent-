"""Ephemeral working memory for the active cognitive loop with clear boundary contracts."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BlackboardEntry:
    value: Any
    source: Optional[str] = None
    confidence: Optional[float] = None
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = _now()


class Blackboard:
    """
    P1-B: Dynamic Working Memory Workspace for reasoning artifacts.
    Distinct from CognitiveState (which holds stable, structured system state):
    - Blackboard stores: candidate hypotheses, evidence, temporary observations, and scratchpad thoughts.
    """

    # Reserved workspace keys
    KEY_CANDIDATE_PLANS = "candidate_plans"
    KEY_ACTIVE_HYPOTHESES = "active_hypotheses"
    KEY_PENDING_OBSERVATIONS = "pending_observations"
    KEY_SCRATCHPAD_THOUGHTS = "scratchpad_thoughts"

    def __init__(self) -> None:
        self._entries: Dict[str, BlackboardEntry] = {}

    def set(
        self,
        key: str,
        value: Any,
        *,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> None:
        if not key or not key.strip():
            raise ValueError("Blackboard key cannot be empty")
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        self._entries[key] = BlackboardEntry(value, source, confidence)

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._entries.get(key)
        return default if entry is None else entry.value

    def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        return self._entries.get(key)

    def has(self, key: str) -> bool:
        return key in self._entries

    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        self._entries.clear()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {key: asdict(entry) for key, entry in self._entries.items()}

    def keys(self):
        return self._entries.keys()

    def __len__(self) -> int:
        return len(self._entries)
