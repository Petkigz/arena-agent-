"""Pending-approval store for Level-3 (sensitive) actions.

When the ActionGate blocks a Level-3 proposal, the runtime records it here as
`pending_approval`. The owner then approves/denies via the `action_approval`
WebSocket message (handled in the message router), and the stored decision can be
used to resume execution.

Approval requests are in-memory. An approval mints a separate short-lived,
single-use authorization grant bound to the exact action and payload; execution
then requires an explicit second stage through ActionGate.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalRequest:
    action_id: str
    conversation_id: str
    action_type: str
    payload: Dict[str, Any]
    reason: str
    goal_text: str = ""
    proposal_id: str = ""
    recommendation_reason: str = ""
    alternatives_considered: List[Dict[str, Any]] = field(default_factory=list)
    predicted_outcome: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | approved | denied
    created_at: str = field(default_factory=_now)
    decided_at: Optional[str] = None
    decision_note: str = ""
    authorization_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "conversation_id": self.conversation_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "reason": self.reason,
            "goal_text": self.goal_text,
            "proposal_id": self.proposal_id,
            "recommendation_reason": self.recommendation_reason,
            "alternatives_considered": self.alternatives_considered,
            "predicted_outcome": self.predicted_outcome,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "decision_note": self.decision_note,
            "authorization_id": self.authorization_id,
        }


class ApprovalStore:
    """Thread-safe registry of pending owner-approval requests."""

    def __init__(self) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def add(
        self,
        conversation_id: str,
        action_type: str,
        payload: Dict[str, Any],
        reason: str,
        goal_text: str = "",
        proposal_id: str = "",
        recommendation_reason: str = "",
        alternatives_considered: Optional[List[Dict[str, Any]]] = None,
        predicted_outcome: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            action_id=uuid4().hex[:12],
            conversation_id=conversation_id,
            action_type=action_type,
            payload=payload,
            reason=reason,
            goal_text=goal_text,
            proposal_id=proposal_id,
            recommendation_reason=recommendation_reason,
            alternatives_considered=list(alternatives_considered or []),
            predicted_outcome=dict(predicted_outcome or {}),
        )
        with self._lock:
            self._requests[req.action_id] = req
        return req

    def decide(
        self,
        action_id: str,
        approved: bool,
        note: str = "",
        ttl_seconds: int = 300,
    ) -> Optional[ApprovalRequest]:
        with self._lock:
            req = self._requests.get(action_id)
            if req is None:
                return None
            # Decisions are final. Replaying or flipping an approval must not
            # mint additional authority.
            if req.status != "pending":
                return req
            req.status = "approved" if approved else "denied"
            req.decided_at = _now()
            req.decision_note = note
            if approved:
                from app.cognition.owner_control import authorization_store
                grant = authorization_store.issue(
                    req.action_type,
                    req.payload,
                    ttl_seconds=ttl_seconds,
                    max_uses=1,
                    source_approval_id=req.action_id,
                )
                req.authorization_id = grant.authorization_id
        return req

    def list_pending(self) -> List[ApprovalRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.status == "pending"]

    def get(self, action_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._requests.get(action_id)


# Module-level singleton used by the runtime + message router.
approval_store = ApprovalStore()
