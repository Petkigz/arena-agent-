"""Persistent recommendation/decision ledger for owner-reviewed actions.

The ledger persists review records, never reusable authority. Exact execution
grants remain short-lived and memory-only in owner_control.AuthorizationStore.
After restart an approved historical record is still visible, but its old grant
is absent and execution requires a fresh recommendation/authorization cycle.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger


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
    status: str = "pending"
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRequest":
        return cls(
            action_id=str(data["action_id"]),
            conversation_id=str(data.get("conversation_id", "")),
            action_type=str(data.get("action_type", "")),
            payload=dict(data.get("payload") or {}),
            reason=str(data.get("reason", "")),
            goal_text=str(data.get("goal_text", "")),
            proposal_id=str(data.get("proposal_id", "")),
            recommendation_reason=str(data.get("recommendation_reason", "")),
            alternatives_considered=list(data.get("alternatives_considered") or []),
            predicted_outcome=dict(data.get("predicted_outcome") or {}),
            status=str(data.get("status", "pending")),
            created_at=str(data.get("created_at") or _now()),
            decided_at=data.get("decided_at"),
            decision_note=str(data.get("decision_note", "")),
            authorization_id=data.get("authorization_id"),
        )


class ApprovalStore:
    """Thread-safe owner-review ledger with optional atomic JSON persistence."""

    MAX_RECORDS = 5000

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        self._requests: Dict[str, ApprovalRequest] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            records = raw if isinstance(raw, list) else raw.get("requests", [])
            for item in records:
                request = ApprovalRequest.from_dict(item)
                self._requests[request.action_id] = request
        except Exception as exc:
            # Review corruption never broadens authority; grants are separate and
            # memory-only. Keep an empty ledger and surface the diagnostic.
            app_logger.error(f"Could not load approval ledger: {exc}")

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = sorted(self._requests.values(), key=lambda item: item.created_at)
        if len(records) > self.MAX_RECORDS:
            pending = [item for item in records if item.status == "pending"][-self.MAX_RECORDS:]
            terminal = [item for item in records if item.status != "pending"]
            slots = max(0, self.MAX_RECORDS - len(pending))
            keep_terminal = terminal[-slots:] if slots else []
            records = pending + keep_terminal
            self._requests = {item.action_id: item for item in records}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps([item.to_dict() for item in records], indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

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
        # JSON round-trip creates an immutable snapshot relative to caller-owned
        # nested dict/list objects and rejects non-serializable payloads early.
        payload_snapshot = json.loads(json.dumps(payload, allow_nan=False))
        req = ApprovalRequest(
            action_id=uuid4().hex[:12],
            conversation_id=conversation_id,
            action_type=action_type,
            payload=payload_snapshot,
            reason=reason,
            goal_text=goal_text,
            proposal_id=proposal_id,
            recommendation_reason=recommendation_reason,
            alternatives_considered=json.loads(json.dumps(alternatives_considered or [])),
            predicted_outcome=json.loads(json.dumps(predicted_outcome or {}, allow_nan=False)),
        )
        with self._lock:
            self._requests[req.action_id] = req
            self._persist()
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
            self._persist()
            return req

    def list_pending(self) -> List[ApprovalRequest]:
        with self._lock:
            return sorted(
                (r for r in self._requests.values() if r.status == "pending"),
                key=lambda item: item.created_at,
            )

    def list_all(self, limit: int = 500) -> List[ApprovalRequest]:
        with self._lock:
            return sorted(
                self._requests.values(), key=lambda item: item.created_at, reverse=True
            )[:max(1, min(int(limit), self.MAX_RECORDS))]

    def get(self, action_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._requests.get(action_id)


approval_store = ApprovalStore(settings.DATA_DIR / "approval_requests.json")
