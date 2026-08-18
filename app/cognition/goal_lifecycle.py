"""Goal Lifecycle & State Progression Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from uuid import uuid4

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class GoalLifecycleState(str, Enum):
    CREATED = "created"
    UNDERSTOOD = "understood"
    PLANNED = "planned"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    ACHIEVED = "achieved"
    FAILED = "failed"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    WAITING_FOR_USER = "waiting_for_user"
    REASSESSING = "reassessing"
    REPLAN = "replan"

@dataclass
class GoalStateTransition:
    from_state: GoalLifecycleState
    to_state: GoalLifecycleState
    reason: str
    timestamp: str = field(default_factory=_now)

@dataclass
class GoalTracker:
    goal_id: str = field(default_factory=lambda: f"goal_{uuid4().hex[:8]}")
    user_query: str = ""
    current_state: GoalLifecycleState = GoalLifecycleState.CREATED
    history: List[GoalStateTransition] = field(default_factory=list)

    def transition(self, to_state: GoalLifecycleState, reason: str) -> GoalLifecycleState:
        transition_record = GoalStateTransition(
            from_state=self.current_state,
            to_state=to_state,
            reason=reason
        )
        self.history.append(transition_record)
        self.current_state = to_state
        return self.current_state
