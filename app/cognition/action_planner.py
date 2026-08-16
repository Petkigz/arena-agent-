"""Cognitive Action Planner & Candidate Branch Evaluator."""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from app.cognition.action_proposal import ActionProposal
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.utils.logger import app_logger

class ActionPlanner:
    """
    Generates competing candidate action branches for a given goal, evaluates risk/utility using
    CounterfactualSimulator in memory, and outputs the optimal ActionProposal.
    """

    @classmethod
    def generate_candidate_actions(cls, goal_text: str, complexity: str = "fast") -> List[Dict[str, Any]]:
        goal_rep = SemanticGoalInterpreter.interpret_goal(goal_text, complexity=complexity)
        return goal_rep.recommended_candidates

    @classmethod
    def plan_and_evaluate_action(cls, goal_text: str, complexity: str = "fast") -> ActionProposal:
        """
        Generates candidate strategies via SemanticGoalInterpreter, runs parallel counterfactual simulation in memory,
        and constructs the winning ActionProposal.
        """
        candidates = cls.generate_candidate_actions(goal_text, complexity=complexity)
        sim_res = CounterfactualSimulator.simulate_competing_branches(goal_text, candidates)
        winner = sim_res.winning_branch

        app_logger.info(f"ActionPlanner selected winning branch '{winner.branch_name}' for action_type '{winner.hypothetical_action}'")

        return ActionProposal(
            action_type=winner.hypothetical_action,
            payload={"query": goal_text, "complexity": complexity, "action_type": winner.hypothetical_action},
            predicted_outcome=winner.predicted_state_change
        )
