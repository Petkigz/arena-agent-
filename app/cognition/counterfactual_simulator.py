"""Milestone 4: Counterfactual Parallel Mental Simulator Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.cognition.prediction_engine import PredictionEngine
from app.utils.logger import app_logger

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class SimulationBranch:
    branch_id: str
    branch_name: str
    hypothetical_action: str
    predicted_state_change: Dict[str, Any]
    risk_score: float  # 0.0 = low risk, 1.0 = critical risk
    goal_fit_score: float  # 0.0 = low goal fit, 1.0 = perfect goal fit
    estimated_surprisal: float
    utility_score: float
    reasoning_summary: str

@dataclass
class CounterfactualSimulationResult:
    simulation_id: str
    target_goal: str
    winning_branch: SimulationBranch
    competing_branches: List[SimulationBranch]
    created_at: str = field(default_factory=_now)

class CounterfactualSimulator:
    """
    Simulates competing hypothetical execution branches (S_A, S_B, S_C) in memory,
    evaluating predicted outcomes, risk scores, goal fit, and utility BEFORE touching the live host system.
    """

    @classmethod
    def simulate_competing_branches(
        cls,
        target_goal: str,
        candidate_actions: List[Dict[str, Any]]
    ) -> CounterfactualSimulationResult:
        app_logger.info(f"CounterfactualSimulator running parallel simulation for goal: '{target_goal}' ({len(candidate_actions)} branches)")

        branches: List[SimulationBranch] = []
        pe = PredictionEngine()

        for idx, act in enumerate(candidate_actions, 1):
            act_name = act.get("name", f"Branch_{idx}")
            act_type = act.get("action_type", "generic_action")
            payload = act.get("payload", {})

            # 1. Predict state change
            pred = pe.predict_action(act_type, payload)

            # 2. Compute risk score heuristic
            risk = 0.1
            payload_str = str(payload).lower()
            if "delete" in payload_str or "remove" in payload_str or "purge" in payload_str:
                risk = 0.85
            elif "update" in payload_str or "install" in payload_str:
                risk = 0.40

            # 3. Compute Goal Fit Heuristic (How well candidate action matches user goal)
            goal_lower = target_goal.lower()
            goal_fit = 0.5
            if act_type in ["open_application", "web_search"] and any(k in goal_lower for k in ["open", "launch", "search"]):
                goal_fit = 0.95
            elif act_type in ["search_files"] and any(k in goal_lower for k in ["find", "file", "song", "document"]):
                goal_fit = 0.95
            elif act_type in ["phone_command"] and any(k in goal_lower for k in ["phone", "call", "sms", "battery"]):
                goal_fit = 0.95

            # Composite utility = 0.5*GoalFit + 0.3*(1 - Risk) + 0.2*(1 - Surprisal)
            utility = round(0.5 * goal_fit + 0.3 * (1.0 - risk) + 0.2 * (1.0 - 0.15), 2)

            branch = SimulationBranch(
                branch_id=uuid4().hex[:8],
                branch_name=act_name,
                hypothetical_action=act_type,
                predicted_state_change=pred.expected_changes,
                risk_score=risk,
                goal_fit_score=goal_fit,
                estimated_surprisal=0.15,
                utility_score=utility,
                reasoning_summary=f"Branch '{act_name}' ({act_type}): GoalFit={goal_fit:.2f}, Risk={risk:.2f}, Utility={utility:.2f}"
            )
            branches.append(branch)

        # Select winning branch (maximizes overall UtilityScore)
        branches.sort(key=lambda b: b.utility_score, reverse=True)
        winning_branch = branches[0] if branches else SimulationBranch(
            branch_id="fallback",
            branch_name="Default Fallback",
            hypothetical_action="observe",
            predicted_state_change={},
            risk_score=0.0,
            goal_fit_score=0.0,
            estimated_surprisal=0.0,
            utility_score=0.0,
            reasoning_summary="No candidate branches provided; falling back to observe."
        )

        return CounterfactualSimulationResult(
            simulation_id=f"sim_{uuid4().hex[:8]}",
            target_goal=target_goal,
            winning_branch=winning_branch,
            competing_branches=branches
        )
