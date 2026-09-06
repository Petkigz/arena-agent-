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
    # Consideration is deliberately broader than authorization. A restricted or
    # uncomfortable branch remains visible for consequence comparison, but this
    # field never grants permission to execute it.
    authorization_requirement: str = "policy_review_required"
    consequences: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CounterfactualSimulationResult:
    simulation_id: str
    target_goal: str
    winning_branch: SimulationBranch
    competing_branches: List[SimulationBranch]
    created_at: str = field(default_factory=_now)
    # Measured concurrency evidence from the governor receipt: workers granted,
    # parallel/serial execution, pressure reasons, duration. Configuration only;
    # no authorization meaning.
    execution_evidence: Dict[str, Any] = field(default_factory=dict)

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

    # Honest priors for untested actions (P0 #14): an action with no
    # execution history is a coin flip, never confident-by-default; an
    # UNREGISTERED action is even less certain.
    _UNTESTED_SURPRISAL = 0.5
    _UNREGISTERED_SURPRISAL = 0.7

    # Native executable actions that are NOT manifest tools (open_application
    # and friends, executed by the master agent's resolvers) are still REAL,
    # proven execution paths. They must not be classified as 'unregistered'
    # by the surprisal prior — live regression caught by the full suite:
    # open_application ranked below web_search and rerouted a replan test.
    # ONE list (P0 review #12): the master-agent-native execution paths now
    # live in the capability registry — the planner's provenance classifier
    # reads them from the same source. Alias kept for existing callers.
    from app.cognition.tool_registry import NATIVE_EXECUTABLES as _NATIVE
    _NATIVE_EXECUTABLES = _NATIVE

    @staticmethod
    def _snapshot_manifest_levels() -> Dict[str, int]:
        levels: Dict[str, int] = {}
        try:
            from app.tools.manifest import get_tool_manifest
            levels = {
                name: int(entry.get("safety_level", 0))
                for name, entry in get_tool_manifest().items()
            }
        except Exception:
            levels = {}
        # P0 review #12: the capability authority supplies the full
        # capability universe — manifest AND runtime-installed tools — with
        # the registry's (runtime) readings overriding the static catalog.
        try:
            from app.cognition.tool_registry import get_shared_registry
            for name, entry in get_shared_registry().capabilities().items():
                # Safety level 0 (read-only) is a REAL value — an `or`
                # default coerces it to 99 and reclassifies read-only
                # actions as owner-approval.
                level = entry.get("safety_level")
                if level is None:
                    levels[name] = 99
                    continue
                try:
                    levels[name] = int(level)
                except (TypeError, ValueError):
                    levels[name] = 99
        except Exception:
            pass
        for _native in CounterfactualSimulator._NATIVE_EXECUTABLES:
            levels.setdefault(_native, 1)
        return levels

    @staticmethod
    def _estimate_surprisal(act_type: str, manifest_levels: Dict[str, int]) -> tuple:
        """Honest pre-execution uncertainty (P0 bottleneck #14): how
        surprised WOULD we be by this branch's outcome?

        Derived from Arena's verified execution history
        (app.cognition.action_outcomes — built for exactly this purpose and
        previously ignored here in favor of a hardcoded 0.15):

        * outcome DISPERSION: an action whose verified outcomes are
          consistent (always or never succeeds) is predictable — low
          surprisal. A 50/50 action is genuinely unpredictable — high
          surprisal. This is what makes the term DISCRIMINATE between
          branches.
        * Wilson interval WIDTH: few samples keep the interval wide, so
          thin evidence stays uncertain instead of masquerading as
          knowledge.
        * No history at all: the honest coin-flip prior (0.5), labeled as
          such — never a fake confident constant.

        Returns (surprisal, source_label)."""
        try:
            from app.cognition.action_outcomes import action_outcome_store
            est = action_outcome_store.estimate(act_type)
        except Exception:
            est = None
        if est is not None and getattr(est, "n", 0) > 0:
            p = max(0.0, min(1.0, float(est.smoothed_success_rate)))
            dispersion = 2.0 * p * (1.0 - p)
            width = max(0.0, float(est.wilson_high) - float(est.wilson_low))
            surprisal = min(1.0, max(0.0, 0.6 * dispersion + 0.4 * width))
            return surprisal, f"learned (n={est.n})"
        if act_type in manifest_levels:
            return CounterfactualSimulator._UNTESTED_SURPRISAL, "prior (no execution history)"
        return CounterfactualSimulator._UNREGISTERED_SURPRISAL, "prior (unregistered action)"

    @staticmethod
    def _simulate_one_branch(
        idx_act: tuple,
        *,
        target_goal: str,
        goal_type: Optional[str],
        outcome_store,
        lesson_store,
        skill_classifier,
        hardware_self_model,
        resource_manager,
        manifest_levels: Dict[str, int],
    ) -> SimulationBranch:
        """Compute one branch. Pure function of its inputs; no shared mutable state."""
        idx, act = idx_act
        act_name = act.get("name", f"Branch_{idx}")
        act_type = act.get("action_type", "generic_action")
        payload = act.get("payload", {})
        pe = PredictionEngine()

        # 1. Predict state change
        pred = pe.predict_action(act_type, payload)

        # 2. Compute risk score heuristic
        risk = 0.1
        # Include the action name: a send/delete/trade action can be risky
        # even when its payload contains only a target and content/path.
        action_context = f"{act_type} {payload}".lower()
        if any(k in action_context for k in ("delete", "remove", "purge", "trade")):
            risk = 0.85
        elif any(k in action_context for k in ("send", "publish", "production", "shell")):
            risk = 0.70
        elif "update" in action_context or "install" in action_context:
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
            costs = CounterfactualSimulator.RESOURCE_COSTS.get(act_type, CounterfactualSimulator.RESOURCE_COSTS["default"])
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

        # Phase 3: structural analogical evidence is advisory and bounded. It
        # is deliberately carried outside the executable payload so it cannot
        # become an authorization or execution claim.
        analogical_adj = 1.0
        try:
            analogical_adj = max(
                0.88,
                min(1.12, float(act.get("_analogical_adjustment", 1.0))),
            )
        except Exception:
            analogical_adj = 1.0

        # Combined adjustment: outcome history × lessons × skill transfer × resources × analogies
        combined_adj = history_adj * lesson_adj * skill_adj * resource_adj * analogical_adj

        # 5. Honest surprisal (P0 #14): evidence-derived uncertainty that
        # actually discriminates branches — consistent verified outcomes are
        # predictable, 50/50 outcomes are not, and no history is an honest
        # prior instead of a decorative 0.15.
        surprisal, surprisal_source = CounterfactualSimulator._estimate_surprisal(
            act_type, manifest_levels)

        # Composite utility = (0.5*GoalFit + 0.3*(1 - Risk) + 0.2*(1 - Surprisal)) × combined_adjustment
        base_utility = 0.5 * goal_fit + 0.3 * (1.0 - risk) + 0.2 * (1.0 - surprisal)
        utility = round(base_utility * combined_adj, 4)

        history_note = ""
        if combined_adj != 1.0:
            history_note = f", HistoryAdj={combined_adj:.2f}"
        if analogical_adj != 1.0:
            history_note += f", AnalogyAdj={analogical_adj:.2f}"
            analogy_reason = str(act.get("_analogical_reason", "")).strip()
            if analogy_reason:
                history_note += f" [{analogy_reason}]"

        # Classify the authorization requirement without invoking the gate.
        # Simulation/consideration must be side-effect free: even sensitive
        # alternatives may be examined and compared before a recommendation
        # is made. Only the later ActionGate stage can authorize execution.
        authorization_requirement = "policy_review_required"
        if act_type in manifest_levels:
            level = manifest_levels[act_type]
            authorization_requirement = (
                "explicit_owner_approval" if level >= 3 else "delegated_policy"
            )

        consequences = {
            "expected_benefit": round(goal_fit, 4),
            "risk": round(risk, 4),
            "uncertainty": round(surprisal, 4),
            "uncertainty_source": surprisal_source,
            "reversible": risk < 0.70,
            "predicted_state_change": dict(pred.expected_changes),
        }
        return SimulationBranch(
            branch_id=uuid4().hex[:8],
            branch_name=act_name,
            hypothetical_action=act_type,
            predicted_state_change=pred.expected_changes,
            risk_score=risk,
            goal_fit_score=goal_fit,
            estimated_surprisal=round(surprisal, 4),
            utility_score=utility,
            reasoning_summary=(
                f"Branch '{act_name}' ({act_type}): GoalFit={goal_fit:.2f}, Risk={risk:.2f}, "
                f"Surprisal={surprisal:.2f} [{surprisal_source}], Utility={utility:.4f}{history_note}"
            ),
            candidate_payload=dict(payload),
            history_adjustment=combined_adj,
            authorization_requirement=authorization_requirement,
            consequences=consequences,
        )

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

        # Snapshot manifest levels once: deterministic and thread-safe.
        manifest_levels = CounterfactualSimulator._snapshot_manifest_levels()

        def branch_fn(idx_act):
            return cls._simulate_one_branch(
                idx_act,
                target_goal=target_goal,
                goal_type=goal_type,
                outcome_store=outcome_store,
                lesson_store=lesson_store,
                skill_classifier=skill_classifier,
                hardware_self_model=hardware_self_model,
                resource_manager=resource_manager,
                manifest_levels=manifest_levels,
            )

        # Measured concurrency: the granted worker budget comes from live RAM/CPU
        # pressure and the owner's persisted override; execution evidence (workers,
        # duration, reasons) is returned with the result and receipted.
        from app.utils.concurrency_governor import ConcurrencyGovernor

        enumerated = list(enumerate(candidate_actions, 1))
        branches, receipt = ConcurrencyGovernor.run_parallel(
            branch_fn, enumerated, label="counterfactual_branches"
        )
        branches: List[SimulationBranch] = list(branches)

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
            competing_branches=branches,
            execution_evidence=receipt,
        )
