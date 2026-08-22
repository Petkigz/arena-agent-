"""Persistent owner control plane for action authorization.

The cognitive system may consider and recommend broadly, but execution authority
comes from this owner-controlled policy. The default preserves the historical
behavior (Levels 0-2 autonomous, Level 3 requires approval) while allowing the
owner to tighten control globally or per action.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger


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
        return self.update({"paused": bool(paused)})

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
        if policy.mode in (ControlMode.APPROVE_EVERY_ACTION, ControlMode.APPROVE_EACH_PLAN):
            scope = "action" if policy.mode == ControlMode.APPROVE_EVERY_ACTION else "plan"
            return OwnerControlDecision(False, True, f"Owner approval is required for every {scope}.", policy.mode.value)
        if action in policy.require_approval_actions:
            return OwnerControlDecision(False, True, f"Action '{action}' requires approval by owner policy.", policy.mode.value)
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


owner_control_store = OwnerControlStore()
