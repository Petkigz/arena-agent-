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

        # NOT_CHECKED != AVAILABLE (P0 #21): a candidate whose dependency was
        # never probed is a RISK, not a capability. Before committing, probe
        # the chosen tool's dependencies (one module import, cached). A
        # KNOWN-unavailable winner is skipped in favor of the next branch
        # that probes available; if nothing is available the winner stands
        # but the proposal carries the honest state — the missing dependency
        # must be visible at PLANNING time, not discovered mid-execution.
        winner = cls._probe_and_select(sim_res, winner)

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

    @classmethod
    def _probe_and_select(cls, sim_res, winner):
        """Probe branch dependencies before committing to a winner (P0 #21).

        The registry is the only source of truth:
        * not_registered — NOT a registry tool (native master-agent path,
          dynamically registered capability, or a caller-supplied candidate).
          Other execution paths exist; never invent unavailability.
        * available True — committable.
        * available False — dependency KNOWN missing: skip the branch.
        * available None — NOT_CHECKED even after probing: keep as a
          last-resort candidate, annotated honestly.

        Probes use probe=True (one module import, cached for
        ToolRegistry._AVAILABILITY_CACHE_TTL_S).
        """
        try:
            from app.cognition.tool_registry import get_shared_registry
            registry = get_shared_registry()
        except Exception:
            return winner

        branches = sorted(
            [b for b in sim_res.competing_branches
             if getattr(b, "branch_name", "") != "Default Fallback"],
            key=lambda b: getattr(b, "utility_score", 0.0),
            reverse=True,
        )
        if not branches:
            return winner

        best_unknown = None
        best_unknown_status = None
        for branch in branches:
            action = str(getattr(branch, "hypothetical_action", "") or "")
            try:
                status = registry.get_tool_availability(action, probe=True)
            except Exception as exc:
                status = {"available": None, "status": f"probe_error:{exc}"}
            if status.get("status") == "not_registered":
                return branch
            if status.get("available") is True:
                return branch
            if status.get("available") is None and best_unknown is None:
                best_unknown, best_unknown_status = branch, status
            # available False: dependency KNOWN missing — skip this branch.
        if best_unknown is not None:
            # Nothing decisively available: keep the highest-utility
            # not-checked branch, annotated honestly.
            best_unknown.candidate_payload["availability"] = (
                best_unknown_status or {"available": None, "status": "not_checked"}
            )
            app_logger.warning(
                f"ActionPlanner: no branch with a probed-available dependency; "
                f"committing '{best_unknown.hypothetical_action}' with honest "
                f"availability {best_unknown_status}"
            )
            return best_unknown
        # Every registry branch's dependency is KNOWN missing: keep the
        # original winner, annotated, so the gate/owner sees it before
        # execution.
        winner.candidate_payload["availability"] = {
            "available": False, "status": "dependency_unavailable",
        }
        app_logger.warning(
            "ActionPlanner: every candidate branch depends on a missing "
            "dependency; committing the winner with honest availability."
        )
        return winner
