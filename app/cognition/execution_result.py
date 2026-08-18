"""First-Class ExecutionResult and ExecutionStatus Abstractions."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class ExecutionStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"

@dataclass
class ExecutionResult:
    """
    First-Class ExecutionResult dataclass abstraction representing tool capability execution outcomes.
    Carries explicit status states (NOT_ATTEMPTED, RUNNING, SUCCEEDED, FAILED, PARTIAL, UNKNOWN),
    proposal_id, action_type, tool_results, errors, outputs, side_effects, and observations.
    """
    proposal_id: str
    action_type: str
    execution_status: ExecutionStatus = ExecutionStatus.NOT_ATTEMPTED
    attempted: bool = True
    executed_actions: List[str] = field(default_factory=list)
    assistant_reply: str = ""
    tool_result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    side_effects: List[Dict[str, Any]] = field(default_factory=list)
    execution_facts: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Any] = field(default_factory=list)
    model_used: str = "fast"
    timestamp: str = field(default_factory=_now)

    @property
    def success(self) -> bool:
        return self.execution_status == ExecutionStatus.SUCCEEDED

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts ExecutionResult into a dictionary for backward compatibility with dictionary callers.
        """
        base_dict = {
            "proposal_id": self.proposal_id,
            "action_type": self.action_type,
            "execution_status": self.execution_status.value,
            "success": self.success,
            "attempted": self.attempted,
            "executed_actions": self.executed_actions,
            "assistant_reply": self.assistant_reply,
            "tool_result": self.tool_result,
            "error": self.error,
            "outputs": self.outputs,
            "side_effects": self.side_effects,
            "execution_facts": self.execution_facts,
            "observations": self.observations,
            "model_used": self.model_used,
            "timestamp": self.timestamp,
            # Top-level dict compatibility
            "raw_output": self.outputs,
        }
        if isinstance(self.outputs, dict):
            for k, v in self.outputs.items():
                if k not in base_dict:
                    base_dict[k] = v
        return base_dict

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access method for backward compatibility."""
        return self.to_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        """Dict-like subscript access method for backward compatibility."""
        return self.to_dict()[key]

    def __contains__(self, key: str) -> bool:
        """Dict-like 'in' operator support for backward compatibility."""
        return key in self.to_dict()
