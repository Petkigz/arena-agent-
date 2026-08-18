"""Goal Lifecycle & State Progression Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from uuid import uuid4
from app.utils.logger import app_logger

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

VALID_TRANSITIONS: Dict[GoalLifecycleState, List[GoalLifecycleState]] = {
    GoalLifecycleState.CREATED: [
        GoalLifecycleState.UNDERSTOOD,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.DEFERRED,
        GoalLifecycleState.BLOCKED
    ],
    GoalLifecycleState.UNDERSTOOD: [
        GoalLifecycleState.PLANNED,
        GoalLifecycleState.EXECUTING,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.DEFERRED,
        GoalLifecycleState.BLOCKED,
        GoalLifecycleState.WAITING_FOR_USER
    ],
    GoalLifecycleState.PLANNED: [
        GoalLifecycleState.EXECUTING,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.BLOCKED,
        GoalLifecycleState.WAITING_FOR_USER,
        GoalLifecycleState.DEFERRED
    ],
    GoalLifecycleState.EXECUTING: [
        GoalLifecycleState.VERIFYING,
        GoalLifecycleState.ACHIEVED,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.BLOCKED,
        GoalLifecycleState.WAITING_FOR_USER,
        GoalLifecycleState.DEFERRED
    ],
    GoalLifecycleState.VERIFYING: [
        GoalLifecycleState.ACHIEVED,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.BLOCKED,
        GoalLifecycleState.DEFERRED,
        GoalLifecycleState.REASSESSING
    ],
    GoalLifecycleState.FAILED: [
        GoalLifecycleState.REASSESSING,
        GoalLifecycleState.REPLAN
    ],
    GoalLifecycleState.REASSESSING: [
        GoalLifecycleState.REPLAN,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.EXECUTING
    ],
    GoalLifecycleState.REPLAN: [
        GoalLifecycleState.PLANNED,
        GoalLifecycleState.EXECUTING,
        GoalLifecycleState.VERIFYING,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.BLOCKED
    ],
    GoalLifecycleState.BLOCKED: [
        GoalLifecycleState.REASSESSING,
        GoalLifecycleState.REPLAN,
        GoalLifecycleState.WAITING_FOR_USER,
        GoalLifecycleState.FAILED
    ],
    GoalLifecycleState.DEFERRED: [
        GoalLifecycleState.UNDERSTOOD,
        GoalLifecycleState.PLANNED,
        GoalLifecycleState.EXECUTING
    ],
    GoalLifecycleState.WAITING_FOR_USER: [
        GoalLifecycleState.EXECUTING,
        GoalLifecycleState.PLANNED,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.BLOCKED
    ],
    GoalLifecycleState.ACHIEVED: [
        GoalLifecycleState.CREATED,
        GoalLifecycleState.UNDERSTOOD
    ]
}

class InvalidStateTransitionError(ValueError):
    """Raised when a goal tracker transition violates state machine rules."""
    pass

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

    def is_valid_transition(self, to_state: GoalLifecycleState) -> bool:
        if to_state == self.current_state:
            return True
        allowed = VALID_TRANSITIONS.get(self.current_state, [])
        return to_state in allowed

    def transition(self, to_state: GoalLifecycleState, reason: str, strict: bool = True) -> GoalLifecycleState:
        if strict and not self.is_valid_transition(to_state):
            err_msg = f"GoalTracker [{self.goal_id[:8]}]: Invalid lifecycle transition from '{self.current_state.value}' to '{to_state.value}'."
            app_logger.error(err_msg)
            raise InvalidStateTransitionError(err_msg)

        transition_record = GoalStateTransition(
            from_state=self.current_state,
            to_state=to_state,
            reason=reason
        )
        self.history.append(transition_record)
        self.current_state = to_state
        return self.current_state
