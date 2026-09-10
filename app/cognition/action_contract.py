"""Phase 4 (owner plan 2026-09-10): action, authority, and verification contracts.

Objective: capability, permission, action, and outcome are SEPARATE FACTS.
For every proposed action the contract answers:

  1. capability     — can I technically do it?
  2. target         — do I know exactly what this is? (Phase 2 identity)
  3. authority      — am I allowed to do it right now?
  4. expectation    — what do I expect will happen?
  5. verification   — how will I observe success or failure?
  6. reversibility  — can it be reversed?
  7. outcome        — what happened in reality? (execution receipt)

The launch process-verification override in runtime (owner live test
2026-09-08) was the first instance of the right idea — machine-observed
evidence outranks inference. ``apply_receipt_to_verification`` is that
pattern made general: ANY action with a declared observation probe gets
the same treatment, and NO success claim is made without evidence
(``can_claim_observed``).

Contract (owner rules, standing):
  * fail-open: a broken contract never blocks an action the policy allows;
  * kill switch: ``ARENA_ACTION_CONTRACT=0`` restores pre-Phase-4 behavior;
  * authority questions are specific and actionable (name the action, the
    target, and the one word that unblocks);
  * a clear, allowed request goes straight to execution — the owner never
    has to repeat "do it".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Action families the identity layer resolves (Phase 2).
_APP_ACTIONS = frozenset({"open_application", "launch_app"})
_FILE_ACTIONS = frozenset({"create_file", "write_file", "move_file", "rename_file"})

# Expected effect + observation probe per action family. Actions without a
# declared probe are honestly "unverifiable by observation" — they never get
# an evidence-based success claim.
ACTION_EFFECTS: Dict[str, Dict[str, Any]] = {
    "open_application": {
        "effect": "the application's process is running",
        "predicate": "process_state",
        "verification_method": "process_probe",
        "reversible": True,
        "undo": "close the window or terminate the process",
    },
    "launch_app": {
        "effect": "the application's process is running",
        "predicate": "process_state",
        "verification_method": "process_probe",
        "reversible": True,
        "undo": "close the window or terminate the process",
    },
    "create_file": {
        "effect": "a file exists at the target path",
        "predicate": "file_exists",
        "verification_method": "file_exists",
        "reversible": True,
        "undo": "delete the created file",
    },
    "write_file": {
        "effect": "the file exists with the written content",
        "predicate": "file_exists",
        "verification_method": "file_exists",
        "reversible": False,
        "undo": "previous content is not recoverable without a backup",
    },
    "move_file": {
        "effect": "the file exists at the destination path",
        "predicate": "file_exists",
        "verification_method": "file_exists",
        "reversible": True,
        "undo": "move it back to the source path",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    try:
        from app.config import settings
        raw = str(getattr(settings, "ARENA_ACTION_CONTRACT", "1")).strip().lower()
        return raw not in ("0", "false", "off", "no", "")
    except Exception:
        return True  # fail-open


@dataclass
class ActionContract:
    """The seven separated facts for one proposed action."""

    action_type: str
    capability: Dict[str, Any] = field(default_factory=dict)
    target: Dict[str, Any] = field(default_factory=dict)
    authority: Dict[str, Any] = field(default_factory=dict)
    expectation: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    reversibility: Dict[str, Any] = field(default_factory=dict)
    decision: str = "act"  # act | ask_target | ask_approval | blocked
    question: str = ""     # the ONE focused question when decision != act
    blocker: str = ""      # the concrete blocker when blocked

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "capability": self.capability,
            "target": self.target,
            "authority": self.authority,
            "expectation": self.expectation,
            "verification": self.verification,
            "reversibility": self.reversibility,
            "decision": self.decision,
            "question": self.question,
            "blocker": self.blocker,
        }


@dataclass
class ExecutionReceipt:
    """What happened in reality — separate from what was attempted."""

    proposal_id: str = ""
    action_type: str = ""
    target_name: str = ""
    target_entity_id: Optional[str] = None
    executed: bool = False
    success: bool = False
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    verified: Optional[bool] = None  # True/False observed; None = no probe/unobserved
    verification_method: str = "none"
    blocker: str = ""
    observed_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "action_type": self.action_type,
            "target_name": self.target_name,
            "target_entity_id": self.target_entity_id,
            "executed": self.executed,
            "success": self.success,
            "evidence": self.evidence,
            "verified": self.verified,
            "verification_method": self.verification_method,
            "blocker": self.blocker,
            "observed_at": self.observed_at,
        }


# ── fact 1: capability ────────────────────────────────────────────────────


def capability_available(action_type: str) -> Dict[str, Any]:
    """Can I technically do it? The manifest is the capability authority;
    legacy/virtual names known to the ActionGate count as available."""
    at = str(action_type or "").strip().lower()
    if not at:
        return {"available": False, "detail": "no action type given"}
    try:
        from app.cognition.tool_registry import capability_safety_or_none
        level = capability_safety_or_none(at)
        if level is not None:
            return {"available": True, "detail": f"manifest capability (safety level {level})"}
    except Exception:
        return {"available": True, "detail": "capability check unavailable (fail-open)"}
    try:
        from app.cognition.action_proposal import ActionGate
        known = at in ActionGate.POLICY_ACTION_MAP or at in set(ActionGate.POLICY_ACTION_MAP.values())
        if known:
            return {"available": True, "detail": "known virtual action (gate-mapped)"}
    except Exception:
        pass
    return {"available": False,
            "detail": f"no manifest entry for capability '{at}' — it cannot be executed"}


# ── contract assembly ─────────────────────────────────────────────────────


def build_contract(proposal: Any, user_text: str = "",
                   world: Optional[Any] = None) -> ActionContract:
    """Assemble the seven facts and the single decision for a proposal.

    decision == 'act' means: capability, target, and authority are all
    clear — execute without asking. The owner never has to repeat "do it"
    after a clear request; every non-act decision carries ONE specific,
    actionable question or a concrete blocker.
    """
    action_type = str(getattr(proposal, "action_type", "") or "").strip().lower()
    payload = getattr(proposal, "payload", {}) or {}
    c = ActionContract(action_type=action_type)

    c.capability = capability_available(action_type)

    # Fact 2: target (Phase 2 identity for app actions; path for file actions)
    target_name = ""
    if action_type in _APP_ACTIONS:
        target_name = str(payload.get("app_name") or payload.get("app")
                          or payload.get("app_query") or payload.get("query") or "").strip()
        if not target_name and user_text:
            try:
                from app.agents.master_agent import extract_app_query
                target_name = extract_app_query(user_text)
            except Exception:
                target_name = ""
        identity: Dict[str, Any] = {"status": "unknown", "name": target_name}
        if world is not None and target_name:
            try:
                from app.mind.app_identity import resolve_app_target
                verdict = resolve_app_target(target_name, world)
                if verdict.get("status") == "resolved":
                    identity = {"status": "resolved", "name": verdict.get("name"),
                                "entity_id": verdict.get("entity_id"),
                                "confidence": verdict.get("confidence"),
                                "evidence": verdict.get("evidence")}
                    target_name = identity["name"] or target_name
                elif verdict.get("status") == "ambiguous":
                    identity = {"status": "ambiguous", "name": target_name,
                                "question": verdict.get("question", ""),
                                "candidates": verdict.get("candidates", [])}
            except Exception:
                pass  # fail-open — identity unknown, execution may still proceed
        c.target = identity
    elif action_type in _FILE_ACTIONS:
        target_name = str(payload.get("destination") or payload.get("file_path")
                          or payload.get("path") or payload.get("query") or "").strip()
        c.target = {"status": "path" if target_name else "unknown", "name": target_name}
    else:
        c.target = {"status": "n_a", "name": target_name}

    # Fact 3: authority (PolicyEvaluator stays the authority of record)
    c.authority = {"allowed": True, "level": 0, "reason": "no policy restriction",
                   "requires_approval": False}
    try:
        from app.cognition.action_proposal import ActionGate
        from app.policy import PolicyEvaluator
        policy_name = ActionGate.POLICY_ACTION_MAP.get(action_type, action_type)
        allowed, reason, level = PolicyEvaluator.evaluate_action(
            policy_name, {"app_name": target_name} if action_type in _APP_ACTIONS else {})
        c.authority = {"allowed": bool(allowed), "level": int(level), "reason": str(reason),
                       "requires_approval": (not allowed) and int(level) >= 3}
    except Exception:
        pass  # fail-open: a policy glitch must not fabricate a denial

    # Facts 4-6: expectation, verification, reversibility
    spec = ACTION_EFFECTS.get(action_type, {})
    c.expectation = {"effect": spec.get("effect", "no declared observable effect"),
                     "predicate": spec.get("predicate", "")}
    c.verification = {"method": spec.get("verification_method", "none"),
                      "description": (f"probe after execution: {spec['effect']}"
                                      if spec else "no observation probe declared — success stays unverified")}
    c.reversibility = {
        "reversible": bool(getattr(proposal, "reversibility", spec.get("reversible", True))),
        "undo": spec.get("undo", "no recorded undo path"),
    }

    # The single decision
    if not c.capability.get("available"):
        c.decision = "blocked"
        c.blocker = c.capability.get("detail", "capability unavailable")
    elif c.target.get("status") == "ambiguous":
        c.decision = "ask_target"
        c.question = c.target.get("question") or (
            f"Target ambiguous for '{target_name}' — which one did you mean?")
    elif not c.authority.get("allowed"):
        if c.authority.get("requires_approval"):
            c.decision = "ask_approval"
            what = f"{action_type.replace('_', ' ')} '{target_name}'".strip()
            c.question = (
                f"'{what}' needs your approval (authority level "
                f"{c.authority.get('level')}: {c.authority.get('reason')}). "
                "Say 'approve' to run it now, or 'no' to skip."
            )
        else:
            c.decision = "blocked"
            c.blocker = f"policy denied: {c.authority.get('reason')}"
    return c


# ── fact 7: outcome — receipts, probes, and the honesty gate ─────────────


def evidence_from_result(action_type: str, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Machine-observed evidence carried by the execution result itself."""
    ev: List[Dict[str, Any]] = []
    result = result or {}
    if action_type in _APP_ACTIONS:
        launch = result.get("launch_res") or {}
        if "process_verified" in launch or launch.get("already_running"):
            ev.append({
                "kind": "process",
                "running": bool(launch.get("process_verified")),
                "pid": launch.get("pid"),
                "process_name": launch.get("process_name", ""),
                "source": "psutil_scan",
                "observed_at": launch.get("verified_at") or _now(),
            })
    return ev


def verify_execution(action_type: str, result: Dict[str, Any],
                     target_name: str = "") -> Dict[str, Any]:
    """Run the declared observation probe for an action's outcome.

    Returns {method, verified (True/False/None), evidence}. verified is
    None when no probe is declared or the probe itself failed — an
    unobserved outcome is NEVER silently upgraded to success.
    """
    spec = ACTION_EFFECTS.get(action_type, {})
    method = spec.get("verification_method", "none")
    if method == "none":
        return {"method": "none", "verified": None, "evidence": [],
                "note": "no observation probe declared for this action"}
    try:
        if method == "process_probe":
            # The result may already carry the machine's observation.
            carried = evidence_from_result(action_type, result)
            if carried:
                return {"method": method,
                        "verified": bool(carried[0].get("running")),
                        "evidence": carried}
            from app.tools.app_inventory import SystemAppInventory
            probe = SystemAppInventory.verify_app_running(target_name or "",
                                                          wait_seconds=2.0)
            return {"method": method,
                    "verified": bool(probe.get("process_verified")),
                    "evidence": [{
                        "kind": "process",
                        "running": bool(probe.get("process_verified")),
                        "pid": probe.get("pid"),
                        "process_name": probe.get("process_name", ""),
                        "source": "psutil_scan",
                        "observed_at": _now(),
                    }]}
        if method == "file_exists":
            import os
            path = str(((result or {}).get("file_path"))
                       or ((result or {}).get("destination")) or target_name or "")
            exists = bool(path) and os.path.exists(path)
            return {"method": method, "verified": exists,
                    "evidence": [{"kind": "file", "path": path, "exists": exists,
                                  "source": "os.path.exists", "observed_at": _now()}]}
    except Exception as exc:  # fail-open: a broken probe never fakes success
        return {"method": method, "verified": None,
                "evidence": [{"kind": "probe_error",
                              "detail": f"{type(exc).__name__}: {exc}",
                              "observed_at": _now()}]}
    return {"method": method, "verified": None, "evidence": []}


def receipt_from_execution(proposal: Any, result: Dict[str, Any],
                           world: Optional[Any] = None) -> ExecutionReceipt:
    """Build the outcome fact from an execution result (fail-open)."""
    action_type = str(getattr(proposal, "action_type", "") or "").strip().lower()
    result = result or {}
    outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else result
    target_name = ""
    if action_type in _APP_ACTIONS:
        launch = (outputs or {}).get("launch_res") or {}
        target_name = str(launch.get("app_name") or "").strip()
    receipt = ExecutionReceipt(
        proposal_id=str(getattr(proposal, "proposal_id", "") or ""),
        action_type=action_type,
        target_name=target_name,
        executed=bool(result.get("attempted", True)),
        success=bool(result.get("success", False)),
    )
    if not receipt.success:
        launch = (outputs or {}).get("launch_res") or {}
        receipt.blocker = str(launch.get("error") or result.get("error")
                              or "execution did not succeed")
    try:
        v = verify_execution(action_type, outputs or {}, target_name)
        receipt.verification_method = v.get("method", "none")
        receipt.verified = v.get("verified")
        receipt.evidence = list(v.get("evidence") or [])
    except Exception:
        receipt.verified = None
    # Persist the observation so the world model learns from REALITY.
    if world is not None and target_name:
        try:
            for e in receipt.evidence:
                if e.get("kind") == "process":
                    from app.mind.app_identity import record_process_state
                    record_process_state(target_name, bool(e.get("running")),
                                         world, source="execution_receipt")
        except Exception:
            pass  # fail-open: recording never fails a task
    return receipt


def apply_receipt_to_verification(verification: Any, receipt: Optional[ExecutionReceipt]) -> bool:
    """The generalized launch-truth override.

    Machine-observed evidence in an execution receipt outranks inference
    for ANY action with a declared probe — the isolated 2026-09-08 launch
    patch as a general pattern. Never fires without evidence.
    """
    if verification is None or getattr(verification, "verified_success", False):
        return False
    if receipt is None or receipt.verified is not True or not receipt.evidence:
        return False
    ev = receipt.evidence[0]
    if ev.get("kind") == "process":
        cond = (f"process probe: '{receipt.target_name}' is running "
                f"(pid {ev.get('pid')})")
    elif ev.get("kind") == "file":
        cond = f"file probe: '{ev.get('path')}' exists"
    else:
        cond = f"execution receipt evidence ({ev.get('kind')})"
    verification.verified_success = True
    verification.is_unknown = False
    verification.met_conditions = list(getattr(verification, "met_conditions", None) or []) + [cond]
    verification.verification_reason = (
        f"verified by machine observation via execution receipt "
        f"({receipt.verification_method})"
    )
    return True


def can_claim_observed(receipt: Optional[ExecutionReceipt]) -> bool:
    """The honesty gate: 'I see you opened it' requires observed evidence.

    No receipt, no probe, or an unobserved/failed outcome → the claim is
    not allowed; the reply must state what is actually known instead.
    """
    return bool(receipt is not None and receipt.verified is True and receipt.evidence)
