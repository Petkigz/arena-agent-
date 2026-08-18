"""ActionProposal & Multi-Gate Verification Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.policy import PolicyEvaluator
from app.utils.hardware_governor import HardwareGovernor
from app.utils.hardware_monitor import HardwareMonitor
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

    @classmethod
    def from_candidate(
        cls,
        candidate: Any,
        goal_text: str = "",
        complexity: str = "fast",
        predicted_outcome: Optional[Dict[str, Any]] = None
    ) -> ActionProposal:
        """
        Constructs an ActionProposal directly from a winning candidate branch or candidate dict,
        preserving 100% of the candidate's custom payload fields, predicted outcome, and provenance.
        """
        if hasattr(candidate, "candidate_payload") and hasattr(candidate, "hypothetical_action"):
            act_type = candidate.hypothetical_action
            c_payload = dict(getattr(candidate, "candidate_payload", {}) or {})
            pred_outcome = predicted_outcome or getattr(candidate, "predicted_state_change", {})
            branch_name = getattr(candidate, "branch_name", "candidate_branch")
        elif isinstance(candidate, dict):
            act_type = candidate.get("action_type", "generic_action")
            c_payload = dict(candidate.get("payload", {}) or {})
            pred_outcome = predicted_outcome or candidate.get("predicted_outcome", {})
            branch_name = candidate.get("name", "candidate_branch")
        else:
            act_type = str(candidate)
            c_payload = {}
            pred_outcome = predicted_outcome or {}
            branch_name = "candidate_branch"

        if goal_text:
            c_payload.setdefault("query", goal_text)
        if complexity:
            c_payload.setdefault("complexity", complexity)
        c_payload.setdefault("action_type", act_type)
        c_payload.setdefault("provenance", f"candidate_synthesizer:{branch_name}")

        return cls(
            action_type=act_type,
            payload=c_payload,
            predicted_outcome=pred_outcome
        )

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
        "run_command": "execute_command",
        "master_task": "user_task",
        "user_task": "user_task"
    }

    @classmethod
    def evaluate_proposal(cls, proposal: ActionProposal) -> GateResult:
        # 1. Policy Gate (Evaluates underlying action list if present)
        actions_to_check = [proposal.action_type]
        if isinstance(proposal.payload.get("actions"), list):
            actions_to_check.extend(proposal.payload.get("actions"))
        if proposal.payload.get("underlying_action"):
            actions_to_check.append(proposal.payload.get("underlying_action"))

        for act in actions_to_check:
            action_name = cls.POLICY_ACTION_MAP.get(str(act).lower(), str(act))
            allowed, reason, level = PolicyEvaluator.evaluate_action(action_name, proposal.payload)
            proposal.safety_level = max(proposal.safety_level, level)

            if not allowed:
                audit_logger.warning(f"ActionGate BLOCKED proposal '{act}' at Policy Gate: {reason}")
                return GateResult(
                    allowed=False,
                    gate_name="policy_gate",
                    reason=f"Action '{act}' blocked: {reason}",
                    requires_approval=(level == 3)
                )

        # 2. Resource Gate (Non-destructive check)
        hw_stats = HardwareMonitor.get_hardware_stats()
        ram_percent = float(hw_stats.get("ram_used_percent", 0.0))

        # Only purge VRAM/system memory if RAM usage crosses critical 95% pressure
        if ram_percent > 95.0:
            ram_stats = HardwareGovernor.purge_vram_and_system_memory()
            ram_percent = float(ram_stats.get("ram_usage_percent", ram_percent))

        if ram_percent > 98.0:
            audit_logger.warning(f"ActionGate BLOCKED proposal '{proposal.action_type}' at Resource Gate: High RAM pressure ({ram_percent}%)")
            return GateResult(
                allowed=False,
                gate_name="resource_gate",
                reason=f"System RAM pressure above critical threshold ({ram_percent}%). Task paused."
            )

        # 3. Prediction Gate (Reuses canonical pre-execution prediction if already attached)
        if not proposal.predicted_outcome:
            pe = PredictionEngine()
            pred = pe.predict_action(proposal.action_type, proposal.payload)
            proposal.predicted_outcome = pred.expected_changes

        audit_logger.info(f"ActionGate PASSED proposal '{proposal.action_type}' (Safety Level {proposal.safety_level})")

        return GateResult(
            allowed=True,
            gate_name="passed_all_gates",
            reason=f"Action proposal passed Policy (Level {proposal.safety_level}), Resource, and Prediction gates."
        )
