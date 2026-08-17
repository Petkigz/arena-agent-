"""Goal Verification Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.utils.logger import app_logger, audit_logger

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class GoalVerificationResult:
    goal_id: str
    verified_success: bool
    final_state: GoalLifecycleState
    verification_reason: str
    met_conditions: List[str] = field(default_factory=list)
    failed_conditions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)

class GoalVerifier:
    """
    Goal Verification Engine.
    Evaluates whether the environment actually reached goal_rep.desired_outcome using
    goal_rep.success_conditions and failure_conditions, distinguishing tool execution success
    from true goal achievement.
    """

    @classmethod
    def verify_goal_achievement(
        cls,
        goal_rep: SemanticGoalRepresentation,
        executed_actions: List[str],
        assistant_reply: str,
        tracker: Optional[GoalTracker] = None
    ) -> GoalVerificationResult:
        goal_id = tracker.goal_id if tracker else "goal_verify_anon"
        if tracker:
            tracker.transition(GoalLifecycleState.VERIFYING, "Evaluating real environmental goal achievement against success_conditions.")

        reply_lower = assistant_reply.lower().strip()
        actions_str = " ".join(executed_actions).lower()

        met_conditions = []
        failed_conditions = []

        # 1. Check Explicit Failure Conditions FIRST
        for fail_cond in goal_rep.failure_conditions:
            if "empty" in fail_cond and not reply_lower:
                failed_conditions.append(fail_cond)
            elif "blocked" in fail_cond and "blocked" in reply_lower:
                failed_conditions.append(fail_cond)
            elif "not found" in reply_lower or "failed" in reply_lower or "error" in reply_lower:
                failed_conditions.append("Execution error or missing resource reported")

        # 2. Check Success Conditions
        for succ_cond in goal_rep.success_conditions:
            if "response_delivered" in succ_cond and len(reply_lower) > 5:
                met_conditions.append(succ_cond)
            elif "running" in succ_cond or "launched" in succ_cond or "opened" in actions_str:
                met_conditions.append(succ_cond)

        # Evaluate Overall Success
        verified_success = len(failed_conditions) == 0 and (len(executed_actions) > 0 or len(reply_lower) > 10)

        final_state = GoalLifecycleState.ACHIEVED if verified_success else GoalLifecycleState.FAILED
        reason = f"Goal '{goal_rep.goal}' achieved: Met {len(met_conditions)} success criteria." if verified_success else f"Goal verification failed: {failed_conditions or 'Target state not verified.'}"

        if tracker:
            tracker.transition(final_state, reason)

        audit_logger.info(f"GoalVerifier [{goal_id[:8]}]: VerifiedSuccess={verified_success}, State={final_state.value}")

        return GoalVerificationResult(
            goal_id=goal_id,
            verified_success=verified_success,
            final_state=final_state,
            verification_reason=reason,
            met_conditions=met_conditions,
            failed_conditions=failed_conditions
        )
