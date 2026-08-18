"""Semantic Goal & Intent Representation Layer (Goal Representation v2)."""

from __future__ import annotations
import re
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.utils.logger import app_logger

@dataclass
class SemanticGoalSchemaValidationResult:
    is_valid: bool
    data: Dict[str, Any] = field(default_factory=dict)
    validation_error: Optional[str] = None

@dataclass
class SemanticGoalRepresentation:
    user_query: str
    primary_intent_type: str        # 'action_intent', 'information_need', 'knowledge_query'
    target_domain: str              # 'desktop_os', 'filesystem', 'web_research', 'mobile_phone', 'vision_desktop', 'conversation', 'diagnostic'
    goal: str                       # Actionable core objective (e.g. "locate project")
    desired_outcome: str            # Target state (e.g. "project path identified")
    entities: List[str]             # Extracted key entities/nouns (e.g. ["project", "chrome"])
    constraints: List[str]          # Safety/operational constraints (e.g. ["read_only"])
    assumptions: List[str]          # Inferred assumptions (e.g. ["refers to default browser"])
    unknowns: List[str]             # Information gaps/missing facts (e.g. ["file location"])
    preconditions: List[str]        # Required prior states (e.g. ["application installed"])
    success_conditions: List[str]   # Criteria verifying success (e.g. ["process_running = true"])
    failure_conditions: List[str]   # Criteria indicating failure (e.g. ["exit code != 0"])
    required_capabilities: List[str]# Capabilities needed (e.g. ["filesystem.search"])
    risk_factors: List[str]         # Potential risks (e.g. ["data modification"])
    recommended_candidates: List[Dict[str, Any]] = field(default_factory=list) # Candidate strategy branches
    confidence: float = 0.95        # Epistemic confidence score (0.0 to 1.0)
    provenance_source: str = "inferred_from_user"
    parsed_goal_summary: str = ""   # Legacy string summary for backward compatibility

class SemanticGoalInterpreter:
    """
    Goal Representation v2 Layer.
    Parses user queries into rich SemanticGoalRepresentation v2 objects carrying
    goals, desired outcomes, entities, constraints, assumptions, unknowns,
    success conditions, required capabilities, and candidate strategies.
    """

    VALID_INTENTS = {"action_intent", "information_need", "knowledge_query"}
    VALID_DOMAINS = {"desktop_os", "filesystem", "web_research", "mobile_phone", "vision_desktop", "diagnostic", "conversation"}

    @classmethod
    def validate_schema(cls, parsed_json: Any) -> SemanticGoalSchemaValidationResult:
        """
        P1 Fix: Validates parsed LLM JSON against the strict Goal Representation v2 schema contract.
        Explicitly validates intent, domain, entities, conditions, capabilities, and risks.
        Rejects malformed semantic representations if required fields or types are invalid.
        """
        if not isinstance(parsed_json, dict):
            return SemanticGoalSchemaValidationResult(
                is_valid=False,
                data={},
                validation_error="Payload is not a dictionary object"
            )

        errors = []

        # 1. Validate intent type
        raw_intent = parsed_json.get("primary_intent_type")
        if not raw_intent or not isinstance(raw_intent, str):
            errors.append("Missing or non-string 'primary_intent_type'")
        else:
            clean_intent = raw_intent.lower().strip()
            if clean_intent not in cls.VALID_INTENTS:
                errors.append(f"Invalid 'primary_intent_type' '{raw_intent}'. Must be one of {cls.VALID_INTENTS}")

        # 2. Validate target domain
        raw_domain = parsed_json.get("target_domain")
        if not raw_domain or not isinstance(raw_domain, str):
            errors.append("Missing or non-string 'target_domain'")
        else:
            clean_domain = raw_domain.lower().strip()
            if clean_domain not in cls.VALID_DOMAINS:
                errors.append(f"Invalid 'target_domain' '{raw_domain}'. Must be one of {cls.VALID_DOMAINS}")

        # 3. Validate goal & desired outcome
        goal = parsed_json.get("goal")
        if not goal or not isinstance(goal, str) or not goal.strip():
            errors.append("Missing or empty string field 'goal'")

        outcome = parsed_json.get("desired_outcome")
        if not outcome or not isinstance(outcome, str) or not outcome.strip():
            errors.append("Missing or empty string field 'desired_outcome'")

        # 4. Validate array fields: entities, conditions, capabilities, risks, constraints, etc.
        LIST_FIELDS = [
            "entities", "constraints", "assumptions", "unknowns",
            "preconditions", "success_conditions", "failure_conditions",
            "required_capabilities", "risk_factors"
        ]
        validated_lists = {}
        for field_name in LIST_FIELDS:
            val = parsed_json.get(field_name)
            if val is not None and not isinstance(val, list):
                errors.append(f"Field '{field_name}' must be a list of strings, got {type(val).__name__}")
            elif isinstance(val, list):
                if not all(isinstance(item, str) for item in val):
                    errors.append(f"All elements in '{field_name}' must be strings")
                else:
                    validated_lists[field_name] = val
            else:
                validated_lists[field_name] = []

        if errors:
            return SemanticGoalSchemaValidationResult(
                is_valid=False,
                data={},
                validation_error="; ".join(errors)
            )

        clean_data = {
            "primary_intent_type": parsed_json["primary_intent_type"].lower().strip(),
            "target_domain": parsed_json["target_domain"].lower().strip(),
            "goal": parsed_json["goal"].strip(),
            "desired_outcome": parsed_json["desired_outcome"].strip(),
            **validated_lists
        }

        return SemanticGoalSchemaValidationResult(is_valid=True, data=clean_data)

    @classmethod
    def extract_json_object(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Robust JSON object extractor that handles markdown codeblocks, nested JSON objects,
        Windows file path backslashes, and braces inside strings without regex limitations.
        """
        if not text:
            return None

        clean_text = text.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0].strip()

        def sanitize_json_str(s: str) -> str:
            return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)

        # 1. Attempt direct parse
        for candidate in [clean_text, sanitize_json_str(clean_text)]:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # 2. Extract between first '{' and last '}'
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")

        if start_idx != -1 and end_idx > start_idx:
            candidate = clean_text[start_idx:end_idx + 1]
            for c_str in [candidate, sanitize_json_str(candidate)]:
                try:
                    data = json.loads(c_str)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass

        return None

    @classmethod
    def normalize_and_validate(cls, intent_type: str, domain: str) -> tuple[str, str]:
        clean_intent = str(intent_type).lower().strip()
        clean_domain = str(domain).lower().strip()

        if clean_intent not in cls.VALID_INTENTS:
            if any(k in clean_intent for k in ["act", "task", "open", "run", "launch"]):
                clean_intent = "action_intent"
            elif any(k in clean_intent for k in ["investigate", "info", "search", "check"]):
                clean_intent = "information_need"
            else:
                clean_intent = "knowledge_query"

        if clean_domain not in cls.VALID_DOMAINS:
            if clean_intent == "action_intent":
                clean_domain = "desktop_os"
            elif clean_intent == "information_need":
                clean_domain = "diagnostic"
            else:
                clean_domain = "conversation"

        return clean_intent, clean_domain

    @classmethod
    def build_candidates_for_domain(cls, domain: str, user_text: str) -> List[Dict[str, Any]]:
        domain_clean = domain.lower().strip()
        candidates = []
        if domain_clean == "diagnostic":
            candidates.append({"name": "Diagnostic Investigation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}})
            candidates.append({"name": "Filesystem Search Probe", "action_type": "search_files", "payload": {"query": user_text, "action_type": "search_files"}})
        elif domain_clean == "mobile_phone":
            candidates.append({"name": "Android ADB Phone Command", "action_type": "phone_command", "payload": {"query": user_text, "action_type": "phone_command"}})
        elif domain_clean == "web_research":
            candidates.append({"name": "Web Search & Browser Research", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
        elif domain_clean == "filesystem":
            candidates.append({"name": "Local Filesystem Search", "action_type": "search_files", "payload": {"query": user_text, "action_type": "search_files"}})
            candidates.append({"name": "Web Research Fallback", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
        elif domain_clean == "vision_desktop":
            candidates.append({"name": "Desktop Screen Capture & Vision", "action_type": "screen_capture", "payload": {"query": user_text, "action_type": "screen_capture"}})
        elif domain_clean == "desktop_os":
            candidates.append({"name": "Desktop Application Launch", "action_type": "open_application", "payload": {"query": user_text, "action_type": "open_application"}})
            candidates.append({"name": "Web Browser Fallback Search", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
        else:
            candidates.append({"name": "Direct Conversational Answer", "action_type": "formulate_answer", "payload": {"query": user_text, "action_type": "formulate_answer"}})
        return candidates

    @classmethod
    def synthesize_candidates_from_context(
        cls,
        domain: str,
        user_text: str,
        goal_rep: Optional[SemanticGoalRepresentation] = None,
        memory_store: Optional[Any] = None,
        world_model: Optional[Any] = None,
        tool_registry: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes candidate execution strategies by combining:
        1. Domain baseline strategy branches
        2. System capabilities registered in WorldModel / ToolRegistry (if world_model supplied)
        3. MemoryStore reflections and past learned lessons for similar queries (if memory_store supplied)

        Note: Does NOT instantiate fallback MemoryStore() or WorldModel() instances when
        context is not provided, preventing uncoordinated cognitive store creation.
        """
        domain_clean = domain.lower().strip()
        candidates: List[Dict[str, Any]] = []

        # 1. Base domain candidate strategies
        candidates.extend(cls.build_candidates_for_domain(domain_clean, user_text))

        # 2. Ingest learned strategy lessons from MemoryStore if explicitly supplied
        if memory_store is not None:
            try:
                past_memories = memory_store.search(user_text, limit=3)
                for mem in past_memories:
                    if hasattr(mem, "content") and any(k in str(mem.content).lower() for k in ["strategy", "used", "worked", "lesson"]):
                        candidates.append({
                            "name": f"Memory Learned Strategy ({str(mem.task_id or 'past')[:6]})",
                            "action_type": "investigate" if "investigat" in str(mem.content).lower() else "web_search",
                            "payload": {"query": user_text, "memory_lesson": str(mem.content)[:100]},
                            "source": "memory_store"
                        })
            except Exception as e:
                app_logger.warning(f"Memory candidate synthesis note: {e}")

        # 3. Inspect WorldModel capability graph for active, EXECUTABLE capabilities if explicitly supplied
        if world_model is not None:
            try:
                if tool_registry is not None:
                    executable_tools = set(tool_registry._registry.keys())
                else:
                    from app.cognition.tool_registry import ToolRegistry
                    executable_tools = set(ToolRegistry()._registry.keys())

                NATIVE_EXECUTABLE_CAPS = {
                    "open_application", "launch_app", "web_search", "search_files",
                    "phone_command", "make_phone_call", "send_sms", "screen_capture",
                    "opsec_audit", "daily_briefing", "investigate", "diagnostic",
                    "formulate_answer", "answer", "workflow_execute"
                }

                active_caps = world_model.find_entities(entity_type="capability")
                for cap in active_caps[:5]:
                    cap_name = cap.name.lower().replace(" ", "_")
                    # EXECUTABILITY VERIFICATION: Ensure capability has an active handler before synthesizing candidate
                    is_executable = (cap_name in executable_tools) or (cap_name in NATIVE_EXECUTABLE_CAPS) or any(ec in cap_name for ec in NATIVE_EXECUTABLE_CAPS)
                    if is_executable:
                        if cap_name not in [c.get("action_type") for c in candidates]:
                            candidates.append({
                                "name": f"Dynamic Capability: {cap.name}",
                                "action_type": cap_name,
                                "payload": {"query": user_text, "action_type": cap_name},
                                "source": "world_model_capability"
                            })
                    else:
                        app_logger.warning(f"CandidateSynthesizer: Skipping non-executable capability entity '{cap.name}'")
            except Exception as e:
                app_logger.warning(f"WorldModel capability candidate synthesis note: {e}")

        # Ensure candidates are unique
        seen_keys = set()
        unique_candidates = []
        for c in candidates:
            key = (c.get("action_type"), c.get("name"))
            if key not in seen_keys:
                seen_keys.add(key)
                unique_candidates.append(c)

        return unique_candidates

    @classmethod
    def interpret_goal(
        cls,
        user_text: str,
        complexity: str = "fast",
        memory_store: Optional[Any] = None,
        world_model: Optional[Any] = None,
        tool_registry: Optional[Any] = None
    ) -> SemanticGoalRepresentation:
        text_lower = user_text.lower().strip()

        # Fast Heuristic Baseline
        intent_type = "knowledge_query"
        domain = "conversation"
        goal = f"Respond to user query: '{user_text[:60]}'"
        outcome = "User receives helpful direct response"
        entities = [w for w in user_text.split() if len(w) > 3 and w.lower() not in ["what", "where", "when", "how", "with", "this"]]
        constraints = ["read_only_safe", "no_destructive_actions"]
        assumptions = ["user expects concise human response"]
        unknowns = []
        preconditions = ["system active"]
        success_conditions = ["response_delivered = true"]
        failure_conditions = ["response_empty = true"]
        req_caps = ["llm.generate"]
        risks = ["low"]

        # 1. Diagnostic, Research & Information Gathering queries FIRST
        if any(k in text_lower for k in ["why ", "how come", "find out", "find whether", "find if", "check if", "investigate", "where is", "does file", "error", "crash", "failed", "won't open", "can't open"]):
            intent_type = "information_need"
            domain = "diagnostic"
            goal = f"Investigate cause or evidence for: '{user_text[:60]}'"
            outcome = "Diagnostic evidence gathered and reported"
            unknowns = ["underlying error cause", "evidence availability"]
            req_caps = ["filesystem.search", "system.probe"]

        # 2. Operational Action Commands SECOND
        elif any(k in text_lower for k in ["open", "launch", "start", "run", "search", "call", "sms", "photo", "screenshot", "briefing", "play", "find"]):
            intent_type = "action_intent"
            if "phone" in text_lower or "mobile" in text_lower or "call" in text_lower or "sms" in text_lower or "battery" in text_lower or "charged" in text_lower:
                domain = "mobile_phone"
                goal = f"Execute mobile phone operation: '{user_text[:60]}'"
                outcome = "Mobile phone action completed via ADB"
                req_caps = ["phone.adb", "phone.control"]
            elif "youtube" in text_lower or "google" in text_lower or "search web" in text_lower:
                domain = "web_research"
                goal = f"Perform web search or research: '{user_text[:60]}'"
                outcome = "Web search results retrieved"
                req_caps = ["browser.open", "web.search"]
            elif "find" in text_lower or "file" in text_lower or "ordinary" in text_lower or "document" in text_lower or "song" in text_lower:
                domain = "filesystem"
                goal = f"Locate or inspect local file: '{user_text[:60]}'"
                outcome = "Matching file path identified"
                req_caps = ["filesystem.search", "filesystem.read"]
            elif "screenshot" in text_lower or "screen" in text_lower:
                domain = "vision_desktop"
                goal = f"Capture and analyze active screen window"
                outcome = "Desktop screen capture saved and analyzed"
                req_caps = ["screen.capture", "vision.analyze"]
            else:
                domain = "desktop_os"
                goal = f"Launch or operate desktop application: '{user_text[:60]}'"
                outcome = "Desktop application process running"
                req_caps = ["os.launch_app"]

        intent_type, domain = cls.normalize_and_validate(intent_type, domain)

        # Collision & Ambiguity Detection:
        # Unambiguous action verbs with explicit operational targets (e.g. open, launch) yield high confidence.
        # Ambiguous collision verbs (e.g. find, check, search) or baseline queries flag is_ambiguous=True.
        UNAMBIGUOUS_ACTION_VERBS = {"open", "launch", "start", "run", "call", "sms", "screenshot"}
        AMBIGUOUS_COLLISION_VERBS = {"find", "check", "search", "look", "get", "inspect", "where"}

        words = text_lower.split()
        first_word = words[0] if words else ""

        is_unambiguous_action = (
            first_word in UNAMBIGUOUS_ACTION_VERBS or
            any(text_lower.startswith(v + " ") for v in UNAMBIGUOUS_ACTION_VERBS)
        )

        is_ambiguous_collision = (
            first_word in AMBIGUOUS_COLLISION_VERBS or
            any(f" {v} " in f" {text_lower} " or text_lower.startswith(v + " ") for v in AMBIGUOUS_COLLISION_VERBS)
        )

        if is_unambiguous_action and not is_ambiguous_collision:
            confidence = 0.90
            provenance = "clear_deterministic_keyword_intent"
            is_ambiguous = False
        elif is_ambiguous_collision:
            confidence = 0.60
            provenance = "ambiguous_keyword_collision"
            is_ambiguous = True
        else:
            confidence = 0.55
            provenance = "heuristic_baseline"
            is_ambiguous = True

        heuristic_intent = intent_type
        heuristic_domain = domain

        # Domain-specific heuristic assignments for semantic attributes
        if domain == "desktop_os":
            constraints = ["user_session_active", "no_unauthorized_deletion"]
            assumptions = ["application installed on host PC"]
            preconditions = ["os_gui_running"]
            success_conditions = ["app_process_running = true"]
            failure_conditions = ["process_crashed = true", "launch_failed = true"]
            risks = ["unwanted_process_execution"]
        elif domain == "filesystem":
            constraints = ["workspace_boundary_enforced", "read_only_default"]
            assumptions = ["file resides in local storage"]
            preconditions = ["storage_mounted"]
            success_conditions = ["file_path_identified = true"]
            failure_conditions = ["file_not_found = true"]
            risks = ["unintended_file_modification"]
        elif domain == "web_research":
            constraints = ["network_timeout_10s", "no_paid_apis"]
            assumptions = ["local_wifi_or_internet_connected"]
            preconditions = ["network_available"]
            success_conditions = ["search_results_retrieved = true"]
            failure_conditions = ["network_error = true", "no_results_found = true"]
            risks = ["untrusted_web_content"]
        elif domain == "mobile_phone":
            constraints = ["adb_authorized", "no_remote_wiping"]
            assumptions = ["phone_connected_via_usb_or_wifi"]
            preconditions = ["adb_daemon_listening"]
            success_conditions = ["adb_command_succeeded = true"]
            failure_conditions = ["adb_device_offline = true"]
            risks = ["cellular_data_or_call_cost"]
        elif domain == "vision_desktop":
            constraints = ["screen_privacy_boundary", "no_credential_leak"]
            assumptions = ["desktop_display_active"]
            preconditions = ["screen_capture_permission_granted"]
            success_conditions = ["screen_capture_saved = true"]
            failure_conditions = ["screen_capture_failed = true"]
            risks = ["sensitive_screen_data"]
        elif domain == "diagnostic":
            constraints = ["read_only_investigation", "bounded_probe_steps"]
            assumptions = ["system_logs_or_probes_accessible"]
            preconditions = ["diagnostic_tools_registered"]
            success_conditions = ["diagnostic_evidence_gathered = true"]
            failure_conditions = ["evidence_unavailable = true"]
            risks = ["misdiagnosed_root_cause"]
        else:
            constraints = ["read_only_safe", "no_destructive_actions"]
            assumptions = ["user expects concise human response"]
            preconditions = ["system active"]
            success_conditions = ["response_delivered = true"]
            failure_conditions = ["response_empty = true"]
            risks = ["low"]

        # Deeper Semantic Interpretation Path:
        # Triggered when explicitly requested (complexity in ["main", "deep"]) OR when fast heuristics detect ambiguity/collisions (is_ambiguous)
        if complexity in ["main", "deep"] or is_ambiguous:
            try:
                system_prompt = (
                    "You are a Goal Representation v2 Decomposition Engine. Parse user input into JSON with keys: "
                    "'primary_intent_type' (action_intent, information_need, knowledge_query), "
                    "'target_domain' (desktop_os, filesystem, web_research, mobile_phone, vision_desktop, diagnostic, conversation), "
                    "'goal' (1 phrase actionable goal), "
                    "'desired_outcome' (1 phrase target state), "
                    "'entities' (array of string noun entities), "
                    "'constraints' (array of safety constraint strings), "
                    "'assumptions' (array of assumption strings), "
                    "'unknowns' (array of missing fact strings), "
                    "'preconditions' (array of precondition strings), "
                    "'success_conditions' (array of success criterion strings), "
                    "'failure_conditions' (array of failure criterion strings), "
                    "'required_capabilities' (array of capability strings), "
                    "'risk_factors' (array of risk factor strings)."
                )
                llm_res = llm_client.generate_chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Parse goal v2: '{user_text}'"}
                    ],
                    complexity="fast",
                    max_tokens=300
                )
                if llm_res and llm_res.get("choices"):
                    content = llm_res["choices"][0]["message"]["content"]
                    parsed_json = cls.extract_json_object(content)
                    if parsed_json:
                        val_res = cls.validate_schema(parsed_json)
                        if val_res.is_valid:
                            val_data = val_res.data
                            intent_type = val_data["primary_intent_type"]
                            domain = val_data["target_domain"]
                            goal = val_data["goal"]
                            outcome = val_data["desired_outcome"]
                            if val_data["entities"]: entities = val_data["entities"]
                            if val_data["constraints"]: constraints = val_data["constraints"]
                            if val_data["assumptions"]: assumptions = val_data["assumptions"]
                            if val_data["unknowns"]: unknowns = val_data["unknowns"]
                            if val_data["preconditions"]: preconditions = val_data["preconditions"]
                            if val_data["success_conditions"]: success_conditions = val_data["success_conditions"]
                            if val_data["failure_conditions"]: failure_conditions = val_data["failure_conditions"]
                            if val_data["required_capabilities"]: req_caps = val_data["required_capabilities"]
                            if val_data["risk_factors"]: risks = val_data["risk_factors"]

                            # Epistemic Confidence Calibration after strict schema validation:
                            if intent_type == heuristic_intent and domain == heuristic_domain:
                                confidence = 0.95
                                provenance = "llm_heuristic_agreement"
                            else:
                                confidence = 0.85 if is_ambiguous else 0.60
                                provenance = "llm_semantic_disambiguation" if is_ambiguous else "llm_heuristic_conflict"
                        else:
                            app_logger.warning(
                                f"Rejected malformed LLM semantic goal representation: {val_res.validation_error}"
                            )
                            confidence = 0.50
                            provenance = "rejected_malformed_llm_schema"
            except Exception as e:
                app_logger.warning(f"LLM-assisted Goal v2 decomposition fallback: {e}")

        candidates = cls.synthesize_candidates_from_context(
            domain, user_text, memory_store=memory_store, world_model=world_model, tool_registry=tool_registry
        )
        summary = f"Goal [{domain.upper()}]: '{goal}' | Target Outcome: '{outcome}' | Strategies: {len(candidates)}"

        app_logger.info(f"SemanticGoalInterpreter v2: Intent='{intent_type}', Domain='{domain}', Confidence={confidence:.2f}, Candidates={len(candidates)}")

        return SemanticGoalRepresentation(
            user_query=user_text,
            primary_intent_type=intent_type,
            target_domain=domain,
            goal=goal,
            desired_outcome=outcome,
            entities=entities,
            constraints=constraints,
            assumptions=assumptions,
            unknowns=unknowns,
            preconditions=preconditions,
            success_conditions=success_conditions,
            failure_conditions=failure_conditions,
            required_capabilities=req_caps,
            risk_factors=risks,
            recommended_candidates=candidates,
            confidence=confidence,
            provenance_source=provenance,
            parsed_goal_summary=summary
        )
