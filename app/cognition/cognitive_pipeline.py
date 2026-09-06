"""Cognitive Pipeline Enforcer delegating strictly to CognitiveRuntime Composition Root."""

from __future__ import annotations
import uuid
from typing import Dict, Any, List, Optional
from app.cognition.runtime import CognitiveRuntime
from app.cognition.epistemic_presentation import presentation_for_cycle
from app.utils.logger import app_logger

class CognitivePipeline:
    """Enforces closed-loop cognition across all incoming user prompts and tool calls via CognitiveRuntime."""

    @classmethod
    def process_chat(cls, user_text: str, complexity: str = "fast", session_id: Optional[str] = None) -> Dict[str, Any]:
        return cls.process_request(user_text, session_id=session_id, complexity=complexity)

    @classmethod
    def process_request(cls, user_text: str, session_id: Optional[str] = None, complexity: str = "fast") -> Dict[str, Any]:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        app_logger.info(f"CognitivePipeline routing request for session '{session_id}' to CognitiveRuntime...")

        runtime = CognitiveRuntime.get_instance()
        try:
            res = runtime.process_cognitive_cycle(user_text, complexity=complexity, session_id=session_id)
        except Exception as exc:
            # The bridge must never manufacture success — a runtime crash is
            # an honest failure with a reason, not a 500 or a fake 'True'.
            app_logger.error(f"CognitiveRuntime raised during process_cognitive_cycle: {exc}")
            failure_presentation = presentation_for_cycle(
                goal_verified=False,
                unknown=True,
                evidence_items=[f"the cognitive runtime raised an exception: {type(exc).__name__}"],
            )
            res = {
                "request_success": False,
                "success": False,
                "execution_success": False,
                "goal_verified": False,
                "goal_lifecycle_state": "failed",
                "assistant_reply": failure_presentation.append_to(
                    "The cognitive engine failed to process this request."
                ),
                "reason": f"runtime exception: {exc}",
                "executed_actions": [],
                "epistemic_presentation": failure_presentation.to_dict(),
            }
        if not isinstance(res, dict):
            app_logger.error(f"CognitiveRuntime returned a non-dict result ({type(res).__name__}).")
            failure_presentation = presentation_for_cycle(
                goal_verified=False,
                unknown=True,
                evidence_items=["the cognitive runtime returned no structured result"],
            )
            res = {
                "request_success": False,
                "success": False,
                "goal_lifecycle_state": "failed",
                "reason": f"runtime returned {type(res).__name__}, expected dict",
                "assistant_reply": failure_presentation.append_to(
                    "The cognitive engine returned an invalid result."
                ),
                "executed_actions": [],
                "epistemic_presentation": failure_presentation.to_dict(),
            }

        success = bool(res.get("success"))
        reason = res.get("reason")
        if not success and not reason:
            # Never a bare failure: derive the 'why' from real runtime fields.
            reason = f"goal not verified (lifecycle state: {res.get('goal_lifecycle_state') or 'unknown'})"
        if not success:
            app_logger.info(
                "CognitivePipeline returning honest failure for session '%s': %s",
                session_id, reason,
            )

        return {
            # ── Honest outcome propagation — the runtime's verdict, never
            #    manufactured. (Live P0: the old bridge returned success=True
            #    even when the cycle ended blocked/unverified, which made
            #    normal testing read as gaslighting.)
            "success": success,
            "request_success": bool(res.get("request_success", success)),
            "execution_success": res.get("execution_success"),
            "goal_verified": res.get("goal_verified"),
            "verification_unknown": res.get("verification_unknown"),
            "goal_lifecycle_state": res.get("goal_lifecycle_state"),
            "action_type": res.get("action_type"),
            "reasoning_action": res.get("reasoning_action"),
            "llm_available": res.get("llm_available"),
            "reason": reason,
            # ── Identity / telemetry ──
            "session_id": res.get("session_id", session_id),
            "trace_id": res.get("trace_id", f"trace_{uuid.uuid4().hex[:8]}"),
            "user_text": user_text,
            "assistant_reply": res.get("assistant_reply", "Done."),
            "executed_actions": res.get("executed_actions", []),
            "latency_ms": res.get("latency_ms", 0.0),
            "model_used": res.get("model_used", "fast"),
            "epistemic_presentation": res.get("epistemic_presentation", {}),
            # Owner review P1 #9: when a loaded FALLBACK model answered
            # (requested model not loaded), the runtime names both models
            # — pass it through so the disclosure survives the bridge.
            # Absent when the requested model answered.
            **({"model_fallback": res["model_fallback"]}
               if isinstance(res.get("model_fallback"), dict) else {}),
            # ── Approval flow (F6): when the gate holds a Level-3 action
            # for 1-click owner approval, the request itself must be
            # visible to bridge consumers (diagnostics, REST callers) —
            # a bare 'blocked' hides that the agent asked to run code.
            "requires_approval": res.get("requires_approval", False),
            "approval_request": res.get("approval_request"),
            "recommendation": res.get("recommendation"),
        }
