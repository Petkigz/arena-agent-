"""Goal Verification Engine."""

from __future__ import annotations
import re
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.condition_language import (
    AnswerContainsVerifiedValue,
    FlagCondition,
    ObservationEnvironment,
    ObservedValue,
    ResponseDelivered,
    Verdict,
    parse_condition,
)
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
    ANSWER_CONTENT = "answer_content"  # The reply's CONTENT must state a computed/derivable answer value

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

class _ProvenanceEnv(ObservationEnvironment):
    """Observation queries answered from the world model, with the
    GoalVerifier's provenance enforcement: every environmental fact must
    carry authorized provenance — self-reported claims cannot satisfy
    environmental conditions. Resolvers return typed ObservedValues (or
    None when nothing was observed); the AST nodes decide the verdict.
    """

    def __init__(self, verifier, cond_type, target_entities, observations_map,
                 verified_entity_states, verified_entity_details, reply_clean,
                 deterministic_answers=None):
        self.verifier = verifier
        self.cond_type = cond_type
        self.target_entities = target_entities
        self.observations_map = observations_map or {}
        self.verified_entity_states = verified_entity_states or {}
        self.verified_entity_details = verified_entity_details or {}
        self.reply_clean = reply_clean or ""
        self.deterministic_answers = list(deterministic_answers or [])

    # -- response delivery: the reply is the deliverable ---------------------
    def response_delivered(self):
        return bool(self.reply_clean.strip())

    # -- answer content: values the system computed deterministically -------
    def verified_answer_values(self):
        return [
            a.get("value")
            for a in self.deterministic_answers
            if isinstance(a, dict) and a.get("value") is not None
        ]

    def response_text(self):
        return self.reply_clean

    # -- flags / named conditions, routed by condition type ------------------
    def flag(self, name: str):
        if self.cond_type == GoalConditionType.ENVIRONMENT:
            return self._resolve_process_state()
        if self.cond_type == GoalConditionType.ARTIFACT:
            return self._resolve_artifact_state()
        return self._resolve_named_observation(name)

    def _resolve_process_state(self):
        """Subject-bound process/window state with DIRECT provenance."""
        candidates = self.target_entities or [""]
        for ent in candidates:
            for k, obs_entry in self.observations_map.items():
                if ent and not self.verifier.matches_canonical_entity(ent, k):
                    continue
                is_auth, val = self.verifier.is_direct_provenance_evidence(
                    obs_entry, allowed_types=["direct", "environmental"])
                val_str = str(val).lower().strip()
                # Primitive/unprovenanced values are NOT evidence — skip them
                # and keep looking; only authorized values may decide.
                if is_auth and val_str in ("running", "active"):
                    return ObservedValue(val_str, "state", True, source=k)
                if is_auth and val_str in ("crashed", "failed", "terminated", "error"):
                    return ObservedValue(val_str, "state", True, source=k)
            for ent_name, ent_entry in self.verified_entity_states.items():
                if ent and not self.verifier.matches_canonical_entity(ent, ent_name):
                    continue
                ent_detail = self.verified_entity_details.get(ent_name) \
                    if isinstance(self.verified_entity_details, dict) else None
                if ent_detail is None and isinstance(ent_entry, dict):
                    ent_detail = ent_entry
                if ent_detail is None:
                    # Primitive entity state without provenance — cannot verify
                    continue
                is_auth, st_val = self.verifier.is_direct_provenance_evidence(
                    ent_detail, allowed_types=["direct", "environmental"])
                st_clean = str(st_val).lower().strip()
                if is_auth and st_clean in ("running", "active"):
                    return ObservedValue(st_clean, "state", True, source=ent_name)
                if is_auth and st_clean in ("crashed", "failed", "terminated"):
                    return ObservedValue(st_clean, "state", True, source=ent_name)
        return None

    def _resolve_artifact_state(self):
        """Subject-bound file/path/artifact state with DIRECT provenance."""
        candidates = self.target_entities or [""]
        for ent in candidates:
            for k, obs_entry in self.observations_map.items():
                if ent and not self.verifier.matches_canonical_entity(ent, k):
                    continue
                is_auth, val = self.verifier.is_direct_provenance_evidence(
                    obs_entry, allowed_types=["direct", "environmental"])
                val_str = str(val).lower().strip()
                # Only authorized observations may decide (primitives cannot).
                if is_auth and val_str in ("not_found", "failed", "error"):
                    return ObservedValue(val_str, "state", True, source=k)
                if is_auth and val_str not in ("failed", "false", "none", "not_found", "error"):
                    return ObservedValue(val_str, "state", True, source=k)
            fs_obs = self.observations_map.get("filesystem.file_path")
            if fs_obs:
                is_auth, val = self.verifier.is_direct_provenance_evidence(
                    fs_obs, allowed_types=["direct", "environmental"])
                val_str = str(val).lower().strip()
                # Only authorized filesystem observations may decide; a
                # primitive 'not_found' string is not structured evidence.
                if is_auth and val_str == "not_found":
                    return ObservedValue(val_str, "state", True, source="filesystem.file_path")
                if is_auth and val_str not in ("failed", "false", "none", "error"):
                    if not ent or self.verifier.matches_canonical_entity(ent, val_str):
                        return ObservedValue(val_str, "state", True, source="filesystem.file_path")
            for ent_name, ent_entry in self.verified_entity_states.items():
                if ent and not self.verifier.matches_canonical_entity(ent, ent_name):
                    continue
                ent_detail = self.verified_entity_details.get(ent_name) \
                    if isinstance(self.verified_entity_details, dict) else None
                if ent_detail is None and isinstance(ent_entry, dict):
                    ent_detail = ent_entry
                if ent_detail is None:
                    continue
                is_auth, st_val = self.verifier.is_direct_provenance_evidence(
                    ent_detail, allowed_types=["direct", "environmental"])
                st_clean = str(st_val).lower().strip()
                if is_auth and st_clean in ("not_found", "failed"):
                    return ObservedValue(st_clean, "state", True, source=ent_name)
                if is_auth and st_clean in ("identified", "found", "accessed"):
                    return ObservedValue(st_clean, "state", True, source=ent_name)
        if not self.target_entities:
            obs_found = any(("file" in k or "path" in k or "filesystem" in k)
                            and str(v).lower() not in ("failed", "false", "none", "not_found", "error")
                            for k, v in self.observations_map.items())
            if obs_found:
                return ObservedValue("found", "state", True, source="filesystem observation")
            for k, v in self.observations_map.items():
                if str(v).lower() == "not_found":
                    return ObservedValue("not_found", "state", True, source=k)
        return None

    def _resolve_named_observation(self, name: str):
        """Fallback resolution: subject key containment over the observation
        map (self_reported is accepted here per the historical channel mix)."""
        cond_key = (name or "").lower().split("=")[0].strip()
        for k, obs_entry in self.observations_map.items():
            if cond_key and cond_key in k.lower():
                is_auth, val = self.verifier.is_direct_provenance_evidence(
                    obs_entry, allowed_types=["direct", "environmental", "self_reported"])
                val_str = str(val).lower().strip()
                if val_str in ("failed", "false", "error"):
                    return ObservedValue(val_str, "state", is_auth, source=k)
                if is_auth:
                    return ObservedValue(val_str, "state", True, source=k)
        return None

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

        # F3c (D1/D2/D6): answer-content conditions are about WHAT the
        # reply states, not that a reply exists.
        if "computed_answer_in_reply" in sc_lower or "answer_value_in_reply" in sc_lower:
            return GoalConditionType.ANSWER_CONTENT

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

    # D6: capability names come from the request's own words —
    # 'tool called reverse_words'. Not used for anything else; a request
    # that names no capability cannot be probed (honest UNKNOWN).
    _CALLED_NAME_RE = re.compile(
        r"\b(?:called|named)\s+['\"]?([a-z_][a-z0-9_]{1,60})",
        re.IGNORECASE,
    )

    @classmethod
    def _probe_capability_installation(
        cls, succ_cond: str, goal_rep: SemanticGoalRepresentation
    ) -> Optional[ConditionStatus]:
        """Registry probe for capability conditions (D6 hard condition).

        capability_installed: SATISFIED iff the shared registry has the
        named capability; FAILED when the probe ran and found nothing
        (absence is direct evidence — the registry is the authority for
        installation).

        capability_executes_correctly: FAILED when not installed;
        SATISFIED when a SELF-EVOLVED entry (runtime install or plugin
        category) smoke-executes with success=True; None (UNKNOWN)
        otherwise — semantic correctness needs ground truth the runtime
        does not have.

        Returns None when no capability name is extractable (nothing to
        probe — never guess a name).
        """
        cond_lower = str(succ_cond or "").lower()
        goal_text = " ".join(
            str(getattr(goal_rep, "goal", "") or "").split())
        m = cls._CALLED_NAME_RE.search(goal_text)
        if not m:
            return None
        name = m.group(1).lower()
        try:
            from app.cognition.tool_registry import get_shared_registry
            registry = get_shared_registry()
            entry = registry.effective_capability(name)
        except Exception:
            return None
        installed = entry is not None
        if "capability_installed" in cond_lower:
            audit_logger.info(
                f"Capability registry probe '{name}': "
                f"{'installed' if installed else 'NOT installed'}")
            return (ConditionStatus.SATISFIED if installed
                    else ConditionStatus.FAILED)
        if "capability_executes_correctly" in cond_lower:
            if not installed:
                return ConditionStatus.FAILED
            source = str(entry.get("source") or "")
            category = str(entry.get("category") or "")
            # Smoke-execute ONLY self-evolved entries (runtime installs
            # and discovered plugins) — they carry the sandbox-verified
            # execute_tool contract and were tested before install.
            # Built-in tools are never executed as a verification side
            # effect.
            if source != "runtime_install" and category != "plugin":
                return None
            try:
                res = registry.execute_registered_tool(name, {}) or {}
                ok = bool(res.get("success"))
            except Exception:
                ok = False
            audit_logger.info(
                f"Capability smoke execution '{name}': success={ok}")
            return (ConditionStatus.SATISFIED if ok
                    else ConditionStatus.FAILED)
        return None

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
        verified_entity_details: Optional[Dict[str, Any]] = None,
        deterministic_answers: Optional[List[Dict[str, Any]]] = None
    ) -> ConditionStatus:
        """
        Phase E Tri-State Condition Evaluator:
        Evaluates conditions into explicit SATISFIED, FAILED, or UNKNOWN states.
        Differentiates explicit environmental failure from missing perception evidence (UNKNOWN).
        """
        sc_lower = succ_cond.lower().strip()
        actions_str = " ".join(executed_actions).lower()
        reply_lower = reply_clean.lower()

        # D6 (live 2026-09-01, owner review item 4): installation is a
        # HARD success condition. The shared ToolRegistry is the
        # authority: a nameable capability that is NOT registered is
        # direct evidence of non-installation — a reply claiming
        # 'Successfully created X' can never verify the goal, and
        # 'waiting for evidence' is not honest once the authoritative
        # probe ran and found nothing. No name to probe -> fall through
        # (UNKNOWN via the normal path).
        if ("capability_installed" in sc_lower
                or "capability_executes_correctly" in sc_lower):
            probed = cls._probe_capability_installation(succ_cond, goal_rep)
            if probed is not None:
                return probed

        has_crash_or_err = len(failed_conditions) > 0 or any(k in reply_lower or k in actions_str for k in ["crash", "crashed", "failed", "error", "cannot find"])

        if has_crash_or_err:
            return ConditionStatus.FAILED

        # P0 review #9: conditions go through the typed condition language —
        # Condition AST -> observation query -> typed value -> predicate ->
        # PASS / FAIL / UNKNOWN. The keyword-dispatch heuristics are gone;
        # the provenance enforcement lives in the environment's resolvers,
        # and the acceptance logic lives in the AST nodes.
        cond_type = cls.classify_condition_type(succ_cond, goal_rep.primary_intent_type, goal_rep.target_domain)
        cond_key = sc_lower.split("=")[0].strip() if "=" in sc_lower else sc_lower

        node = parse_condition(succ_cond)
        if cond_type == GoalConditionType.ANSWER_CONTENT:
            node = AnswerContainsVerifiedValue()
        elif cond_type == GoalConditionType.RESPONSE or "response_delivered" in sc_lower or "answer_provided" in sc_lower:
            # The reply IS the deliverable; its existence is directly observable.
            node = ResponseDelivered()
        elif not isinstance(node, FlagCondition):
            # Free-form goal condition: resolve it as a named flag query
            # (subject-bound containment over the observation map).
            node = FlagCondition(name=cond_key or sc_lower)

        # Type-specific acceptance sets (the predicate, typed):
        if isinstance(node, FlagCondition):
            if cond_type == GoalConditionType.ENVIRONMENT or any(k in sc_lower for k in ["app_process_running", "process_running", "window_active", "status = running"]):
                node.satisfied_by = ("running", "active")
                node.refuted_by = ("crashed", "failed", "terminated", "error")
                node.mode = "membership"
            elif cond_type == GoalConditionType.ARTIFACT:
                node.refuted_by = ("failed", "false", "none", "not_found", "error")
                node.mode = "not_refuted"
            else:
                node.refuted_by = ("failed", "false", "error")
                node.mode = "not_refuted"

        env = _ProvenanceEnv(
            verifier=cls,
            cond_type=cond_type,
            target_entities=[e.lower().strip() for e in goal_rep.entities] if goal_rep.entities else [],
            observations_map=observations_map,
            verified_entity_states=verified_entity_states,
            verified_entity_details=verified_entity_details,
            reply_clean=reply_clean,
            deterministic_answers=deterministic_answers,
        )
        verdict: Verdict = node.evaluate(env)
        if verdict.status == "pass":
            return ConditionStatus.SATISFIED
        if verdict.status == "fail":
            return ConditionStatus.FAILED
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

        # General error/crash detection — includes the OS-level failure
        # patterns that actually appear in subprocess output (live bug:
        # Windows printed 'The system cannot find the file' but the
        # verifier checked only the friendly action description).
        error_indicators = [
            "crashed", "fatal error", "unhandled exception", "permission denied",
            "timed out", "process exited unexpectedly",
            "cannot find the file", "the system cannot find", "not recognized as",
            "no such file or directory", "is not recognized",
            "failed to launch", "launch failed", "could not find",
            "refused", "looks like a sentence",
        ]
        for err_ind in error_indicators:
            if err_ind in reply_lower or err_ind in actions_str:
                if f"error_detected:{err_ind}" not in failed_conditions:
                    failed_conditions.append(f"Environmental error detected: {err_ind}")

        # CRITICAL: a tool reporting success=False or refused=True in its
        # own result must NEVER verify as achieved, regardless of what the
        # friendly action text says (live bug: 'Successfully launched' was
        # recorded when the subprocess actually failed).
        if any(k in reply_lower or k in actions_str for k in (
            '"success": false', "'success': false", "success: false",
            "refused", "looks like a sentence",
        )):
            failed_conditions.append("Tool reported failure or refusal in its result")

        # 2. Evaluate Success Conditions against Tri-State Evaluator (SATISFIED, FAILED, UNKNOWN)
        target_conditions = goal_rep.success_conditions or ["response_delivered = true"]

        # F3c (D1/D2/D6): deterministic computations recorded by the
        # runtime are GROUND TRUTH for what the reply must state.
        deterministic_answers = [
            a for a in (obs_dict.get("deterministic_answers") or [])
            if isinstance(a, dict)
        ]

        for succ_cond in target_conditions:
            cond_st = cls.evaluate_condition_status_against_world_model(
                succ_cond,
                goal_rep,
                observations_map,
                verified_entity_states,
                executed_actions,
                reply_clean,
                failed_conditions,
                verified_entity_details=verified_entity_details,
                deterministic_answers=deterministic_answers,
            )
            if cond_st == ConditionStatus.SATISFIED:
                met_conditions.append(succ_cond)
            elif cond_st == ConditionStatus.FAILED:
                failed_conditions.append(f"failed_condition: {succ_cond}")
            else:
                unknown_conditions.append(f"unverifiable_condition: {succ_cond}")

        # F3c unconditional ground-truth check: this runs REGARDLESS of
        # what the goal representation's conditions say. Live incident D1:
        # the runtime computed 17*24=408 deterministically, the model
        # replied 396, and 'response_delivered' verified the goal as
        # achieved. A recorded deterministic answer that the reply does
        # not state means the answer was NOT delivered — a failed
        # condition in its own right, with the ground truth named.
        if deterministic_answers:
            # Lazy import: keep the verifier's import graph free of the
            # tools layer at module load; the calculator owns the
            # numeric-match semantics (thousands separators, tolerance).
            from app.tools.calculator import DeterministicCalculator
            for ans in deterministic_answers:
                if ans.get("value") is None:
                    continue
                if not DeterministicCalculator.reply_mentions_value(
                        reply_clean, ans.get("value")):
                    failed_conditions.append(
                        f"Deterministic answer missing from reply: "
                        f"{ans.get('expression', '?')} = "
                        f"{ans.get('value_str', ans.get('value'))} "
                        f"(computed deterministically; the reply must state this value)"
                    )

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
