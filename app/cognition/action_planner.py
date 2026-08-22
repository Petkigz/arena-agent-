"""Cognitive Action Planner & Candidate Branch Evaluator."""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from app.cognition.action_proposal import ActionProposal
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.goal_interpreter import SemanticGoalInterpreter, SemanticGoalRepresentation
from app.utils.logger import app_logger

class ActionPlanner:
    """
    Generates competing candidate action branches for a given goal, evaluates risk/utility using
    CounterfactualSimulator in memory, and outputs the optimal ActionProposal.
    """

    @classmethod
    def generate_candidate_actions(
        cls,
        goal_text: str,
        complexity: str = "fast",
        goal_rep: Optional[SemanticGoalRepresentation] = None,
        memory_store: Optional[Any] = None,
        world_model: Optional[Any] = None,
        tool_registry: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        if not goal_rep:
            goal_rep = SemanticGoalInterpreter.interpret_goal(
                goal_text, complexity=complexity, memory_store=memory_store, world_model=world_model, tool_registry=tool_registry
            )
        return goal_rep.recommended_candidates

    @classmethod
    def plan_and_evaluate_action(
        cls,
        goal_text: str,
        complexity: str = "fast",
        goal_rep: Optional[SemanticGoalRepresentation] = None,
        candidates: Optional[List[Dict[str, Any]]] = None,
        memory_store: Optional[Any] = None,
        world_model: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        outcome_store: Optional[Any] = None,
        lesson_store: Optional[Any] = None,
        hardware_self_model: Optional[Dict[str, Any]] = None,
        resource_manager: Optional[Any] = None,
    ) -> ActionProposal:
        """
        Generates candidate strategies via SemanticGoalInterpreter (or uses provided candidates),
        runs parallel counterfactual simulation in memory, and constructs the winning ActionProposal,
        preserving 100% of the winning candidate's payload fields.

        Phase 1B: When outcome_store is provided, historical success rates adjust utility scores.
        Phase 1C: When lesson_store is provided, structured lessons influence strategy selection.
        P2 AGI: When hardware_self_model/resource_manager provided, resource-aware adjustment
        penalizes high-cost actions under pressure (RAM/CPU/disk).
        """
        candidate_list = candidates if candidates is not None else cls.generate_candidate_actions(
            goal_text, complexity=complexity, goal_rep=goal_rep, memory_store=memory_store, world_model=world_model, tool_registry=tool_registry
        )
        # Phase 1B/1C/P2: Pass stores for history-influenced + resource-aware selection
        goal_type = goal_rep.primary_intent_type if goal_rep else None
        # Auto-fetch hardware self-model and resource manager from runtime if not provided
        if hardware_self_model is None or resource_manager is None:
            try:
                from app.cognition.runtime import CognitiveRuntime
                rt = CognitiveRuntime.get_instance()
                if hardware_self_model is None:
                    hardware_self_model = getattr(rt, "hardware_self_model", None)
                if resource_manager is None:
                    # ResourceManager lives in advanced_cognition
                    rm = getattr(getattr(rt, "advanced_cognition", None), "resource_manager", None)
                    if rm is None:
                        # Fallback: try direct
                        rm = getattr(rt, "resource_manager", None)
                    resource_manager = rm
            except Exception:
                pass

        sim_res = CounterfactualSimulator.simulate_competing_branches(
            goal_text, candidate_list, goal_type=goal_type,
            outcome_store=outcome_store, lesson_store=lesson_store,
            hardware_self_model=hardware_self_model,
            resource_manager=resource_manager,
        )
        winner = sim_res.winning_branch

        app_logger.info(f"ActionPlanner selected winning branch '{winner.branch_name}' for action_type '{winner.hypothetical_action}' (utility {winner.utility_score:.4f})")

        # Preserve the complete ranked consideration set, including alternatives
        # that would require owner approval. Describing an alternative and its
        # consequences does not authorize it; ActionGate evaluates only the
        # selected recommendation in the next stage.
        alternatives = [
            {
                "rank": rank,
                "branch_id": branch.branch_id,
                "name": branch.branch_name,
                "action_type": branch.hypothetical_action,
                "utility_score": branch.utility_score,
                "reasoning_summary": branch.reasoning_summary,
                "authorization_requirement": branch.authorization_requirement,
                "consequences": dict(branch.consequences),
                "recommended": branch.branch_id == winner.branch_id,
            }
            for rank, branch in enumerate(sim_res.competing_branches, start=1)
        ]
        return ActionProposal.from_candidate(
            winner,
            goal_text=goal_text,
            complexity=complexity,
            alternatives_considered=alternatives,
        )
