"""ActionProposal & Multi-Gate Verification Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.policy import PolicyEvaluator
from app.utils.hardware_governor import HardwareGovernor
from app.cognition.prediction_engine import PredictionEngine
from app.utils.logger import app_logger, audit_logger

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class ActionProposal:
    action_type: str
    payload: Dict[str, Any]
    safety_level: int = 0
    reversibility: bool = True
    predicted_outcome: Dict[str, Any] = field(default_factory=dict)
    proposal_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)

@dataclass
class GateResult:
    allowed: bool
    gate_name: str
    reason: str
    requires_approval: bool = False

class ActionGate:
    """
    P1-D: Reasoning / Action Gate Boundary.
    Enforces that reasoning models issue structured proposals through multi-gate verification
    (Policy, Resource, and Prediction gates) rather than implicitly executing commands.
    """

    POLICY_ACTION_MAP = {
        "launch_app": "open_application",
        "search_files": "read_file",
        "screen_capture": "capture_screen",
        "web_search": "web_search",
        "run_command": "execute_command"
    }

    @classmethod
    def evaluate_proposal(cls, proposal: ActionProposal) -> GateResult:
        # 1. Policy Gate
        action_name = cls.POLICY_ACTION_MAP.get(proposal.action_type.lower(), proposal.action_type)
        allowed, reason, level = PolicyEvaluator.evaluate_action(action_name, proposal.payload)
        proposal.safety_level = level

        if not allowed:
            audit_logger.warning(f"ActionGate BLOCKED proposal '{proposal.action_type}' at Policy Gate: {reason}")
            return GateResult(
                allowed=False,
                gate_name="policy_gate",
                reason=reason,
                requires_approval=(level == 3)
            )

        # 2. Resource Gate
        ram_stats = HardwareGovernor.purge_vram_and_system_memory()
        if ram_stats.get("ram_usage_percent", 0) > 98.0:
            audit_logger.warning(f"ActionGate BLOCKED proposal '{proposal.action_type}' at Resource Gate: High RAM pressure")
            return GateResult(
                allowed=False,
                gate_name="resource_gate",
                reason="System RAM pressure above critical threshold (98%). Task paused."
            )

        # 3. Prediction Gate
        pe = PredictionEngine()
        pred = pe.predict_action(proposal.action_type, proposal.payload)
        proposal.predicted_outcome = pred.expected_changes

        audit_logger.info(f"ActionGate PASSED proposal '{proposal.action_type}' (Safety Level {level})")

        return GateResult(
            allowed=True,
            gate_name="passed_all_gates",
            reason=f"Action proposal passed Policy (Level {level}), Resource, and Prediction gates."
        )
