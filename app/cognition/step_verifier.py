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
- the epistemic ladder below.

Deterministic, no LLM, and testable with a plain dict cycle result.

The epistemic ladder (P0 #15) — three SEPARATE states, never collapsed:

    ACTION_ATTEMPTED → ENVIRONMENT_OBSERVED → POSTCONDITION_VERIFIED

"I attempted the action" is NOT "I observed the resulting environmental
state." An attempt says nothing about the world; only a real observation
does; and only a check of the declared outcome against that observation
completes the ladder. Observation is therefore NEVER inferred from the
attempt (the old `observed = bool(executed) or reasoning in (investigate,
act)` leak): the cycle result must carry an actual observation signal —
`environment_observed` (probes ran and returned / the verifier probed world
state) or `os_grounding` (post-action OS probe) or
`verification_observed_state`. Missing signals honestly mean "not
observed", even when actions clearly fired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Confidence is evidence-derived, never a hard-coded 1.0 on success.
VERIFIED_CONFIDENCE = 0.9        # postcondition verified against a real observation
CONVERSATIONAL_CONFIDENCE = 0.7  # verified but only a reply (no declared evidence)
UNVERIFIED_CONFIDENCE = 0.5      # no confirming evidence
ATTEMPT_ONLY_CONFIDENCE = 0.3    # action fired, world never sensed — riskiest unknown
FAILED_CONFIDENCE = 0.0          # definitive failure

# Cycle-result keys that constitute REAL observation evidence. Attempt-shaped
# keys (executed_actions, reasoning_action) deliberately absent: an attempt is
# not an observation.
_OBSERVATION_SIGNAL_KEYS = ("environment_observed", "os_grounding", "verification_observed_state")


@dataclass
class StepVerificationResult:
    status: str  # "verified" | "unverified" | "failed"
    confidence: float
    met_criteria: List[str] = field(default_factory=list)
    unmet_criteria: List[str] = field(default_factory=list)
    triggered_failure_conditions: List[str] = field(default_factory=list)
    explanation: str = ""
    # Epistemic ladder states — always reported, never collapsed.
    action_attempted: bool = False
    environment_observed: bool = False
    postcondition_verified: bool = False


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

        # Attempt/observation states, computed once for every verdict below.
        action_attempted = bool(cycle_result.get("executed_actions") or []) or             (cycle_result.get("reasoning_action") or "").lower() in ("act", "investigate")
        environment_observed = any(
            cycle_result.get(k) for k in _OBSERVATION_SIGNAL_KEYS
        )

        # 1. Definitive failure: the cycle reached a failed/blocked/deferred state.
        if verified is False and lifecycle in ("failed", "blocked", "deferred"):
            return StepVerificationResult(
                status="failed",
                confidence=FAILED_CONFIDENCE,
                triggered_failure_conditions=list(getattr(step, "failure_conditions", []) or [lifecycle]),
                explanation=f"cycle ended in '{lifecycle}': {cycle_result.get('assistant_reply', '')[:120]}",
                action_attempted=action_attempted,
                environment_observed=environment_observed,
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

        # 3. The epistemic ladder states were computed above (once, for every
        #    verdict): ACTION_ATTEMPTED, ENVIRONMENT_OBSERVED — the latter only
        #    ever from real observation signals carried by the cycle result,
        #    never inferred from the attempt — and now the third rung:
        #    POSTCONDITION_VERIFIED, the declared outcome confirmed against
        #    that observation.
        postcondition_verified = verified is True and environment_observed

        if verified is True:
            if declares_evidence and not environment_observed:
                if action_attempted:
                    # Attempt without observation: the world may have changed but
                    # was never sensed afterwards. Lower confidence than "no
                    # evidence at all" — we acted blind.
                    return StepVerificationResult(
                        status="unverified",
                        confidence=ATTEMPT_ONLY_CONFIDENCE,
                        unmet_criteria=list(getattr(step, "success_criteria", None) or ["environmental evidence"]),
                        explanation=(
                            "action was attempted but the resulting environmental state "
                            "was never observed (attempt is not observation)"
                        ),
                        action_attempted=True,
                        environment_observed=False,
                        postcondition_verified=False,
                    )
                # The original leak: goal_verified=True because a reply was delivered,
                # but the step declared an evidence/criteria contract that no
                # observation fulfilled. Honest verdict: UNVERIFIED, not COMPLETED.
                return StepVerificationResult(
                    status="unverified",
                    confidence=UNVERIFIED_CONFIDENCE,
                    unmet_criteria=list(getattr(step, "success_criteria", None) or ["environmental evidence"]),
                    explanation=(
                        "step declares evidence/success criteria but the cycle produced "
                        "only a conversational reply (no environmental observation)"
                    ),
                    action_attempted=False,
                    environment_observed=False,
                    postcondition_verified=False,
                )
            confidence = VERIFIED_CONFIDENCE if postcondition_verified else CONVERSATIONAL_CONFIDENCE
            return StepVerificationResult(
                status="verified",
                confidence=confidence,
                met_criteria=list(getattr(step, "success_criteria", None) or []),
                explanation="step outcome verified"
                + (" against an observed environment" if postcondition_verified else " (conversational)"),
                action_attempted=action_attempted,
                environment_observed=environment_observed,
                postcondition_verified=postcondition_verified,
            )

        # 4. verified False/None but not provably failed → unknown.
        return StepVerificationResult(
            status="unverified",
            confidence=UNVERIFIED_CONFIDENCE,
            unmet_criteria=list(getattr(step, "success_criteria", None) or ["goal_verified"]),
            explanation="step outcome could not be verified (no confirming evidence)",
            action_attempted=action_attempted,
            environment_observed=environment_observed,
        )
