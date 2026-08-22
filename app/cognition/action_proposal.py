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
from app.cognition.owner_control import authorization_store, owner_control_store
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
    # Decision transparency. These are recommendation-stage records only and
    # carry no execution authority; ActionGate remains the authorization stage.
    recommendation_reason: str = ""
    alternatives_considered: List[Dict[str, Any]] = field(default_factory=list)
    decision_stage: str = "recommendation"
    authorization_id: Optional[str] = None
    plan_id: Optional[str] = None
    proposal_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_candidate(
        cls,
        candidate: Any,
        goal_text: str = "",
        complexity: str = "fast",
        predicted_outcome: Optional[Dict[str, Any]] = None,
        alternatives_considered: Optional[List[Dict[str, Any]]] = None,
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
            predicted_outcome=pred_outcome,
            recommendation_reason=(
                str(getattr(candidate, "reasoning_summary", ""))
                if not isinstance(candidate, dict)
                else str(candidate.get("reasoning_summary", ""))
            ),
            alternatives_considered=list(alternatives_considered or []),
        )

@dataclass
class GateResult:
    allowed: bool
    gate_name: str
    reason: str
    requires_approval: bool = False
    # consideration → recommendation → authorization → execution are distinct.
    decision_stage: str = "authorization"

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
    def _manifest_safety_level(cls, action_type: str):
        """Return the manifest-declared safety level for an action type, or None.

        The tool manifest (app/tools/manifest.py) is the authoritative source of
        truth for safety levels; this is consulted before the legacy policy list.
        """
        try:
            from app.tools.manifest import get_tool_manifest
            entry = get_tool_manifest().get(action_type)
            if entry:
                return int(entry.get("safety_level", 0))
        except Exception:
            pass
        return None

    @classmethod
    def evaluate_proposal(cls, proposal: ActionProposal) -> GateResult:
        # Validate a supplied grant early, but consume it only after every other
        # gate passes. The grant is exact-action, exact-payload, short-lived, and
        # cannot override hard owner denials such as pause/block/observe-only.
        authorization_valid = False
        if proposal.authorization_id:
            auth = authorization_store.validate(
                proposal.authorization_id,
                proposal.action_type,
                proposal.payload,
                plan_id=proposal.plan_id,
            )
            if not auth.valid:
                proposal.decision_stage = "rejected"
                return GateResult(
                    allowed=False,
                    gate_name="authorization_gate",
                    reason=auth.reason,
                    requires_approval=True,
                    decision_stage="rejected",
                )
            authorization_valid = True

        # Owner control is evaluated independently from capability/safety policy.
        # A global pause or non-executing mode must stop the proposal before any
        # resource cleanup, prediction, or capability code can run.
        owner_preflight = owner_control_store.evaluate(proposal.action_type, 0)
        if not owner_preflight.allowed and not (
            owner_preflight.requires_approval and authorization_valid
        ):
            proposal.decision_stage = (
                "awaiting_authorization" if owner_preflight.requires_approval else "rejected"
            )
            return GateResult(
                allowed=False,
                gate_name="owner_control_gate",
                reason=owner_preflight.reason,
                requires_approval=owner_preflight.requires_approval,
                decision_stage=proposal.decision_stage,
            )

        # 1. Policy Gate (Evaluates underlying action list if present)
        actions_to_check = [proposal.action_type]
        if isinstance(proposal.payload.get("actions"), list):
            actions_to_check.extend(proposal.payload.get("actions"))
        if proposal.payload.get("underlying_action"):
            actions_to_check.append(proposal.payload.get("underlying_action"))

        for act in actions_to_check:
            act_key = str(act).lower().strip()

            # ── Authoritative safety level: the unified tool manifest ──
            # The manifest is the single source of truth for every tool's safety
            # level. Consult it first so all 66 tools behave per their declared
            # level (not the PolicyEvaluator's "unknown → Level 3" fallback).
            manifest_level = cls._manifest_safety_level(act_key)

            if manifest_level is not None:
                proposal.safety_level = max(proposal.safety_level, manifest_level)
                owner_decision = owner_control_store.evaluate(act_key, manifest_level)
                if not owner_decision.allowed and not (
                    owner_decision.requires_approval and authorization_valid
                ):
                    reason = owner_decision.reason
                    gate_name = "policy_gate" if manifest_level >= 3 else "owner_control_gate"
                    audit_logger.warning(
                        f"ActionGate BLOCKED proposal '{act}' at {gate_name} "
                        f"(Level {manifest_level}, mode={owner_decision.mode})"
                    )
                    proposal.decision_stage = (
                        "awaiting_authorization" if owner_decision.requires_approval else "rejected"
                    )
                    return GateResult(
                        allowed=False,
                        gate_name=gate_name,
                        reason=reason,
                        requires_approval=owner_decision.requires_approval,
                        decision_stage=proposal.decision_stage,
                    )
                # Manifest tool is within owner-delegated authority.
                continue

            # ── Legacy fallback: PolicyEvaluator for non-manifest action names ──
            action_name = cls.POLICY_ACTION_MAP.get(act_key, act_key)
            allowed, reason, level = PolicyEvaluator.evaluate_action(action_name, proposal.payload)
            proposal.safety_level = max(proposal.safety_level, level)

            if not allowed and not (level == 3 and authorization_valid):
                audit_logger.warning(f"ActionGate BLOCKED proposal '{act}' at Policy Gate: {reason}")
                stage = "awaiting_authorization" if level == 3 else "rejected"
                proposal.decision_stage = stage
                return GateResult(
                    allowed=False,
                    gate_name="policy_gate",
                    reason=f"Action '{act}' blocked: {reason}",
                    requires_approval=(level == 3),
                    decision_stage=stage,
                )

            owner_decision = owner_control_store.evaluate(act_key, level)
            if not owner_decision.allowed and not (
                owner_decision.requires_approval and authorization_valid
            ):
                proposal.decision_stage = (
                    "awaiting_authorization" if owner_decision.requires_approval else "rejected"
                )
                return GateResult(
                    allowed=False,
                    gate_name="owner_control_gate",
                    reason=owner_decision.reason,
                    requires_approval=owner_decision.requires_approval,
                    decision_stage=proposal.decision_stage,
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
            proposal.decision_stage = "rejected"
            return GateResult(
                allowed=False,
                gate_name="resource_gate",
                reason=f"System RAM pressure above critical threshold ({ram_percent}%). Task paused.",
                decision_stage="rejected",
            )

        # 3. Prediction Gate (Reuses canonical pre-execution prediction if already attached)
        if not proposal.predicted_outcome:
            pe = PredictionEngine()
            pred = pe.predict_action(proposal.action_type, proposal.payload)
            proposal.predicted_outcome = pred.expected_changes

        if proposal.authorization_id:
            consumed = authorization_store.consume(
                proposal.authorization_id,
                proposal.action_type,
                proposal.payload,
                plan_id=proposal.plan_id,
            )
            if not consumed.valid:
                proposal.decision_stage = "rejected"
                return GateResult(
                    allowed=False,
                    gate_name="authorization_gate",
                    reason=consumed.reason,
                    requires_approval=True,
                    decision_stage="rejected",
                )

        audit_logger.info(f"ActionGate PASSED proposal '{proposal.action_type}' (Safety Level {proposal.safety_level})")
        proposal.decision_stage = "authorized"

        return GateResult(
            allowed=True,
            gate_name="passed_all_gates",
            reason=f"Action proposal passed Policy (Level {proposal.safety_level}), Resource, and Prediction gates.",
            decision_stage="authorized",
        )
