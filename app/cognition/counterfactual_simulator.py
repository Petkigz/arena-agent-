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
    estimated_surprisal: float
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
    evaluating predicted outcomes, risk scores, and surprisal BEFORE touching the live host system.
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

            # 3. Construct Simulation Branch
            branch = SimulationBranch(
                branch_id=uuid4().hex[:8],
                branch_name=act_name,
                hypothetical_action=act_type,
                predicted_state_change=pred.expected_changes,
                risk_score=risk,
                estimated_surprisal=0.15,
                reasoning_summary=f"Branch '{act_name}' executes '{act_type}' predicting {pred.expected_changes} with risk {risk}"
            )
            branches.append(branch)

        # Select winning branch (minimizes risk score and expected surprisal)
        branches.sort(key=lambda b: (b.risk_score, b.estimated_surprisal))
        winning_branch = branches[0] if branches else SimulationBranch(
            branch_id="fallback",
            branch_name="Default Fallback",
            hypothetical_action="observe",
            predicted_state_change={},
            risk_score=0.0,
            estimated_surprisal=0.0,
            reasoning_summary="No candidate branches provided; falling back to observe."
        )

        return CounterfactualSimulationResult(
            simulation_id=f"sim_{uuid4().hex[:8]}",
            target_goal=target_goal,
            winning_branch=winning_branch,
            competing_branches=branches
        )
