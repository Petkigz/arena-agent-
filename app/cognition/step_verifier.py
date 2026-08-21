"""StepVerifier — independent per-step verification, distinct from GoalVerifier.

The cognitive runtime's `process_cognitive_cycle()` treats the step's description
as a *goal* and returns a `goal_verified` verdict from GoalVerifier. That is the
WRONG granularity for the autonomous executor: for a conversational/analysis step
("Analyze current state"), the ANSWER branch resolves `response_delivered →
SATISFIED`, so `goal_verified=True` means "a reply was produced", NOT "the step's
declared outcome was environmentally verified".

This module is the missing layer the auditor identified:

    Step → CognitiveRuntime → ExecutionResult → StepVerifier → StepVerificationResult
        → (step COMPLETED / UNVERIFIED / FAILED) → GoalVerifier → overall goal.

StepVerifier evaluates a step's OWN declared contract:
- success_criteria / failure_conditions
- requires_evidence / produces_evidence
- whether the cycle produced environmental observation (ACT/INVESTIGATE) vs a
  bare conversational answer (ANSWER).

Deterministic, no LLM, and testable with a plain dict cycle result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Confidence is evidence-derived, never a hard-coded 1.0 on success.
VERIFIED_CONFIDENCE = 0.9        # verified AND backed by environmental observation
CONVERSATIONAL_CONFIDENCE = 0.7  # verified but only a reply (no declared evidence)
UNVERIFIED_CONFIDENCE = 0.5      # no confirming evidence
FAILED_CONFIDENCE = 0.0          # definitive failure

# reasoning_action values that indicate real observation/action occurred (vs a
# bare ANSWER). Anything else is treated as "no environmental evidence".
_OBSERVING_ACTIONS = ("investigate", "act")


@dataclass
class StepVerificationResult:
    status: str  # "verified" | "unverified" | "failed"
    confidence: float
    met_criteria: List[str] = field(default_factory=list)
    unmet_criteria: List[str] = field(default_factory=list)
    triggered_failure_conditions: List[str] = field(default_factory=list)
    explanation: str = ""


class StepVerifier:
    @classmethod
    def verify_step(
        cls,
        step: Any,
        cycle_result: Dict[str, Any],
        available_evidence: Optional[set] = None,
    ) -> StepVerificationResult:
        """Evaluate one step's outcome against its OWN declared contract.

        Args:
            step: an ExecutionStep (duck-typed: has produces_evidence,
                  requires_evidence, success_criteria, failure_conditions).
            cycle_result: the dict returned by process_cognitive_cycle().
            available_evidence: set of evidence names produced by COMPLETED
                prerequisite steps (for requires_evidence enforcement).

        Returns a StepVerificationResult with status + evidence-derived confidence.
        """
        verified = cycle_result.get("goal_verified")
        lifecycle = cycle_result.get("goal_lifecycle_state", "") or ""
        reasoning = (cycle_result.get("reasoning_action") or "").lower()
        executed = cycle_result.get("executed_actions") or []

        declares_evidence = bool(
            getattr(step, "produces_evidence", None)
            or getattr(step, "requires_evidence", None)
            or getattr(step, "success_criteria", None)
        )

        # 1. Definitive failure: the cycle reached a failed/blocked/deferred state.
        if verified is False and lifecycle in ("failed", "blocked", "deferred"):
            return StepVerificationResult(
                status="failed",
                confidence=FAILED_CONFIDENCE,
                triggered_failure_conditions=list(getattr(step, "failure_conditions", []) or [lifecycle]),
                explanation=f"cycle ended in '{lifecycle}': {cycle_result.get('assistant_reply', '')[:120]}",
            )

        # 2. Required-evidence enforcement: a step that declares a prerequisite
        #    evidence name must not run (nor be verified) if that evidence was
        #    never produced by a completed step. Skipped when the caller passes
        #    available_evidence=None (enforcement happens at the plan level).
        if available_evidence is not None:
            missing = [
                e for e in (getattr(step, "requires_evidence", None) or [])
                if e not in available_evidence
            ]
            if missing:
                return StepVerificationResult(
                    status="unverified",
                    confidence=UNVERIFIED_CONFIDENCE,
                    unmet_criteria=missing,
                    explanation=f"required evidence not available: {', '.join(missing)}",
                )

        # 3. Verified, but was it backed by environmental observation?
        observed = bool(executed) or reasoning in _OBSERVING_ACTIONS
        if verified is True:
            if declares_evidence and not observed:
                # The leak: goal_verified=True because a reply was delivered, but the
                # step declared an evidence/criteria contract that no observation
                # fulfilled. Honest verdict: UNVERIFIED, not COMPLETED.
                return StepVerificationResult(
                    status="unverified",
                    confidence=UNVERIFIED_CONFIDENCE,
                    unmet_criteria=list(getattr(step, "success_criteria", None) or ["environmental evidence"]),
                    explanation=(
                        "step declares evidence/success criteria but the cycle produced "
                        "only a conversational reply (no environmental observation)"
                    ),
                )
            confidence = VERIFIED_CONFIDENCE if observed else CONVERSATIONAL_CONFIDENCE
            return StepVerificationResult(
                status="verified",
                confidence=confidence,
                met_criteria=list(getattr(step, "success_criteria", None) or []),
                explanation="step outcome verified"
                + (" via environmental observation" if observed else " (conversational)"),
            )

        # 4. verified False/None but not provably failed → unknown.
        return StepVerificationResult(
            status="unverified",
            confidence=UNVERIFIED_CONFIDENCE,
            unmet_criteria=list(getattr(step, "success_criteria", None) or ["goal_verified"]),
            explanation="step outcome could not be verified (no confirming evidence)",
        )
