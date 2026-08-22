"""Milestone 4: Counterfactual Parallel Mental Simulator Engine.

Phase 1B: Utility scores are now adjusted by historical strategy outcomes.
Strategies with high success rates are boosted; those with consecutive
failures are deprioritized.
"""

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
    candidate_payload: Dict[str, Any] = field(default_factory=dict)
    history_adjustment: float = 1.0  # Phase 1B: multiplier from historical outcomes

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

    Phase 1B: Utility scores are adjusted by historical strategy outcomes when available.
    """

    # Resource costs per action type (P2 AGI: hierarchical planning with resources)
    # Estimates: cpu 0-1, memory 0-1, time seconds
    RESOURCE_COSTS: Dict[str, Dict[str, float]] = {
        "web_search": {"cpu": 0.1, "memory": 0.1, "time": 2},
        "search_files": {"cpu": 0.2, "memory": 0.2, "time": 1},
        "read_document": {"cpu": 0.1, "memory": 0.2, "time": 1},
        "vision_analyze": {"cpu": 0.4, "memory": 0.7, "time": 15},
        "detect_objects": {"cpu": 0.5, "memory": 0.6, "time": 5},
        "detect_faces": {"cpu": 0.3, "memory": 0.3, "time": 2},
        "analyze_image_grounded": {"cpu": 0.5, "memory": 0.6, "time": 5},
        "run_coding_agent": {"cpu": 0.8, "memory": 0.6, "time": 60},
        "run_data_analysis": {"cpu": 0.6, "memory": 0.5, "time": 20},
        "code_audit": {"cpu": 0.5, "memory": 0.4, "time": 10},
        "generate_presentation": {"cpu": 0.3, "memory": 0.4, "time": 10},
        "generate_document": {"cpu": 0.2, "memory": 0.3, "time": 5},
        "sandbox_run": {"cpu": 0.6, "memory": 0.5, "time": 30},
        "db_query": {"cpu": 0.2, "memory": 0.2, "time": 2},
        "default": {"cpu": 0.3, "memory": 0.3, "time": 5},
    }

    @classmethod
    def simulate_competing_branches(
        cls,
        target_goal: str,
        candidate_actions: List[Dict[str, Any]],
        goal_type: Optional[str] = None,
        outcome_store: Optional[Any] = None,
        lesson_store: Optional[Any] = None,
        skill_classifier: Optional[Any] = None,
        hardware_self_model: Optional[Dict[str, Any]] = None,
        resource_manager: Optional[Any] = None,
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

            # 4. Phase 1B: Historical outcome adjustment
            history_adj = 1.0
            if outcome_store and goal_type:
                history_adj = outcome_store.adjustment_factor(goal_type, act_type)

            # Phase 1C: Lesson-based adjustment (failure pattern influence)
            lesson_adj = 1.0
            if lesson_store and goal_type:
                lesson_adj = lesson_store.lesson_influence(goal_type, act_type)

            # Phase 3A: Skill-based transfer adjustment
            skill_adj = 1.0
            if skill_classifier and outcome_store and goal_type:
                skill_adj = skill_classifier.transfer_adjustment(
                    act_type, outcome_store, goal_type
                )

            # P2 AGI: Resource-aware adjustment — penalize high-cost actions under pressure
            resource_adj = 1.0
            try:
                costs = cls.RESOURCE_COSTS.get(act_type, cls.RESOURCE_COSTS["default"])
                if hardware_self_model:
                    live = hardware_self_model.get("live", {})
                    ram_pressure = float(live.get("ram_percent", 0) or 0)
                    cpu_pressure = float(live.get("cpu_percent", 0) or 0)
                    # If RAM >80% and action needs >0.5 memory, penalize
                    if ram_pressure > 80 and costs["memory"] > 0.5:
                        resource_adj *= 0.6
                    if cpu_pressure > 75 and costs["cpu"] > 0.6:
                        resource_adj *= 0.7
                    # If system is low on disk and action writes files, penalize slightly
                    disk_pressure = float(live.get("disk_percent", 0) or 0)
                    if disk_pressure > 85 and act_type in ("create_document", "generate_presentation", "generate_document", "create_backup"):
                        resource_adj *= 0.8
                if resource_manager:
                    # Check if allocation would exceed budget
                    try:
                        usage = resource_manager.get_usage_report()
                        # Simple check: if any budget >90% utilized, penalize high-cost actions
                        for bname, bdata in usage.get("budgets", {}).items():
                            for rtype, util in bdata.get("utilization", {}).items():
                                if util > 90 and costs.get(rtype, 0) > 0.5:
                                    resource_adj *= 0.7
                    except Exception:
                        pass
            except Exception:
                resource_adj = 1.0

            # Combined adjustment: outcome history × lessons × skill transfer × resources
            combined_adj = history_adj * lesson_adj * skill_adj * resource_adj

            # Composite utility = (0.5*GoalFit + 0.3*(1 - Risk) + 0.2*(1 - Surprisal)) × combined_adjustment
            base_utility = 0.5 * goal_fit + 0.3 * (1.0 - risk) + 0.2 * (1.0 - 0.15)
            utility = round(base_utility * combined_adj, 4)

            history_note = f", HistoryAdj={combined_adj:.2f}" if combined_adj != 1.0 else ""
            branch = SimulationBranch(
                branch_id=uuid4().hex[:8],
                branch_name=act_name,
                hypothetical_action=act_type,
                predicted_state_change=pred.expected_changes,
                risk_score=risk,
                goal_fit_score=goal_fit,
                estimated_surprisal=0.15,
                utility_score=utility,
                reasoning_summary=f"Branch '{act_name}' ({act_type}): GoalFit={goal_fit:.2f}, Risk={risk:.2f}, Utility={utility:.4f}{history_note}",
                candidate_payload=dict(payload),
                history_adjustment=combined_adj
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
