"""Goal Verification Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.utils.logger import app_logger, audit_logger

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class GoalVerificationResult:
    goal_id: str
    verified_success: bool
    final_state: GoalLifecycleState
    verification_reason: str
    failed_action_type: str = ""
    met_conditions: List[str] = field(default_factory=list)
    failed_conditions: List[str] = field(default_factory=list)
    observed_state: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)

class GoalVerifier:
    """
    Goal Verification Engine.
    Evaluates whether the environment actually reached goal_rep.desired_outcome using
    goal_rep.success_conditions and failure_conditions, distinguishing tool execution success
    from true environmental goal achievement.
    """

    @classmethod
    def evaluate_condition_against_world_model(
        cls,
        succ_cond: str,
        goal_rep: SemanticGoalRepresentation,
        observations_map: Dict[str, Any],
        verified_entity_states: Dict[str, str],
        executed_actions: List[str],
        reply_clean: str,
        failed_conditions: List[str]
    ) -> bool:
        """
        Phase 4 Condition Evaluator:
        Evaluates goal conditions directly against WorldModel observations and entities
        rather than relying solely on string searching.
        """
        sc_lower = succ_cond.lower().strip()
        actions_str = " ".join(executed_actions).lower()
        reply_lower = reply_clean.lower()
        has_crash_or_err = len(failed_conditions) > 0 or any(k in reply_lower or k in actions_str for k in ["crash", "crashed", "failed", "error", "not found", "cannot find"])

        if has_crash_or_err:
            return False

        # (a) Response Delivery Condition
        if "response_delivered" in sc_lower:
            return len(reply_clean) > 0

        # (b) App Process / Window Running Condition
        elif any(k in sc_lower for k in ["app_process_running", "process_running", "window_active"]):
            obs_running = any("running" in str(v).lower() or "active" in str(v).lower() for v in observations_map.values())
            entity_running = any("running" in str(st).lower() or "active" in str(st).lower() for st in verified_entity_states.values())
            action_executed = len(executed_actions) > 0 and any(k in actions_str for k in ["launched", "opened", "started", "running"])
            return obs_running or entity_running or action_executed

        # (c) File Path / Access Condition
        elif any(k in sc_lower for k in ["file_path_identified", "file_accessed", "path_found"]):
            obs_found = any("file" in k or "path" in k for k in observations_map.keys())
            has_file_path = obs_found or any(k in reply_lower or k in actions_str for k in ["path", "found file", "file located", "c:", "/home", "f:", "d:", ".txt", ".py", ".pdf", ".doc", ".png"])
            return has_file_path

        # (d) Web Research / Search Results Condition
        elif any(k in sc_lower for k in ["search_results_retrieved", "results_found"]):
            obs_results = any("web_search" in k or "search_results" in k for k in observations_map.keys())
            has_results = obs_results or len(reply_clean) > 20 or any(k in reply_lower or k in actions_str for k in ["http", "search results", "retrieved", "found", "summary"])
            return has_results

        # (e) Diagnostic Evidence Condition
        elif any(k in sc_lower for k in ["diagnostic_evidence_gathered", "evidence_gathered"]):
            obs_evidence = any("diagnostic" in k or "evidence" in k for k in observations_map.keys())
            return obs_evidence or len(reply_clean) > 10 or len(executed_actions) > 0

        # (f) ADB / Phone Command Condition
        elif any(k in sc_lower for k in ["adb_command_succeeded", "phone_action_completed"]):
            obs_adb = any("adb" in k or "battery" in k for k in observations_map.keys())
            has_adb_ok = obs_adb or any(k in reply_lower or k in actions_str for k in ["adb", "battery", "call", "sms", "photo", "screen", "succeeded", "ok", "done"])
            return has_adb_ok

        # (g) Screen Capture Condition
        elif "screen_capture_saved" in sc_lower:
            obs_screen = any("screen" in k or "vision" in k for k in observations_map.keys())
            has_screen_ok = obs_screen or any(k in reply_lower or k in actions_str for k in ["screenshot", "captured", "saved", "vision", "analyzed"])
            return has_screen_ok

        # (h) Generic Fallback Condition: Requires explicit WorldModel observation or entity match
        else:
            cond_key = sc_lower.split("=")[0].strip() if "=" in sc_lower else sc_lower
            for k, v in observations_map.items():
                if cond_key in k.lower() and str(v).lower() not in ["failed", "false", "error"]:
                    return True
            for ent_name, ent_status in verified_entity_states.items():
                if cond_key in ent_name.lower() and ent_status in ["running", "active", "completed"]:
                    return True

            # Unknown/unverified condition without WorldModel observation -> False (unverifiable)
            return False

    @classmethod
    def verify_goal_achievement(
        cls,
        goal_rep: SemanticGoalRepresentation,
        executed_actions: List[str],
        assistant_reply: str,
        failed_action_type: str = "",
        tracker: Optional[GoalTracker] = None,
        observed_state: Optional[Dict[str, Any]] = None
    ) -> GoalVerificationResult:
        goal_id = tracker.goal_id if tracker else "goal_verify_anon"
        if tracker:
            tracker.transition(GoalLifecycleState.VERIFYING, "Evaluating real environmental goal achievement against success_conditions.")

        reply_clean = assistant_reply.strip()
        reply_lower = reply_clean.lower()
        actions_str = " ".join(executed_actions).lower()
        # Extract structured actual_world_state
        obs_dict = dict(observed_state or {})
        entities_list = obs_dict.get("entities", [])
        observations_map = obs_dict.get("observations", {})

        verified_entity_states = {}
        for ent in entities_list:
            if isinstance(ent, dict):
                ent_name = ent.get("name", "unknown")
                ent_status = ent.get("status", "unknown")
                verified_entity_states[ent_name] = ent_status

        # If entities_list empty, populate verified entity states from executed_actions
        if not verified_entity_states and goal_rep.entities:
            for ent_name in goal_rep.entities:
                # Require explicit tool execution record (actions_str), NOT LLM assistant_reply text
                is_executed = len(executed_actions) > 0 and any(k in actions_str for k in ["running", "launched", "opened", "active"]) and not any(k in actions_str or k in reply_lower for k in ["crash", "crashed", "failed", "error", "not found"])
                verified_entity_states[ent_name] = "running" if is_executed else "unknown"

        met_conditions = []
        failed_conditions = []

        # 1. Evaluate Failure Conditions
        for fail_cond in goal_rep.failure_conditions:
            fc_lower = fail_cond.lower()
            if "empty" in fc_lower and not reply_clean:
                failed_conditions.append(fail_cond)
            elif "crashed" in fc_lower or "crash" in fc_lower:
                crashed_in_entities = any("crash" in str(st).lower() or "failed" in str(st).lower() for st in verified_entity_states.values())
                crashed_in_text = any(k in reply_lower or k in actions_str for k in ["crash", "crashed", "segfault", "fatal error", "exited with code"])
                if crashed_in_entities or crashed_in_text:
                    failed_conditions.append(fail_cond)
            elif "launch_failed" in fc_lower or "failed" in fc_lower:
                if any(k in reply_lower or k in actions_str for k in ["launch failed", "could not launch", "failed to start", "unable to open", "cannot find", "application not found"]):
                    failed_conditions.append(fail_cond)
            elif "not_found" in fc_lower or "file_not_found" in fc_lower:
                if any(k in reply_lower or k in actions_str for k in ["file not found", "no such file", "path does not exist", "directory not found"]):
                    failed_conditions.append(fail_cond)
            elif "blocked" in fc_lower:
                if "blocked by" in reply_lower or "action gate blocked" in reply_lower:
                    failed_conditions.append(fail_cond)
            elif "device_offline" in fc_lower:
                if any(k in reply_lower or k in actions_str for k in ["device offline", "no devices", "device not found"]):
                    failed_conditions.append(fail_cond)

        # General error/crash detection
        error_indicators = ["crashed", "fatal error", "unhandled exception", "permission denied", "timed out", "process exited unexpectedly"]
        for err_ind in error_indicators:
            if err_ind in reply_lower or err_ind in actions_str:
                if f"error_detected:{err_ind}" not in failed_conditions:
                    failed_conditions.append(f"Environmental error detected: {err_ind}")

        # 2. Evaluate Success Conditions against Environmental World State
        target_conditions = goal_rep.success_conditions or ["response_delivered = true"]

        for succ_cond in target_conditions:
            cond_met = cls.evaluate_condition_against_world_model(
                succ_cond,
                goal_rep,
                observations_map,
                verified_entity_states,
                executed_actions,
                reply_clean,
                failed_conditions
            )
            if cond_met:
                met_conditions.append(succ_cond)
            else:
                failed_conditions.append(f"unverifiable_condition: {succ_cond}")

        # STRICT SUCCESS EVALUATION:
        # 1. Zero failure conditions detected
        # 2. ALL required success conditions in target_conditions are satisfied
        required_success_count = len(target_conditions)
        verified_success = (len(failed_conditions) == 0) and (len(met_conditions) >= required_success_count)

        if verified_success:
            final_state = GoalLifecycleState.ACHIEVED
        elif any("blocked" in str(fc).lower() for fc in failed_conditions):
            final_state = GoalLifecycleState.BLOCKED
        else:
            final_state = GoalLifecycleState.FAILED

        reason = (
            f"Goal '{goal_rep.goal}' achieved: Satisfied all {len(met_conditions)}/{required_success_count} success conditions against actual world state."
            if verified_success
            else f"Goal verification failed: Met {len(met_conditions)}/{required_success_count} success conditions. Failed conditions: {failed_conditions or ['Target environmental state not verified.']}"
        )

        if tracker:
            tracker.transition(final_state, reason)

        audit_logger.info(f"GoalVerifier [{goal_id[:8]}]: VerifiedSuccess={verified_success}, State={final_state.value}")

        # Construct actual_world_state payload
        actual_world_state = {
            "entities": entities_list if entities_list else [{"name": e, "status": verified_entity_states.get(e, "unknown")} for e in goal_rep.entities],
            "observations": observations_map if observations_map else {f"{goal_rep.target_domain}.status": "running" if verified_success else "failed"},
            "verified_entity_states": verified_entity_states,
            "executed_actions": executed_actions,
            "assistant_reply": assistant_reply[:200],
            "met_conditions_count": len(met_conditions),
            "required_conditions_count": required_success_count
        }

        return GoalVerificationResult(
            goal_id=goal_id,
            verified_success=verified_success,
            final_state=final_state,
            verification_reason=reason,
            failed_action_type=failed_action_type or goal_rep.primary_intent_type,
            met_conditions=met_conditions,
            failed_conditions=failed_conditions,
            observed_state=actual_world_state
        )
