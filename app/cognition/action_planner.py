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
        analogical_memory: Optional[Any] = None,
        hardware_self_model: Optional[Dict[str, Any]] = None,
        resource_manager: Optional[Any] = None,
    ) -> ActionProposal:
        """
        Generates candidate strategies via SemanticGoalInterpreter (or uses provided candidates),
        runs parallel counterfactual simulation in memory, and constructs the winning ActionProposal,
        preserving 100% of the winning candidate's payload fields.

        Phase 1B: When outcome_store is provided, historical success rates adjust utility scores.
        Phase 1C: When lesson_store is provided, structured lessons influence strategy selection.
        Phase 3: When analogical_memory is provided, structurally similar verified
        tasks adjust candidate utility without changing execution authority.
        P2 AGI: When hardware_self_model/resource_manager provided, resource-aware adjustment
        penalizes high-cost actions under pressure (RAM/CPU/disk).
        """
        if candidates is not None:
            # Explicit capability provenance (P0 review #2): candidates the
            # CALLER provided are tagged as such (copies — caller dicts are
            # never mutated). Provenance participates in winner selection.
            candidate_list = []
            for c in candidates:
                copy = dict(c)
                payload = dict(copy.get("payload") or {})
                payload.setdefault("provenance", "caller_supplied")
                copy["payload"] = payload
                candidate_list.append(copy)
        else:
            candidate_list = cls.generate_candidate_actions(
                goal_text, complexity=complexity, goal_rep=goal_rep, memory_store=memory_store, world_model=world_model, tool_registry=tool_registry
            )
        if analogical_memory is not None and goal_rep is not None:
            candidate_list = cls._apply_analogical_guidance(
                candidate_list,
                goal_rep=goal_rep,
                analogical_memory=analogical_memory,
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
    def _apply_analogical_guidance(
        cls,
        candidates: List[Dict[str, Any]],
        *,
        goal_rep: SemanticGoalRepresentation,
        analogical_memory: Any,
    ) -> List[Dict[str, Any]]:
        """Annotate candidates with bounded structural-memory evidence.

        Analogical recall is advisory only.  It changes simulated utility by a
        small capped multiplier; it never authorizes a tool, bypasses an
        approval gate, or turns a past success into current execution truth.
        """
        domain_entity_types = {
            "filesystem": ["file"],
            "desktop_os": ["process"],
            "web_research": ["url"],
            "mobile_phone": ["phone"],
            "vision_desktop": ["screen"],
            "conversation": ["conversation"],
        }
        entity_types = domain_entity_types.get(
            str(getattr(goal_rep, "target_domain", "") or ""),
            [str(getattr(goal_rep, "target_domain", "unknown") or "unknown")],
        )
        try:
            matches = analogical_memory.find_analogies(
                intent_type=str(getattr(goal_rep, "primary_intent_type", "unknown")),
                target_domain=str(getattr(goal_rep, "target_domain", "unknown")),
                entity_types=entity_types,
                limit=20,
                min_similarity=0.4,
            )
        except Exception as exc:
            app_logger.warning(f"Analogical guidance unavailable; keeping normal planning: {exc}")
            return candidates

        if not matches:
            return candidates

        guided: List[Dict[str, Any]] = []
        for original in candidates:
            candidate = dict(original)
            action_type = str(candidate.get("action_type", ""))
            relevant = [
                match for match in matches
                if str(getattr(getattr(match, "past_task", None), "action_type", "")) == action_type
            ]
            if relevant:
                signals = [
                    (1.0 if bool(getattr(match.past_task, "success", False)) else -1.0)
                    * float(getattr(match, "similarity", 0.0) or 0.0)
                    for match in relevant[:8]
                ]
                signal = sum(signals) / max(1, len(signals))
                adjustment = max(0.88, min(1.12, 1.0 + (0.12 * signal)))
                candidate["_analogical_adjustment"] = adjustment
                candidate["_analogical_reason"] = (
                    f"{len(relevant)} structurally similar task(s): "
                    f"{sum(1 for match in relevant if getattr(match.past_task, 'success', False))} succeeded, "
                    f"{sum(1 for match in relevant if not getattr(match.past_task, 'success', False))} failed"
                )
            guided.append(candidate)
        return guided

    @classmethod
    def _probe_and_select(cls, sim_res, winner):
        """Select the winning branch by capability PROVENANCE, then utility.

        'not registered' never means 'definitely executable elsewhere' (P0
        review #2): an unregistered candidate must not steal the selection
        from a probed-available registered one on mere utility order. Each
        branch is classified by explicit provenance —

            native           master-agent execution path (executable by
                             construction)
            registry         manifest-registered tool (probed availability)
            dynamic          runtime-registered tool (probed availability)
            caller_supplied  candidate the caller provided explicitly
            unknown          no registry entry, no native path

        — and availability, then ranked in tiers:

            tier 1  verified executable now: native, or registered with
                    available=True
            tier 2  registered but NOT_CHECKED even after probing
            tier 3  unverifiable: caller_supplied / unknown
            excluded  registered with available=False (dependency KNOWN
                    missing)

        The highest tier wins; utility decides within a tier. Lower tiers
        only ever win when no higher tier exists, and their payload is
        annotated with the honest provenance so the gate and the owner see
        what kind of capability was committed.
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

        tier1, tier2, tier3 = [], [], []
        for branch in branches:
            provenance, status = cls._classify_capability(
                branch, registry)
            if provenance in ("registry", "dynamic"):
                available = status.get("available")
                if available is False:
                    continue  # dependency KNOWN missing
                if available is True:
                    tier1.append((branch, provenance, status))
                else:
                    tier2.append((branch, provenance, status))
            elif provenance == "native":
                tier1.append((branch, provenance, status))
            else:  # caller_supplied / unknown
                tier3.append((branch, provenance, status))

        if tier1:
            return tier1[0][0]
        if tier2:
            branch, provenance, status = tier2[0]
            branch.candidate_payload["availability"] = status
            branch.candidate_payload["provenance"] = provenance
            app_logger.warning(
                f"ActionPlanner: no verified-executable branch; committing "
                f"'{branch.hypothetical_action}' ({provenance}) with honest "
                f"availability {status}"
            )
            return branch
        if tier3:
            branch, provenance, status = tier3[0]
            branch.candidate_payload["provenance"] = provenance
            app_logger.warning(
                f"ActionPlanner: no registry-backed branch exists; committing "
                f"'{branch.hypothetical_action}' with unverifiable provenance "
                f"'{provenance}'"
            )
            return branch

        # Only registry branches remain, every one KNOWN unavailable: the
        # winner stands, annotated, so the gate/owner sees it before execution.
        winner.candidate_payload["availability"] = {
            "available": False, "status": "dependency_unavailable",
        }
        app_logger.warning(
            "ActionPlanner: every candidate branch depends on a missing "
            "dependency; committing the winner with honest availability."
        )
        return winner

    @classmethod
    def _classify_capability(cls, branch, registry) -> tuple:
        """(provenance, availability_status) for one branch's action type."""
        action = str(getattr(branch, "hypothetical_action", "") or "")
        payload = getattr(branch, "candidate_payload", None) or {}

        from app.cognition.counterfactual_simulator import CounterfactualSimulator
        if action in CounterfactualSimulator._NATIVE_EXECUTABLES:
            return "native", {"available": True, "status": "native_execution_path"}

        try:
            status = registry.get_tool_availability(action, probe=True)
        except Exception as exc:
            status = {"available": None, "status": f"probe_error:{exc}"}

        if status.get("status") != "not_registered":
            # Typed origin (P1 review): source runtime_install == what the
            # legacy 'dynamic' marker meant; the tier labels below are this
            # planner's own vocabulary.
            provenance = ("dynamic"
                          if status.get("source") == "runtime_install"
                          else "registry")
            return provenance, status

        # Not a registry tool. If the caller supplied this candidate
        # explicitly, say so; otherwise its provenance is honestly unknown.
        if payload.get("provenance") == "caller_supplied":
            return "caller_supplied", status
        return "unknown", status
