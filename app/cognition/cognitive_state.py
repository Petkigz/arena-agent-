"""Shared, serializable working state for Arena's cognitive systems."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=_now)
    last_activity: str = field(default_factory=_now)


@dataclass
class TaskState:
    task_id: Optional[str] = None
    goal: Optional[str] = None
    status: str = "idle"
    current_step: Optional[str] = None


@dataclass
class AttentionState:
    focus: Optional[str] = None
    priorities: List[str] = field(default_factory=list)
    active_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionState:
    last_action: Optional[str] = None
    last_result: Any = None
    pending_action: Optional[str] = None


@dataclass
class PredictionState:
    expected: Any = None
    actual: Any = None
    confidence: float = 0.0


@dataclass
class ResourceState:
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    ram_available_mb: Optional[float] = None
    vram_percent: Optional[float] = None
    gpu_percent: Optional[float] = None
    updated_at: str = field(default_factory=_now)


@dataclass
class CognitiveState:
    """The compact mental workspace shared by Arena subsystems.

    This is intentionally not the world model or long-term memory. Those
    systems will be introduced in later phases and can project information
    into this state when relevant to the active task.
    """

    version: int = 1
    session: SessionState = field(default_factory=SessionState)
    task: TaskState = field(default_factory=TaskState)
    attention: AttentionState = field(default_factory=AttentionState)
    reasoning: Dict[str, Any] = field(default_factory=lambda: {
        "hypotheses": [],
        "assumptions": [],
        "confidence": 0.0,
    })
    execution: ExecutionState = field(default_factory=ExecutionState)
    prediction: PredictionState = field(default_factory=PredictionState)
    resources: ResourceState = field(default_factory=ResourceState)
    world_context: Dict[str, Any] = field(default_factory=dict)
    beliefs: Dict[str, Any] = field(default_factory=dict)
    active_memories: List[str] = field(default_factory=list)
    active_skills: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()
        self.session.last_activity = self.updated_at

    def update(self, **changes: Any) -> None:
        for key, value in changes.items():
            if not hasattr(self, key):
                raise AttributeError(f"Unknown cognitive state field: {key}")
            setattr(self, key, value)
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveState":
        data = dict(data)
        data["session"] = SessionState(**data.get("session", {}))
        data["task"] = TaskState(**data.get("task", {}))
        data["attention"] = AttentionState(**data.get("attention", {}))
        data["execution"] = ExecutionState(**data.get("execution", {}))
        data["prediction"] = PredictionState(**data.get("prediction", {}))
        data["resources"] = ResourceState(**data.get("resources", {}))
        return cls(**data)
