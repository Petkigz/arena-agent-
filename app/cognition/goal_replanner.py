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
    def compute_strategy_id(cls, strategy: Dict[str, Any] | Any) -> str:
        """
        P1 Fix: Computes a deterministic strategy_id for candidate strategy branches and proposals.
        Format: '<action_type>::<name_slug>::<query_slug>'
        Makes strategy_id the unit of failure in GoalReplanner rather than prohibiting the entire capability.
        """
        if isinstance(strategy, dict):
            act_type = str(strategy.get("action_type", "generic")).lower().strip()
            name = str(strategy.get("name", "")).lower().strip()
            payload = strategy.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
        else:
            act_type = getattr(strategy, "action_type", str(strategy)).lower().strip()
            name = getattr(strategy, "branch_name", getattr(strategy, "name", "")).lower().strip()
            payload = getattr(strategy, "payload", {}) if hasattr(strategy, "payload") else {}

        query = str(payload.get("query") or payload.get("search_term") or payload.get("app_name") or "").lower().strip()
        engine = str(payload.get("engine", "")).lower().strip()

        name_slug = "".join(c for c in name if c.isalnum() or c == "_")[:20]
        query_slug = "".join(c for c in query if c.isalnum() or c == "_")[:30]
        engine_slug = f"_{engine}" if engine else ""

        return f"{act_type}::{name_slug}::{query_slug}{engine_slug}"

    @classmethod
    def is_failed_strategy_instance(
        cls,
        candidate: Dict[str, Any],
        failed_action_type: str,
        failed_payload: Dict[str, Any]
    ) -> bool:
        """
        Checks if a candidate is the exact failed strategy instance.
        Two candidates with the same action_type are DIFFERENT strategies if their
        payload queries, engines, or strategy parameters differ.
        """
        if candidate.get("action_type") != failed_action_type:
            return False

        c_payload = candidate.get("payload", {})
        if not isinstance(c_payload, dict):
            c_payload = {}

        c_query = str(c_payload.get("query") or c_payload.get("search_term") or c_payload.get("app_name") or "").lower().strip()
        f_query = str(failed_payload.get("query") or failed_payload.get("search_term") or failed_payload.get("app_name") or "").lower().strip()

        c_engine = str(c_payload.get("engine", "")).lower().strip()
        f_engine = str(failed_payload.get("engine", "")).lower().strip()

        # If engines differ (e.g. Google vs YouTube), they are different strategy instances
        if c_engine and f_engine and c_engine != f_engine:
            return False

        # If queries differ (e.g. query A vs query B), they are different strategy instances
        if c_query and f_query and c_query != f_query:
            return False

        # If action_type matches and query/engine match (or no query differentiation provided), it's the failed strategy instance
        return True

    # Actions that search the PUBLIC web. They can never satisfy a
    # LOCAL-artifact success condition (see _cannot_satisfy_goal_conditions).
    _WEB_RESEARCH_ACTIONS = {"web_search", "open_url"}

    # F5 (D9): the web allowlist — domains whose goals a public web search
    # can legitimately serve in Plan-B.
    _WEB_FALLBACK_ALLOWED_DOMAINS = {"web_research"}

    # Condition stems that demand LOCAL-VERIFIABLE content (artifacts,
    # environment, capabilities, or values computed from local data). A
    # public web search can produce none of them. Word-initial matching
    # (not preceded by a letter) so it also works inside snake_case
    # condition names without 'latest' matching the test stem.
    _LOCAL_CONTENT_CONDITION_STEMS = (
        "file_path", "path_found", "file_accessed", "file_content",
        "artifact", "capability", "app_process", "process_running",
        "test_results", "computed_answer", "answer_value",
        "summary_included", "screen_capture", "adb_command",
        "diagnostic_evidence",
    )

    @classmethod
    def _cannot_satisfy_goal_conditions(cls, action_type: str, goal_rep: Any) -> bool:
        """True when this action STRUCTURALLY cannot verify the goal.

        F5 inversion (live D9, 2026-09-01): a project-setup goal's Plan-B
        leaked the whole request to google.com (429). The pre-fix filter
        was a DENYLIST — web actions were excluded only when the goal's
        conditions contained local-ARTIFACT keys — and the live goal's
        conditions came from the LLM v2 path ('project_created = true')
        with no artifact key, so the denylist missed. A denylist keyed on
        condition VOCABULARY loses every time the model words conditions
        differently.

        Web-research actions now need to EARN their place (allowlist): a
        public web search may enter the Plan-B ladder only for INFORMATION
        goals — the domain is web research, or the goal is a knowledge
        query whose conditions are reply-shaped. Action goals (create /
        set up / organize / install / compute) can never be satisfied by
        searching the public web, and routing them there leaks the
        request. Non-web actions are untouched, and first-attempt
        discovery breadth stays as it was — this is the replan ranking
        layer only.
        """
        if str(action_type or "").lower().strip() not in cls._WEB_RESEARCH_ACTIONS:
            return False
        domain = str(getattr(goal_rep, "target_domain", "") or "").lower().strip()
        intent = str(getattr(goal_rep, "primary_intent_type", "") or "").lower().strip()
        if domain in cls._WEB_FALLBACK_ALLOWED_DOMAINS:
            return False
        # Action goals (and information_NEED goals, which demand local
        # diagnostic evidence) are never web-satisfiable.
        if intent and intent != "knowledge_query":
            return True
        # Knowledge query (or a metadata-less goal view): web can serve it
        # only if no condition demands local-verifiable content.
        try:
            conditions = list(getattr(goal_rep, "success_conditions", []) or [])
        except Exception:
            return False
        if not conditions:
            return False
        import re as _re
        for c in conditions:
            c_lower = str(c).lower()
            for stem in cls._LOCAL_CONTENT_CONDITION_STEMS:
                if _re.search(rf"(?<![a-z]){_re.escape(stem)}", c_lower):
                    return True
        return False

    @classmethod
    def execute_reassessment_and_replan(
        cls,
        user_text: str,
        goal_rep: SemanticGoalRepresentation,
        failed_result: GoalVerificationResult,
        tracker: GoalTracker,
        complexity: str = "fast",
        memory_store: Optional[Any] = None,
        world_model: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        failed_payload: Optional[Dict[str, Any]] = None,
        lesson_store: Optional[Any] = None,
        outcome_store: Optional[Any] = None,
        hardware_self_model: Optional[Dict[str, Any]] = None,
        resource_manager: Optional[Any] = None,
    ) -> Optional[ActionProposal]:
        app_logger.info(f"GoalReplanner triggered for goal '{tracker.goal_id[:8]}': Reassessing & generating Plan B...")

        # Handle UNKNOWN verification (perception evidence missing, zero hard failures)
        if failed_result.is_unknown and not failed_result.failed_conditions:
            app_logger.info(f"GoalReplanner: Verification status is UNKNOWN (missing perception evidence). Triggering re-observation probe...")
            tracker.transition(GoalLifecycleState.REASSESSING, f"Re-observing environment for unknown conditions: {failed_result.unknown_conditions}")
            tracker.transition(GoalLifecycleState.REPLAN, "Generating diagnostic re-observation probe strategy.")

            re_obs_candidates = [
                {"name": "Diagnostic Re-observation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}}
            ]
            return ActionPlanner.plan_and_evaluate_action(
                user_text, complexity=complexity, goal_rep=goal_rep, candidates=re_obs_candidates,
                memory_store=memory_store, world_model=world_model, tool_registry=tool_registry,
                outcome_store=outcome_store, lesson_store=lesson_store,
                hardware_self_model=hardware_self_model, resource_manager=resource_manager,
            )

        tracker.transition(GoalLifecycleState.REASSESSING, f"Reassessing failed conditions: {failed_result.failed_conditions}")

        # Update Goal Representation unknowns
        goal_rep.unknowns.append(f"Primary strategy failed: {failed_result.verification_reason}")
        goal_rep.confidence = max(0.30, goal_rep.confidence - 0.20)

        tracker.transition(GoalLifecycleState.REPLAN, "Generating alternative Plan B candidate strategies.")

        # Filter out exact failed strategy instance (same action_type AND same query/engine)
        failed_action_type = failed_result.failed_action_type or goal_rep.primary_intent_type
        f_payload = failed_payload or getattr(failed_result, "failed_payload", {}) or {}
        app_logger.info(f"GoalReplanner filtering out failed strategy instance '{failed_action_type}' for goal '{tracker.goal_id[:8]}'")

        all_candidates = ActionPlanner.generate_candidate_actions(
            user_text, complexity=complexity, goal_rep=goal_rep, memory_store=memory_store, world_model=world_model, tool_registry=tool_registry
        )
        plan_b_candidates = [
            c for c in all_candidates
            if not cls.is_failed_strategy_instance(c, failed_action_type, f_payload)
            and not cls._cannot_satisfy_goal_conditions(c.get("action_type"), goal_rep)
        ]

        if not plan_b_candidates:
            fallbacks = [
                {"name": "Web Research Fallback Strategy", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}},
                {"name": "Diagnostic Investigation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}},
                {"name": "Local Filesystem Search", "action_type": "search_files", "payload": {"query": __import__("app.cognition.goal_interpreter", fromlist=["extract_search_query"]).extract_search_query(user_text), "action_type": "search_files"}}
            ]
            plan_b_candidates = [
                f for f in fallbacks
                if not cls.is_failed_strategy_instance(f, failed_action_type, f_payload)
                and not cls._cannot_satisfy_goal_conditions(f.get("action_type"), goal_rep)
            ]

        replan_proposal = ActionPlanner.plan_and_evaluate_action(
            user_text, complexity=complexity, goal_rep=goal_rep, candidates=plan_b_candidates,
            memory_store=memory_store, world_model=world_model, tool_registry=tool_registry,
            outcome_store=outcome_store, lesson_store=lesson_store,
            hardware_self_model=hardware_self_model, resource_manager=resource_manager,
        )
        audit_logger.info(f"GoalReplanner evaluated {len(plan_b_candidates)} Plan B branches, generated proposal '{replan_proposal.action_type}'")

        return replan_proposal
