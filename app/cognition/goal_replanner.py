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

        # Filter out primary failed action strategy explicitly using structured failed_action_type
        failed_action_type = failed_result.failed_action_type or goal_rep.primary_intent_type
        app_logger.info(f"GoalReplanner filtering out failed action_type '{failed_action_type}' for goal '{tracker.goal_id[:8]}'")

        all_candidates = ActionPlanner.generate_candidate_actions(user_text, complexity=complexity, goal_rep=goal_rep)
        plan_b_candidates = [c for c in all_candidates if c.get("action_type") != failed_action_type]

        if not plan_b_candidates:
            fallbacks = [
                {"name": "Web Research Fallback Strategy", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}},
                {"name": "Diagnostic Investigation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}},
                {"name": "Local Filesystem Search", "action_type": "search_files", "payload": {"query": user_text, "action_type": "search_files"}}
            ]
            plan_b_candidates = [f for f in fallbacks if f.get("action_type") != failed_action_type]

        replan_proposal = ActionPlanner.plan_and_evaluate_action(
            user_text, complexity=complexity, goal_rep=goal_rep, candidates=plan_b_candidates
        )
        audit_logger.info(f"GoalReplanner evaluated {len(plan_b_candidates)} Plan B branches, generated proposal '{replan_proposal.action_type}'")

        return replan_proposal
