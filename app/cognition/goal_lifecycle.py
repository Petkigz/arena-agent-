"""Goal Lifecycle & State Progression Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List
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
    WAITING_FOR_EVIDENCE = "waiting_for_evidence"
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
        GoalLifecycleState.WAITING_FOR_EVIDENCE,
        GoalLifecycleState.REASSESSING
    ],
    GoalLifecycleState.WAITING_FOR_EVIDENCE: [
        GoalLifecycleState.REASSESSING,
        GoalLifecycleState.REPLAN,
        GoalLifecycleState.EXECUTING,
        GoalLifecycleState.FAILED,
        GoalLifecycleState.DEFERRED,
        GoalLifecycleState.WAITING_FOR_USER
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


# ── Typed park reasons (owner-pasted architecture audit 2026-09-09) ────────
# 'waiting_for_evidence' had become a generic failure bucket: an
# unresolvable app name, an underspecified intent, a missing capability,
# a pending approval, and a dead model provider all parked under the
# SAME state — and the auto-recheck then replayed the full chat cycle
# for cases that re-running can never fix ('Have you tried Task
# Manager?' on loop). Parked goals now carry a typed reason; ONLY
# observation-pending goals are eligible for evidence rechecks. The
# lifecycle state itself is unchanged (every existing reader keeps
# working) — the reason is an added column.
PARK_OBSERVATION_PENDING = "OBSERVATION_PENDING"
PARK_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
PARK_TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
PARK_CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
PARK_AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
PARK_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"

PARK_REASONS = frozenset({
    PARK_OBSERVATION_PENDING, PARK_NEEDS_CLARIFICATION, PARK_TARGET_AMBIGUOUS,
    PARK_CAPABILITY_UNAVAILABLE, PARK_AUTHORIZATION_REQUIRED,
    PARK_PROVIDER_UNAVAILABLE,
})

# Legacy rows (NULL/'') predate the taxonomy and keep the historical
# behavior: bounded rechecks (3 attempts) plus follow-up supersession.
RECHECK_ELIGIBLE_PARK_REASONS = frozenset({PARK_OBSERVATION_PENDING, ""})

_PARK_STATUS_GUIDANCE = {
    PARK_OBSERVATION_PENDING:
        "no background task is running. Ask me to re-check and I'll "
        "gather evidence again.",
    PARK_NEEDS_CLARIFICATION:
        "I need your answer before this can continue — it will not "
        "auto-recheck.",
    PARK_TARGET_AMBIGUOUS:
        "tell me which target you mean — it will not auto-recheck.",
    PARK_CAPABILITY_UNAVAILABLE:
        "I have no registered capability for the core action — it will "
        "not auto-recheck.",
    PARK_AUTHORIZATION_REQUIRED:
        "waiting on your approval — it will not auto-recheck.",
    PARK_PROVIDER_UNAVAILABLE:
        "the local model server was unavailable — ask me to re-check "
        "once it is back.",
}


def classify_park_reason(result: Dict[str, object]) -> str:
    """Why did this cycle park? Signal-first, tolerant of missing keys;
    the default is the honest legacy meaning (an action happened or was
    attempted and its outcome awaits observation)."""
    reply = str(result.get("assistant_reply") or result.get("reply") or "")
    reason = str(result.get("reason") or "")
    blob = f"{reply} {reason}".lower()

    if result.get("simulated") is True or "[simulated response" in blob:
        return PARK_PROVIDER_UNAVAILABLE
    if result.get("approval_request") or (
            "approval" in reason.lower() and "requir" in reason.lower()) or (
            # Phase 4 (owner plan 2026-09-10): the action contract's explicit
            # approval ask — narrow phrase, emitted only by action_contract.
            "needs your approval" in blob or "say 'approve'" in blob):
        return PARK_AUTHORIZATION_REQUIRED
    caps = result.get("capability_status") or result.get("capability_status_map") or {}
    if isinstance(caps, dict) and any(
            isinstance(v, dict) and v.get("status") == "unresolved"
            for v in caps.values()):
        return PARK_CAPABILITY_UNAVAILABLE
    if "capability phrase unresolved" in blob or "unresolved capability" in blob:
        return PARK_CAPABILITY_UNAVAILABLE
    if "ambiguous" in blob:
        return PARK_TARGET_AMBIGUOUS
    if (result.get("question_asked") or result.get("owner_question")
            or result.get("pending_question")):
        return PARK_NEEDS_CLARIFICATION
    return PARK_OBSERVATION_PENDING


def park_status_line(reason: str) -> str:
    """The owner-visible parked-status line for a typed reason. Keeps the
    long-standing 'waiting_for_evidence' wording (pinned by the UX
    regressions and familiar to the owner) and ADDS the typed reason."""
    reason = reason if reason in PARK_REASONS else PARK_OBSERVATION_PENDING
    return (f"[status: goal parked as waiting_for_evidence — {reason}: "
            f"{_PARK_STATUS_GUIDANCE[reason]}]")
