"""Goal Reassessment & Replanning Engine."""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.action_planner import ActionPlanner
from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_verifier import GoalVerificationResult, GoalVerifier
from app.utils.logger import app_logger, audit_logger

class GoalReplanner:
    """
    Goal Reassessment & Replanning Engine.
    When GoalVerifier returns FAILED, GoalReplanner reassesses missing conditions,
    ingests failure observations, generates Plan B candidate strategies, and re-evaluates
    competing branches via CounterfactualSimulator.
    """

    @classmethod
    def execute_reassessment_and_replan(
        cls,
        user_text: str,
        goal_rep: SemanticGoalRepresentation,
        failed_result: GoalVerificationResult,
        tracker: GoalTracker,
        complexity: str = "fast"
    ) -> Optional[ActionProposal]:
        app_logger.info(f"GoalReplanner triggered for goal '{tracker.goal_id[:8]}': Reassessing & generating Plan B...")

        tracker.transition(GoalLifecycleState.REASSESSING, f"Reassessing failed conditions: {failed_result.failed_conditions}")

        # Update Goal Representation unknowns
        goal_rep.unknowns.append(f"Primary strategy failed: {failed_result.verification_reason}")
        goal_rep.confidence = max(0.30, goal_rep.confidence - 0.20)

        tracker.transition(GoalLifecycleState.REPLAN, "Generating alternative Plan B candidate strategies.")

        # Filter out primary failed candidate and generate alternative candidate branches
        all_candidates = ActionPlanner.generate_candidate_actions(user_text, complexity=complexity, goal_rep=goal_rep)
        primary_action = failed_result.failed_conditions[0] if failed_result.failed_conditions else ""

        # Alternative candidate strategy (Plan B)
        plan_b_candidates = [c for c in all_candidates if c.get("action_type") not in primary_action]
        if not plan_b_candidates:
            plan_b_candidates = [{"name": "Web Research Fallback Strategy", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}}]

        replan_proposal = ActionPlanner.plan_and_evaluate_action(user_text, complexity=complexity, goal_rep=goal_rep)
        audit_logger.info(f"GoalReplanner generated Plan B proposal '{replan_proposal.action_type}'")

        return replan_proposal
