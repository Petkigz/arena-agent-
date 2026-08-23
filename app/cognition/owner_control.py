"""Persistent owner control plane for action authorization.

The cognitive system may consider and recommend broadly, but execution authority
comes from this owner-controlled policy. The default preserves the historical
behavior (Levels 0-2 autonomous, Level 3 requires approval) while allowing the
owner to tighten control globally or per action.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


_active_plan_scope: ContextVar[Optional[tuple[str, int]]] = ContextVar(
    "arena_active_plan_scope", default=None
)


@contextmanager
def authorized_plan_scope(plan_id: str, max_safety_level: int = 2):
    """Temporarily delegate non-sensitive actions for one approved plan.

    ContextVars keep the scope local to the current execution context/thread.
    Level 3 and per-action approval rules are never covered by a plan grant.
    """
    token = _active_plan_scope.set((str(plan_id), max(0, min(2, int(max_safety_level)))))
    try:
        yield
    finally:
        _active_plan_scope.reset(token)


class ControlMode(str, Enum):
    OBSERVE_ONLY = "observe_only"
    SUGGEST_ONLY = "suggest_only"
    APPROVE_EVERY_ACTION = "approve_every_action"
    APPROVE_EACH_PLAN = "approve_each_plan"
    BOUNDED_AUTONOMY = "bounded_autonomy"
    CUSTOM = "custom"


@dataclass
class OwnerControlPolicy:
    mode: ControlMode = ControlMode.BOUNDED_AUTONOMY
    paused: bool = False
    max_autonomous_level: int = 2
    require_approval_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    custom_autonomous_actions: list[str] = field(default_factory=list)
    revision: int = 1

    def normalized(self) -> "OwnerControlPolicy":
        self.max_autonomous_level = max(0, min(2, int(self.max_autonomous_level)))
        self.require_approval_actions = _normalize_actions(self.require_approval_actions)
        self.blocked_actions = _normalize_actions(self.blocked_actions)
        self.custom_autonomous_actions = _normalize_actions(self.custom_autonomous_actions)
        if not isinstance(self.mode, ControlMode):
            self.mode = ControlMode(str(self.mode))
        return self

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


@dataclass(frozen=True)
class OwnerControlDecision:
    allowed: bool
    requires_approval: bool
    reason: str
    mode: str


def _normalize_actions(actions: Iterable[str]) -> list[str]:
    return sorted({str(action).strip().lower() for action in actions if str(action).strip()})


class OwnerControlStore:
    """Thread-safe policy store with atomic persistence and fail-closed updates."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path is not None else settings.DATA_DIR / "owner_control.json"
        self._lock = threading.RLock()
        self._policy = self._load()

    def _load(self) -> OwnerControlPolicy:
        if not self.path.exists():
            return OwnerControlPolicy()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return OwnerControlPolicy(
                mode=ControlMode(raw.get("mode", ControlMode.BOUNDED_AUTONOMY.value)),
                paused=bool(raw.get("paused", False)),
                max_autonomous_level=int(raw.get("max_autonomous_level", 2)),
                require_approval_actions=list(raw.get("require_approval_actions", [])),
                blocked_actions=list(raw.get("blocked_actions", [])),
                custom_autonomous_actions=list(raw.get("custom_autonomous_actions", [])),
                revision=max(1, int(raw.get("revision", 1))),
            ).normalized()
        except Exception as exc:
            # A malformed control file must never broaden authority.
            app_logger.error(f"Could not load owner control policy; execution paused: {exc}")
            return OwnerControlPolicy(paused=True)

    def get_policy(self) -> OwnerControlPolicy:
        with self._lock:
            data = self._policy.to_dict()
            return OwnerControlPolicy(
                mode=ControlMode(data["mode"]),
                paused=data["paused"],
                max_autonomous_level=data["max_autonomous_level"],
                require_approval_actions=list(data["require_approval_actions"]),
                blocked_actions=list(data["blocked_actions"]),
                custom_autonomous_actions=list(data["custom_autonomous_actions"]),
                revision=data["revision"],
            )

    def update(self, patch: Dict[str, Any]) -> OwnerControlPolicy:
        allowed_keys = {
            "mode", "paused", "max_autonomous_level", "require_approval_actions",
            "blocked_actions", "custom_autonomous_actions",
        }
        unknown = set(patch) - allowed_keys
        if unknown:
            raise ValueError(f"Unknown owner-control field(s): {', '.join(sorted(unknown))}")

        with self._lock:
            current = self._policy.to_dict()
            current.update({k: v for k, v in patch.items() if v is not None})
            policy = OwnerControlPolicy(
                mode=ControlMode(current["mode"]),
                paused=bool(current["paused"]),
                max_autonomous_level=int(current["max_autonomous_level"]),
                require_approval_actions=list(current["require_approval_actions"]),
                blocked_actions=list(current["blocked_actions"]),
                custom_autonomous_actions=list(current["custom_autonomous_actions"]),
                revision=self._policy.revision + 1,
            ).normalized()
            self._persist(policy)
            self._policy = policy
            audit_logger.warning(
                f"Owner control policy updated: mode={policy.mode.value}, "
                f"paused={policy.paused}, revision={policy.revision}"
            )
            return self.get_policy()

    def set_paused(self, paused: bool) -> OwnerControlPolicy:
        policy = self.update({"paused": bool(paused)})
        if paused and self is globals().get("owner_control_store"):
            # Emergency stop on the live singleton also invalidates authority
            # issued before the stop. Isolated test/config stores do not affect it.
            grants = globals().get("authorization_store")
            if grants is not None:
                grants.revoke_all()
            try:
                from app.cognition.execution_control import execution_control_registry
                for execution in execution_control_registry.list(active_only=True, limit=500):
                    execution_control_registry.request_cancel(execution.execution_id)
            except Exception as exc:
                app_logger.warning(f"Could not request cancellation of active executions: {exc}")
        return policy

    def _persist(self, policy: OwnerControlPolicy) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(policy.to_dict(), indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def evaluate(self, action_type: str, safety_level: int) -> OwnerControlDecision:
        policy = self.get_policy()
        action = str(action_type).strip().lower()

        if policy.paused:
            return OwnerControlDecision(False, False, "Owner emergency pause is active.", policy.mode.value)
        if action in policy.blocked_actions:
            return OwnerControlDecision(False, False, f"Action '{action}' is blocked by owner policy.", policy.mode.value)
        if policy.mode == ControlMode.OBSERVE_ONLY:
            return OwnerControlDecision(False, False, "Observe-only mode forbids action execution.", policy.mode.value)
        if policy.mode == ControlMode.SUGGEST_ONLY:
            return OwnerControlDecision(False, False, "Suggest-only mode allows recommendations but not execution.", policy.mode.value)
        if action in policy.require_approval_actions:
            return OwnerControlDecision(False, True, f"Action '{action}' requires approval by owner policy.", policy.mode.value)
        if policy.mode == ControlMode.APPROVE_EVERY_ACTION:
            return OwnerControlDecision(False, True, "Owner approval is required for every action.", policy.mode.value)
        if policy.mode == ControlMode.APPROVE_EACH_PLAN:
            active_plan = _active_plan_scope.get()
            if active_plan is None or int(safety_level) > active_plan[1]:
                return OwnerControlDecision(False, True, "Owner approval is required for this plan.", policy.mode.value)
            return OwnerControlDecision(
                True,
                False,
                f"Allowed within owner-approved plan '{active_plan[0]}'.",
                policy.mode.value,
            )
        if policy.mode == ControlMode.CUSTOM and action not in policy.custom_autonomous_actions:
            return OwnerControlDecision(False, True, f"Action '{action}' is outside the custom autonomous allowlist.", policy.mode.value)
        if int(safety_level) > policy.max_autonomous_level:
            return OwnerControlDecision(
                False,
                True,
                f"Action Level {safety_level} exceeds owner's autonomous limit "
                f"({policy.max_autonomous_level}).",
                policy.mode.value,
            )
        return OwnerControlDecision(True, False, "Allowed within owner-delegated authority.", policy.mode.value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_digest(payload: Dict[str, Any]) -> str:
    """Return a stable digest for an exact JSON payload.

    Authorization is intentionally parameter-bound. Changing a recipient, path,
    command, nested action, or any other value produces a different digest.
    """
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass
class AuthorizationGrant:
    authorization_id: str
    action_type: str
    payload_sha256: str
    issued_at: str
    expires_at: str
    max_uses: int = 1
    uses: int = 0
    revoked: bool = False
    source_approval_id: Optional[str] = None
    plan_id: Optional[str] = None

    @property
    def active(self) -> bool:
        try:
            expires = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        return not self.revoked and self.uses < self.max_uses and _utcnow() < expires

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self) | {"active": self.active}


@dataclass(frozen=True)
class AuthorizationDecision:
    valid: bool
    reason: str
    grant: Optional[AuthorizationGrant] = None


class AuthorizationStore:
    """Short-lived, exact-payload execution grants.

    Grants are intentionally memory-only: a process restart revokes every grant.
    This avoids stale authority surviving a restart or policy recovery.
    """

    def __init__(self) -> None:
        self._grants: Dict[str, AuthorizationGrant] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        action_type: str,
        payload: Dict[str, Any],
        *,
        ttl_seconds: int = 300,
        max_uses: int = 1,
        source_approval_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> AuthorizationGrant:
        ttl = max(1, min(3600, int(ttl_seconds)))
        uses = max(1, min(100, int(max_uses)))
        now = _utcnow()
        grant = AuthorizationGrant(
            authorization_id=f"auth_{uuid4().hex[:16]}",
            action_type=str(action_type).strip().lower(),
            payload_sha256=payload_digest(payload),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl)).isoformat(),
            max_uses=uses,
            source_approval_id=source_approval_id,
            plan_id=plan_id,
        )
        with self._lock:
            self._grants[grant.authorization_id] = grant
        audit_logger.warning(
            f"Scoped authorization issued: {grant.authorization_id}, action={grant.action_type}, "
            f"ttl={ttl}s, max_uses={uses}"
        )
        return grant

    def validate(
        self,
        authorization_id: str,
        action_type: str,
        payload: Dict[str, Any],
        *,
        plan_id: Optional[str] = None,
    ) -> AuthorizationDecision:
        with self._lock:
            grant = self._grants.get(authorization_id)
            if grant is None:
                return AuthorizationDecision(False, "Authorization grant not found.")
            if not grant.active:
                return AuthorizationDecision(False, "Authorization grant is expired, revoked, or exhausted.", grant)
            if grant.action_type != str(action_type).strip().lower():
                return AuthorizationDecision(False, "Authorization action type does not match proposal.", grant)
            try:
                digest = payload_digest(payload)
            except (TypeError, ValueError):
                return AuthorizationDecision(False, "Proposal payload is not canonical JSON.", grant)
            if grant.payload_sha256 != digest:
                return AuthorizationDecision(False, "Authorization payload does not match proposal.", grant)
            if grant.plan_id is not None and grant.plan_id != plan_id:
                return AuthorizationDecision(False, "Authorization plan scope does not match proposal.", grant)
            return AuthorizationDecision(True, "Exact scoped authorization is valid.", grant)

    def consume(
        self,
        authorization_id: str,
        action_type: str,
        payload: Dict[str, Any],
        *,
        plan_id: Optional[str] = None,
    ) -> AuthorizationDecision:
        with self._lock:
            decision = self.validate(
                authorization_id, action_type, payload, plan_id=plan_id
            )
            if not decision.valid or decision.grant is None:
                return decision
            decision.grant.uses += 1
            audit_logger.warning(
                f"Scoped authorization consumed: {authorization_id} "
                f"({decision.grant.uses}/{decision.grant.max_uses})"
            )
            return AuthorizationDecision(True, "Exact scoped authorization consumed.", decision.grant)

    def revoke(self, authorization_id: str) -> bool:
        with self._lock:
            grant = self._grants.get(authorization_id)
            if grant is None:
                return False
            grant.revoked = True
            audit_logger.warning(f"Scoped authorization revoked: {authorization_id}")
            return True

    def revoke_all(self) -> int:
        with self._lock:
            active = [grant for grant in self._grants.values() if grant.active]
            for grant in active:
                grant.revoked = True
            if active:
                audit_logger.warning(f"All scoped authorizations revoked: {len(active)}")
            return len(active)

    def list_active(self) -> list[AuthorizationGrant]:
        with self._lock:
            return [grant for grant in self._grants.values() if grant.active]


owner_control_store = OwnerControlStore()
authorization_store = AuthorizationStore()
