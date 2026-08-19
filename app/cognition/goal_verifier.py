"""Goal Verification Engine."""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.utils.logger import app_logger, audit_logger

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class ConditionStatus(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    UNKNOWN = "unknown"

class GoalConditionType(str, Enum):
    RESPONSE = "response"       # Language-level response (valid ONLY for conversational/knowledge_query goals)
    ENVIRONMENT = "environment" # Environmental OS process or hardware state (requires DIRECT perception probe)
    STATE = "state"             # Entity state / attribute condition
    ARTIFACT = "artifact"       # Created file, image, or output artifact
    EXTERNAL = "external"       # External system / ADB / network confirmation

@dataclass
class GoalVerificationResult:
    goal_id: str
    verified_success: bool
    final_state: GoalLifecycleState
    verification_reason: str
    failed_action_type: str = ""
    failed_payload: Dict[str, Any] = field(default_factory=dict)
    met_conditions: List[str] = field(default_factory=list)
    failed_conditions: List[str] = field(default_factory=list)
    unknown_conditions: List[str] = field(default_factory=list)
    is_unknown: bool = False
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
    def matches_canonical_entity(
        cls,
        entity_needle: str,
        subject_key: str,
        entity_attributes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        P1 Fix: Canonical Entity Matcher.
        Binds condition evaluation to exact canonical entity names and aliases with token boundaries,
        preventing substring collisions (e.g. 'chrome' matching 'chromedriver').
        """
        import re
        n_clean = entity_needle.lower().strip()
        s_clean = subject_key.split(".")[0].lower().strip() if "." in subject_key else subject_key.lower().strip()

        # Prevent known distinct suffix collisions like 'chrome' matching 'chromedriver'
        needle_tokens = [t for t in re.split(r'[\s._\-/\\]+', n_clean) if t]
        if needle_tokens and len(needle_tokens) == 1:
            main_needle = needle_tokens[0]
            if any(s_clean == f"{main_needle}{suf}" or s_clean == f"{main_needle}_{suf}" for suf in ["driver", "agent", "helper", "service", "plugin", "runner"]):
                return False

        # 1. Exact canonical name match
        if n_clean == s_clean:
            return True

        # 2. Check explicit aliases list if attributes supplied
        if entity_attributes and isinstance(entity_attributes.get("aliases"), list):
            aliases = [str(a).lower().strip() for a in entity_attributes["aliases"]]
            for a in aliases:
                a_tokens = [t for t in re.split(r'[\s._\-/\\]+', a) if t]
                if a == s_clean or s_clean in a_tokens or n_clean in a_tokens or a in subject_key.lower():
                    return True

        # 3. Exact word boundary token match
        tokens = [t for t in re.split(r'[\s._\-/\\]+', subject_key.lower()) if t]
        if needle_tokens:
            main_needle = needle_tokens[0]
            if all(nt in tokens for nt in needle_tokens) or main_needle in tokens:
                return True

        return False

    @classmethod
    def classify_condition_type(
        cls,
        succ_cond: str,
        primary_intent_type: str,
        target_domain: str
    ) -> GoalConditionType:
        """
        Classifies goal conditions into explicit condition types:
        RESPONSE, ENVIRONMENT, STATE, ARTIFACT, EXTERNAL.
        Routes verification strictly to the authoritative evidence channel for that condition type.
        """
        sc_lower = succ_cond.lower().strip()

        if "response_delivered" in sc_lower or "answer_provided" in sc_lower:
            if primary_intent_type == "knowledge_query" or target_domain == "conversation":
                return GoalConditionType.RESPONSE
            else:
                return GoalConditionType.ENVIRONMENT

        if any(k in sc_lower for k in ["app_process_running", "process_running", "window_active", "status = running"]):
            return GoalConditionType.ENVIRONMENT

        if any(k in sc_lower for k in ["file_path_identified", "file_accessed", "path_found", "screen_capture_saved", "artifact_created"]):
            return GoalConditionType.ARTIFACT

        if any(k in sc_lower for k in ["adb_command_succeeded", "phone_action_completed", "network_available"]):
            return GoalConditionType.EXTERNAL

        return GoalConditionType.STATE

    @classmethod
    def is_direct_provenance_evidence(cls, obs_entry: Any, allowed_types: Optional[List[str]] = None) -> tuple[bool, Any]:
        """
        P0 Fix: Universal Provenance Enforcement for both Observations and Entity States.
        Returns (is_authorized_evidence, value).
        EVERY environmental fact entering verification must carry authorized provenance
        (DIRECT / ENVIRONMENTAL evidence from process probes, filesystem probes, or system probes).
        SELF_REPORTED claims or un-provenanced entity states CANNOT satisfy environmental conditions.
        """
        if allowed_types is None:
            allowed_types = ["direct", "environmental"]

        if isinstance(obs_entry, dict):
            val = obs_entry.get("status") if "status" in obs_entry else obs_entry.get("value")
            # Require explicit provenance fields — missing keys do NOT default to authoritative
            raw_obs_type = obs_entry.get("observation_type")
            raw_source = obs_entry.get("source")
            raw_confidence = obs_entry.get("confidence")

            # If observation_type or source is missing, this dict has no provenance metadata
            if raw_obs_type is None and raw_source is None:
                return False, val

            obs_type = str(raw_obs_type or "").lower().strip()
            source = str(raw_source or "").lower().strip()
            confidence = float(raw_confidence) if raw_confidence is not None else 0.0

            # Exclude self_reported execution claims or un-provenanced tool logs
            if obs_type == "self_reported" or "execution_result" in source or "system_app_inventory" in source:
                return False, val

            is_authorized = (
                obs_type in allowed_types or
                any(k in source for k in ["os_process_probe", "filesystem_probe", "process_inspector", "system_probe", "win32_api", "web_researcher", "universal_filesystem", "fs"])
            ) and confidence >= 0.8
            return is_authorized, val
        else:
            # Primitive (non-dict) evidence carries no provenance metadata.
            # It cannot be verified as direct/environmental — return non-authoritative.
            return False, obs_entry

    @classmethod
    def evaluate_condition_status_against_world_model(
        cls,
        succ_cond: str,
        goal_rep: SemanticGoalRepresentation,
        observations_map: Dict[str, Any],
        verified_entity_states: Dict[str, Any],
        executed_actions: List[str],
        reply_clean: str,
        failed_conditions: List[str],
        verified_entity_details: Optional[Dict[str, Any]] = None
    ) -> ConditionStatus:
        """
        Phase E Tri-State Condition Evaluator:
        Evaluates conditions into explicit SATISFIED, FAILED, or UNKNOWN states.
        Differentiates explicit environmental failure from missing perception evidence (UNKNOWN).
        """
        sc_lower = succ_cond.lower().strip()
        actions_str = " ".join(executed_actions).lower()
        reply_lower = reply_clean.lower()
        has_crash_or_err = len(failed_conditions) > 0 or any(k in reply_lower or k in actions_str for k in ["crash", "crashed", "failed", "error", "cannot find"])

        if has_crash_or_err:
            return ConditionStatus.FAILED

        cond_type = cls.classify_condition_type(succ_cond, goal_rep.primary_intent_type, goal_rep.target_domain)

        # (a) Response Delivery Condition
        if cond_type == GoalConditionType.RESPONSE or "response_delivered" in sc_lower:
            return ConditionStatus.SATISFIED if len(reply_clean) > 0 else ConditionStatus.FAILED

        # (b) App Process / Window Running Condition (Subject-Bound DIRECT Provenance Verification)
        elif cond_type == GoalConditionType.ENVIRONMENT or any(k in sc_lower for k in ["app_process_running", "process_running", "window_active"]):
            target_entities = [e.lower().strip() for e in goal_rep.entities] if goal_rep.entities else []
            if target_entities:
                for ent in target_entities:
                    for k, obs_entry in observations_map.items():
                        if cls.matches_canonical_entity(ent, k):
                            is_auth, val = cls.is_direct_provenance_evidence(obs_entry, allowed_types=["direct", "environmental"])
                            val_str = str(val).lower().strip()
                            if is_auth and val_str in ["running", "active"]:
                                return ConditionStatus.SATISFIED
                            elif is_auth and val_str in ["crashed", "failed", "terminated", "error"]:
                                return ConditionStatus.FAILED

                    for ent_name, ent_entry in verified_entity_states.items():
                        if cls.matches_canonical_entity(ent, ent_name):
                            # Use the detailed entity record from verified_entity_details;
                            # do NOT fabricate provenance for primitive entity states.
                            ent_detail = None
                            if verified_entity_details and ent_name in verified_entity_details:
                                ent_detail = verified_entity_details[ent_name]
                            elif isinstance(ent_entry, dict):
                                ent_detail = ent_entry
                            if ent_detail is None:
                                # Primitive entity state without provenance — cannot verify
                                continue
                            is_auth, st_val = cls.is_direct_provenance_evidence(ent_detail, allowed_types=["direct", "environmental"])
                            st_clean = str(st_val).lower().strip()
                            if is_auth and st_clean in ["running", "active"]:
                                return ConditionStatus.SATISFIED
                            elif is_auth and st_clean in ["crashed", "failed", "terminated"]:
                                return ConditionStatus.FAILED
                return ConditionStatus.UNKNOWN
            else:
                for k, obs_entry in observations_map.items():
                    is_auth, val = cls.is_direct_provenance_evidence(obs_entry, allowed_types=["direct", "environmental"])
                    val_str = str(val).lower().strip()
                    if is_auth and val_str in ["running", "active"]:
                        return ConditionStatus.SATISFIED
                    elif is_auth and val_str in ["crashed", "failed", "terminated", "error"]:
                        return ConditionStatus.FAILED
                return ConditionStatus.UNKNOWN

        # (c) File Path / Access Condition (Subject-Bound Verification)
        elif cond_type == GoalConditionType.ARTIFACT or any(k in sc_lower for k in ["file_path_identified", "file_accessed", "path_found"]):
            target_entities = [e.lower().strip() for e in goal_rep.entities] if goal_rep.entities else []
            if target_entities:
                for ent in target_entities:
                    for k, obs_entry in observations_map.items():
                        if cls.matches_canonical_entity(ent, k):
                            is_auth, val = cls.is_direct_provenance_evidence(obs_entry, allowed_types=["direct", "environmental"])
                            val_str = str(val).lower().strip()
                            if is_auth and val_str not in ["failed", "false", "none", "not_found", "error"]:
                                return ConditionStatus.SATISFIED
                            elif is_auth and val_str in ["not_found", "failed", "error"]:
                                return ConditionStatus.FAILED

                    fs_obs = observations_map.get("filesystem.file_path")
                    if fs_obs:
                        is_auth, val = cls.is_direct_provenance_evidence(fs_obs, allowed_types=["direct", "environmental"])
                        val_str = str(val).lower().strip()
                        if is_auth and val_str == "not_found":
                            return ConditionStatus.FAILED
                        elif is_auth and val_str not in ["failed", "false", "none", "error"]:
                            if cls.matches_canonical_entity(ent, val_str) or not target_entities:
                                return ConditionStatus.SATISFIED

                    for ent_name, ent_entry in verified_entity_states.items():
                        if cls.matches_canonical_entity(ent, ent_name):
                            # Use detailed entity record; do NOT fabricate provenance for primitives
                            ent_detail = None
                            if verified_entity_details and ent_name in verified_entity_details:
                                ent_detail = verified_entity_details[ent_name]
                            elif isinstance(ent_entry, dict):
                                ent_detail = ent_entry
                            if ent_detail is None:
                                continue
                            is_auth, st_val = cls.is_direct_provenance_evidence(ent_detail, allowed_types=["direct", "environmental"])
                            st_clean = str(st_val).lower().strip()
                            if is_auth and st_clean in ["identified", "found", "accessed"]:
                                return ConditionStatus.SATISFIED
                            elif is_auth and st_clean in ["not_found", "failed"]:
                                return ConditionStatus.FAILED
                return ConditionStatus.UNKNOWN
            else:
                obs_found = any(("file" in k or "path" in k or "filesystem" in k) and str(v).lower() not in ["failed", "false", "none", "not_found", "error"] for k, v in observations_map.items())
                if obs_found:
                    return ConditionStatus.SATISFIED
                obs_not_found = any(str(v).lower() == "not_found" for v in observations_map.values())
                if obs_not_found:
                    return ConditionStatus.FAILED
                return ConditionStatus.UNKNOWN

        # Other conditions (Web / Diagnostic / ADB / Screen Capture)
        else:
            cond_key = sc_lower.split("=")[0].strip() if "=" in sc_lower else sc_lower
            for k, obs_entry in observations_map.items():
                if cond_key in k.lower():
                    is_auth, val = cls.is_direct_provenance_evidence(obs_entry, allowed_types=["direct", "environmental", "self_reported"])
                    val_str = str(val).lower().strip()
                    if val_str in ["failed", "false", "error"]:
                        return ConditionStatus.FAILED
                    elif is_auth:
                        return ConditionStatus.SATISFIED
            return ConditionStatus.UNKNOWN

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
        Evaluates goal conditions directly against WorldModel observations and entities.
        """
        st = cls.evaluate_condition_status_against_world_model(
            succ_cond, goal_rep, observations_map, verified_entity_states, executed_actions, reply_clean, failed_conditions
        )
        return st == ConditionStatus.SATISFIED

    @classmethod
    def verify_goal_achievement(
        cls,
        goal_rep: SemanticGoalRepresentation,
        executed_actions: List[str],
        assistant_reply: str,
        failed_action_type: str = "",
        tracker: Optional[GoalTracker] = None,
        observed_state: Optional[Dict[str, Any]] = None,
        failed_payload: Optional[Dict[str, Any]] = None
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
        verified_entity_details = {}
        for ent in entities_list:
            if isinstance(ent, dict):
                ent_name = ent.get("name", "unknown")
                ent_status = ent.get("status", "unknown")
                verified_entity_states[ent_name] = ent_status
                verified_entity_details[ent_name] = ent
            elif isinstance(ent, str):
                verified_entity_states[ent] = "unknown"
                verified_entity_details[ent] = {
                    "status": "unknown",
                    "value": "unknown",
                    "source": "not_observed",
                    "observation_type": "direct",
                    "confidence": 0.0
                }

        # If entities_list empty, default entity states to unknown (requires WorldModel observation)
        if not verified_entity_states and goal_rep.entities:
            for ent_name in goal_rep.entities:
                verified_entity_states[ent_name] = "unknown"
                verified_entity_details[ent_name] = {
                    "status": "unknown",
                    "value": "unknown",
                    "source": "not_observed",
                    "observation_type": "direct",
                    "confidence": 0.0
                }

        met_conditions = []
        failed_conditions = []
        unknown_conditions = []

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

        # 2. Evaluate Success Conditions against Tri-State Evaluator (SATISFIED, FAILED, UNKNOWN)
        target_conditions = goal_rep.success_conditions or ["response_delivered = true"]

        for succ_cond in target_conditions:
            cond_st = cls.evaluate_condition_status_against_world_model(
                succ_cond,
                goal_rep,
                observations_map,
                verified_entity_states,
                executed_actions,
                reply_clean,
                failed_conditions,
                verified_entity_details=verified_entity_details
            )
            if cond_st == ConditionStatus.SATISFIED:
                met_conditions.append(succ_cond)
            elif cond_st == ConditionStatus.FAILED:
                failed_conditions.append(f"failed_condition: {succ_cond}")
            else:
                unknown_conditions.append(f"unverifiable_condition: {succ_cond}")

        # STRICT TRI-STATE SUCCESS EVALUATION:
        # 1. SATISFIED: Zero failed/unknown conditions AND all required conditions satisfied -> ACHIEVED
        # 2. UNKNOWN: Zero explicit failed conditions, but missing perception evidence (unknown_conditions > 0) -> is_unknown=True
        # 3. FAILED: Explicit environmental failure or missing observations -> FAILED
        required_success_count = len(target_conditions)
        verified_success = (len(failed_conditions) == 0) and (len(unknown_conditions) == 0) and (len(met_conditions) >= required_success_count)
        is_unknown = (len(unknown_conditions) > 0) and (len(failed_conditions) == 0) and not verified_success

        if verified_success:
            final_state = GoalLifecycleState.ACHIEVED
        elif is_unknown:
            # Conditions are UNKNOWN (missing perception evidence, no explicit failures)
            # Lifecycle reflects the epistemic state: waiting for evidence, not failed.
            final_state = GoalLifecycleState.WAITING_FOR_EVIDENCE
        elif any("blocked" in str(fc).lower() for fc in failed_conditions):
            final_state = GoalLifecycleState.BLOCKED
        else:
            final_state = GoalLifecycleState.FAILED

        reason = (
            f"Goal '{goal_rep.goal}' achieved: Satisfied all {len(met_conditions)}/{required_success_count} success conditions against actual world state."
            if verified_success
            else (
                f"Goal verification UNKNOWN: Missing perception evidence for {len(unknown_conditions)} condition(s): {unknown_conditions}"
                if is_unknown
                else f"Goal verification failed: Met {len(met_conditions)}/{required_success_count} success conditions. Failed conditions: {failed_conditions or ['Target environmental state failed.']}"
            )
        )

        if tracker:
            tracker.transition(final_state, reason)

        audit_logger.info(f"GoalVerifier [{goal_id[:8]}]: VerifiedSuccess={verified_success}, IsUnknown={is_unknown}, State={final_state.value}")

        # Construct actual_world_state payload - Clean separation of Evidence, ExecutionTrace, and Response
        actual_world_state = {
            "world_state": {
                "entities": entities_list if entities_list else [{"name": e, "status": verified_entity_states.get(e, "unknown")} for e in goal_rep.entities],
                "observations": observations_map if observations_map else {"status": "unknown", "evidence_source": "not_observed"},
                "verified_entity_states": verified_entity_states,
            },
            "execution_trace": {
                "executed_actions": executed_actions,
                "met_conditions_count": len(met_conditions),
                "required_conditions_count": required_success_count
            },
            "assistant_response": {
                "text": assistant_reply[:200]
            },
            # Top-level aliases for backward compatibility
            "entities": entities_list if entities_list else [{"name": e, "status": verified_entity_states.get(e, "unknown")} for e in goal_rep.entities],
            "observations": observations_map if observations_map else {"status": "unknown", "evidence_source": "not_observed"},
            "verified_entity_states": verified_entity_states,
            "executed_actions": executed_actions,
            "assistant_reply": assistant_reply[:200]
        }

        return GoalVerificationResult(
            goal_id=goal_id,
            verified_success=verified_success,
            final_state=final_state,
            verification_reason=reason,
            failed_action_type=failed_action_type or goal_rep.primary_intent_type,
            failed_payload=failed_payload or {},
            met_conditions=met_conditions,
            failed_conditions=failed_conditions,
            unknown_conditions=unknown_conditions,
            is_unknown=is_unknown,
            observed_state=actual_world_state
        )
