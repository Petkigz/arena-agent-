"""Pending-approval store for Level-3 (sensitive) actions.

When the ActionGate blocks a Level-3 proposal, the runtime records it here as
`pending_approval`. The owner then approves/denies via the `action_approval`
WebSocket message (handled in the message router), and the stored decision can be
used to resume execution.

In-memory (a full resume pipeline is future work) but provides a consistent,
queryable surface and fixes the previously-dead `action_approval` message.
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
    status: str = "pending"  # pending | approved | denied
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "conversation_id": self.conversation_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
        }


class ApprovalStore:
    """Thread-safe registry of pending owner-approval requests."""

    def __init__(self) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def add(self, conversation_id: str, action_type: str, payload: Dict[str, Any], reason: str) -> ApprovalRequest:
        req = ApprovalRequest(
            action_id=uuid4().hex[:12],
            conversation_id=conversation_id,
            action_type=action_type,
            payload=payload,
            reason=reason,
        )
        with self._lock:
            self._requests[req.action_id] = req
        return req

    def decide(self, action_id: str, approved: bool, note: str = "") -> Optional[ApprovalRequest]:
        with self._lock:
            req = self._requests.get(action_id)
            if req is None:
                return None
            req.status = "approved" if approved else "denied"
            req.payload = {**req.payload, "approval_note": note}
        return req

    def list_pending(self) -> List[ApprovalRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.status == "pending"]

    def get(self, action_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._requests.get(action_id)


# Module-level singleton used by the runtime + message router.
approval_store = ApprovalStore()
