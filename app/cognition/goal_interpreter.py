"""Semantic Goal & Intent Representation Layer (Goal Representation v2)."""

from __future__ import annotations
import re
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from app.llm import llm_client, output_budget
from app.utils.logger import app_logger

# ---------------------------------------------------------------------------
# Search query extraction (sentence-as-query bug, found live during P0 #16)
#
# search_files matches FILENAME SUBSTRINGS. Feeding it the whole user sentence
# ("Find all PDF files in the documents folder") can never match a filename, so
# every such search returned 0 results. Extract the content terms instead:
# strip command words and location phrases, KEEP content-type words (pdf, song,
# photo...) — they are legitimate filename substrings. (Item-12 discipline:
# content words may be used as QUERY terms; they must never narrow SCOPE.)
# ---------------------------------------------------------------------------
_LOCATION_PHRASE = re.compile(
    r"\b(?:in|on|under|inside|from)\s+(?:my\s+|the\s+|a\s+)?"
    r"(?:documents?|downloads?|desktop|music|pictures?|videos?|home|pc|computer|laptop|machine|c:|d:|e:|f:)"
    r"(?:\s+(?:folder|directory|dir|drive))?\b",
    re.IGNORECASE,
)
_QUERY_COMMAND_WORDS = {
    "find", "search", "locate", "look", "for", "all", "any", "the", "a", "an",
    "my", "me", "please", "can", "you", "could", "i", "want", "to", "show",
    "get", "give", "list", "open", "up", "of", "and", "with", "there", "is",
    "are", "was", "were", "have", "has", "do", "does", "some", "where",
    "file", "files", "folder", "folders", "directory", "directories",
}


def extract_search_query(user_text: str) -> str:
    """Content terms of a search request, suitable for filename-substring match."""
    text = _LOCATION_PHRASE.sub(" ", user_text or "")
    tokens = [t for t in re.findall(r"[\w.\-]+", text)
              if t.lower() not in _QUERY_COMMAND_WORDS]
    return " ".join(tokens) if tokens else (user_text or "").strip()


@dataclass
class SemanticGoalSchemaValidationResult:
    is_valid: bool
    data: Dict[str, Any] = field(default_factory=dict)
    validation_error: Optional[str] = None


# ── Word-boundary keyword matching ───────────────────────────────────────────
# Live bug (owner machine): 'do i have a song called kaba on my pc' was routed
# to mobile_phone because the bare substring check `"call" in text_lower`
# matched the word 'called'. Keyword routing must match WHOLE WORDS: 'call'
# never matches 'called', 'phone' never matches 'microphone'.
_WORD_PATTERN_CACHE: Dict[str, "re.Pattern"] = {}


def _has_word(text_lower: str, keyword: str) -> bool:
    """True when `keyword` appears in `text_lower` as a whole word/phrase
    (word boundaries on both sides). Safe for multi-word keywords."""
    key = keyword.strip().lower()
    if not key:
        return False
    pat = _WORD_PATTERN_CACHE.get(key)
    if pat is None:
        # Optional plural suffix so 'documents' matches 'document' and
        # 'songs' matches 'song', while 'called' still never matches 'call'.
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(key) + r"(?:s|es)?(?![a-z0-9])")
        _WORD_PATTERN_CACHE[key] = pat
    return pat.search(text_lower) is not None


def _has_any_word(text_lower: str, keywords) -> bool:
    return any(_has_word(text_lower, k) for k in keywords)


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

# ---------------------------------------------------------------------------
# Dynamic candidate breadth (P0 review #3)
#
# A fixed 5-result discovery funnel can lose a NECESSARY capability before
# planning begins: "find the PDF, extract page 4, summarize it, convert it
# and save it" needs ~6 capabilities. Breadth now scales with two honest
# signals, whichever is larger:
#   * the request's complexity tier (fast 5 / main 10 / deep 20), and
#   * the number of DISTINCT action verbs the goal names — a five-step
#     sentence needs several capabilities no matter how it was routed.
# ---------------------------------------------------------------------------
_BREADTH_VERBS = {
    "find", "search", "locate", "list", "open", "launch", "read", "view",
    "extract", "parse", "summarize", "convert", "transform", "save", "write",
    "create", "make", "copy", "move", "rename", "delete", "remove",
    "compress", "zip", "unzip", "send", "email", "upload", "download",
    "install", "update", "check", "verify", "monitor", "analyze", "compare",
    "count", "merge", "split", "edit", "modify", "format", "generate",
    "translate", "transcribe", "print", "scan", "backup", "sync", "schedule",
    "record", "capture", "play", "organize", "sort", "filter", "clean",
}

_COMPLEXITY_BREADTH = {"fast": 5, "main": 10, "deep": 20}
_MAX_BREADTH = 24


def candidate_breadth(user_text: str, complexity: str = "fast") -> int:
    """How many discovered capabilities the candidate funnel may surface."""
    base = _COMPLEXITY_BREADTH.get(complexity, 8)
    words = set(re.findall(r"[a-z_]+", (user_text or "").lower()))
    verb_breadth = 2 * len(words & _BREADTH_VERBS)
    return max(base, min(verb_breadth, _MAX_BREADTH))


class SemanticGoalInterpreter:
    """
    Goal Representation v2 Layer.
    Parses user queries into rich SemanticGoalRepresentation v2 objects carrying
    goals, desired outcomes, entities, constraints, assumptions, unknowns,
    success conditions, required capabilities, and candidate strategies.
    """

    VALID_INTENTS = {"action_intent", "information_need", "knowledge_query"}
    # ── Manifest-unified domain model (P0 bottleneck #2) ────────────────────
    # The tool manifest is the unified capability source (23 categories,
    # 170+ tools). The semantic layer used to reason in only seven legacy
    # domains and SQUASHED everything else (unknown domain → 'desktop_os'/
    # 'diagnostic') — the same family of misroute that deferred a PC song
    # question to phone.adb. Valid domains are now the manifest categories
    # plus the legacy aliases (kept so existing routing stays stable).
    LEGACY_DOMAINS = {
        "desktop_os", "filesystem", "web_research", "mobile_phone",
        "vision_desktop", "diagnostic", "conversation",
    }
    VALID_DOMAINS = set(LEGACY_DOMAINS)  # static backward-compatible view
    # P0 review #5: an agent must not pretend it knows the domain. 'unknown'
    # is the honest answer when classification has no evidence — capability
    # discovery (manifest semantics, world-model caps, memory lessons)
    # resolves the goal, not a guessed domain prior.
    UNKNOWN_DOMAIN = "unknown"

    _manifest_domains_cache = None

    @classmethod
    def _valid_domains(cls):
        if cls._manifest_domains_cache is None:
            domains = set(cls.LEGACY_DOMAINS) | {cls.UNKNOWN_DOMAIN}
            try:
                from app.tools.manifest import get_tool_manifest
                domains |= {
                    str(entry.get("category"))
                    for entry in get_tool_manifest().values()
                    if entry.get("category")
                }
            except Exception as exc:
                app_logger.warning(f"Manifest categories unavailable for domain validation: {exc}")
            cls._manifest_domains_cache = domains
            cls.VALID_DOMAINS = domains  # keep the legacy attribute in sync
        return cls._manifest_domains_cache

    # Keyword hints → manifest-category domain. Checked AFTER the diagnostic
    # branch (investigation intents keep their semantics) and BEFORE the
    # legacy action-keyword branches (which would otherwise swallow these
    # into filesystem/desktop_os). Deliberately conservative: no bare
    # 'pdf'/'photo'/'image'/'web' tokens — those collide with file-search,
    # screenshot and web-research phrasing that must keep its routing.
    _MANIFEST_DOMAIN_KEYWORDS = [
        ("code", ["python", "javascript", "typescript", "script", "scripts", "code",
                  "coding", "refactor", "compile", "unit test", "code review",
                  "git", "github", "commit", "pull request", "merge branch",
                  "bug in my code", "codebase"]),
        ("data", ["csv", "sql", "database", "dataframe", "pandas", "data analysis",
                  "analyze data", "analyze this data", "spreadsheet", "excel",
                  "sqlite", "postgres"]),
        ("documents", ["merge pdf", "split pdf", "combine pdf", "extract pages",
                       "pdf form", "convert to pdf", "create a pdf", "sign pdf",
                       "compress pdf", "docx file", "word document", "pdfs",
                       "these pdf", "the pdf", "both pdf"]),
        ("finance", ["budget", "transaction", "transactions", "expense", "expenses",
                     "crypto", "portfolio", "spending", "income"]),
        ("messaging", ["telegram", "whatsapp", "send a message"]),
        ("network", ["ping", "dns", "traceroute", "port scan", "check port",
                     "whois", "network status", "my network"]),
        ("security", ["opsec", "security audit", "vulnerability", "malware",
                      "clipboard"]),
        ("vision", ["ocr", "analyze image", "read the text in", "take a photo",
                    "camera photo"]),
        ("learning", ["lora", "loras", "fine-tune", "finetune"]),
        ("productivity", ["daily briefing", "briefing", "content ideas",
                          "business opportunities"]),
        ("location", ["where am i", "my location", "geolocate"]),
        ("integration", ["webhook"]),
        ("audio", ["prosody", "tone analysis"]),
        ("knowledge", ["teach you a skill", "learn a new skill", "index knowledge"]),
        ("sandbox", ["sandbox"]),
        ("system", ["running processes", "process list", "cpu usage",
                    "memory usage", "ram usage", "system status"]),
        ("self_awareness", ["what can you do", "your capabilities",
                            "what are you capable of"]),
    ]

    # When the natural tool for a domain lives in another manifest category,
    # name it explicitly (capability awareness resolves real tool names).
    _DOMAIN_CAP_OVERRIDES = {
        "code": ["run_coding_agent", "generate_tests", "code_audit"],
    }

    @classmethod
    def _detect_manifest_domain(cls, text_lower: str):
        """(domain, representative_caps) for a manifest-category hit, else None."""
        for domain, keywords in cls._MANIFEST_DOMAIN_KEYWORDS:
            if _has_any_word(text_lower, keywords):
                return domain, cls._representative_caps(domain)
        return None

    @classmethod
    def _representative_caps(cls, domain: str):
        """Real tool names for the domain: capability awareness resolves them
        against the registry, so an unavailable integration defers HONESTLY
        instead of the goal pretending 'llm.generate' covers it."""
        overrides = list(cls._DOMAIN_CAP_OVERRIDES.get(domain, []))
        if overrides:
            return overrides
        try:
            from app.tools.manifest import get_tool_manifest
            tools = [
                action
                for action, entry in get_tool_manifest().items()
                if str(entry.get("category")) == domain
            ]
            if tools:
                # Prefer read-only (Level 0) representatives; otherwise name
                # the category's real tools so availability is checked truly.
                level0 = [
                    action for action, entry in get_tool_manifest().items()
                    if str(entry.get("category")) == domain
                    and int(entry.get("safety_level", 99)) == 0
                ]
                return (level0 or tools)[:3]
        except Exception:
            pass
        return ["llm.generate"]

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
            if clean_domain not in cls._valid_domains():
                errors.append(f"Invalid 'target_domain' '{raw_domain}'. Must be one of {sorted(cls._valid_domains())}")

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

        if clean_domain not in cls._valid_domains():
            # P0 review #5: unknown domain stays UNKNOWN. Guessing
            # desktop_os/diagnostic/conversation from the intent type was an
            # artificial prior — 'not classified' is not 'desktop'. A real
            # manifest category (code/data/finance/...) is still recognized
            # above; anything else flows on as 'unknown' and capability
            # discovery proposes what the goal actually needs.
            clean_domain = cls.UNKNOWN_DOMAIN

        return clean_intent, clean_domain

    @classmethod
    def build_candidates_for_domain(cls, domain: str, user_text: str) -> List[Dict[str, Any]]:
        domain_clean = domain.lower().strip()
        candidates = []
        if domain_clean == "diagnostic":
            candidates.append({"name": "Diagnostic Investigation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}})
            candidates.append({"name": "Filesystem Search Probe", "action_type": "search_files", "payload": {"query": extract_search_query(user_text), "action_type": "search_files"}})
        elif domain_clean == "mobile_phone":
            candidates.append({"name": "Android ADB Phone Command", "action_type": "phone_command", "payload": {"query": user_text, "action_type": "phone_command"}})
        elif domain_clean == "web_research":
            candidates.append({"name": "Web Search & Browser Research", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
        elif domain_clean == "filesystem":
            candidates.append({"name": "Local Filesystem Search", "action_type": "search_files", "payload": {"query": extract_search_query(user_text), "action_type": "search_files"}})
            candidates.append({"name": "Web Research Fallback", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
        elif domain_clean == "vision_desktop":
            candidates.append({"name": "Desktop Screen Capture & Vision", "action_type": "screen_capture", "payload": {"query": user_text, "action_type": "screen_capture"}})
        elif domain_clean == "desktop_os":
            candidates.append({"name": "Desktop Application Launch", "action_type": "open_application", "payload": {"query": user_text, "action_type": "open_application"}})
            candidates.append({"name": "Web Browser Fallback Search", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
        elif domain_clean == cls.UNKNOWN_DOMAIN:
            # Honest baseline (P0 review #5): no domain prior, no guessed
            # candidates. The manifest semantic discovery (step 1.5), the
            # world-model capability funnel, and memory lessons propose what
            # the goal actually needs; if none of them fires, the
            # conversational answer is the truthful action.
            candidates.append({"name": "Direct Conversational Answer", "action_type": "formulate_answer", "payload": {"query": user_text, "action_type": "formulate_answer"}})
        elif domain_clean in cls._valid_domains():
            # Manifest-category domain: propose the category's primary
            # Level-0 (read-only) tool so the ACT path can genuinely execute,
            # plus the conversational fallback. Gates still apply to anything
            # beyond read-only.
            try:
                from app.tools.manifest import get_tool_manifest
                primary = next(
                    (action for action, entry in get_tool_manifest().items()
                     if str(entry.get("category")) == domain_clean
                     and int(entry.get("safety_level", 99)) == 0),
                    None,
                )
            except Exception:
                primary = None
            if primary:
                # search_files matches filename substrings — the raw sentence
                # can never match one (found live during P0 #16).
                primary_query = extract_search_query(user_text) if primary == "search_files" else user_text
                candidates.append({
                    "name": f"Manifest capability: {primary}",
                    "action_type": primary,
                    "payload": {"query": primary_query, "action_type": primary},
                })
            candidates.append({"name": "Direct Conversational Answer", "action_type": "formulate_answer", "payload": {"query": user_text, "action_type": "formulate_answer"}})
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
        tool_registry: Optional[Any] = None,
        complexity: str = "fast",
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes candidate execution strategies by combining:
        1. Domain baseline strategy branches (the domain prior)
        1.5 Manifest semantic discovery: ranked tools matching THIS goal
            across the entire tool universe (capability discovery + semantic
            matching, not domain-hard-coded shortlists)
        2. System capabilities registered in WorldModel / ToolRegistry (if world_model supplied)
        3. MemoryStore reflections and past learned lessons for similar queries (if memory_store supplied)

        Note: Does NOT instantiate fallback MemoryStore() or WorldModel() instances when
        context is not provided, preventing uncoordinated cognitive store creation.
        """
        domain_clean = domain.lower().strip()
        candidates: List[Dict[str, Any]] = []

        # 1. Base domain candidate strategies
        candidates.extend(cls.build_candidates_for_domain(domain_clean, user_text))

        # 1.5 Manifest semantic discovery (P0 bottleneck #3): candidate
        # generation must flow goal -> capability discovery -> semantic
        # matching -> candidates over the FULL tool universe, not just the
        # domain's hard-coded baseline ('filesystem' used to propose only
        # search_files + web_search while compress/pdf/git/... tools sat
        # unreachable). The baseline stays as the domain prior; discovery
        # adds every tool that semantically matches THIS goal.
        try:
            from app.cognition.tool_matcher import rank_tools
            from app.tools.manifest import get_tool_manifest
            from app.cognition.tool_registry import interpret_availability
            manifest_entries = get_tool_manifest()
            already = {c.get("action_type") for c in candidates}
            for match in rank_tools(
                user_text,
                limit=candidate_breadth(user_text, complexity),
                domain_hint=domain_clean,
            ):
                if match.action_type in already or match.action_type == "formulate_answer":
                    continue
                # ONE canonical interpretation (P0 review #1): a KNOWN
                # missing dependency spends no candidate slot. NOT_CHECKED
                # flows verbatim — the planner probes before committing.
                entry = manifest_entries.get(match.action_type) or {}
                try:
                    _status = interpret_availability(entry.get("availability"), probe=False)
                except Exception:
                    _status = {"available": None, "status": "not_checked"}
                if _status.get("available") is False:
                    continue
                payload = dict(match.payload or {"query": user_text})
                if _status.get("available") is None:
                    payload["availability"] = "not_checked"
                candidates.append({
                    "name": f"Discovered capability: {match.action_type}",
                    "action_type": match.action_type,
                    "payload": payload,
                    "source": "manifest_discovery",
                    "score": match.score,
                })
                already.add(match.action_type)
        except Exception as exc:
            app_logger.warning(f"Manifest candidate discovery unavailable: {exc}")

        # 2. Ingest learned strategy lessons from MemoryStore if explicitly supplied
        lesson_text = ""
        if memory_store is not None:
            try:
                past_memories = memory_store.search(user_text, limit=3)
                lesson_text = " ".join(
                    str(getattr(mem, "content", "") or "") for mem in past_memories
                ).lower()
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

        # 3. Inspect the WorldModel capability graph for active, EXECUTABLE
        # capabilities if explicitly supplied. P0 bottleneck #4: the old
        # `active_caps[:5]` slice considered only the five most-recently-seen
        # entities (find_entities orders by last_seen DESC) — the rest of the
        # capability graph was invisible no matter how relevant. Now ALL
        # capabilities flow through a ranked discovery funnel:
        #   semantic relevance -> availability -> safety ->
        #   historical success -> resource cost -> top candidates
        # (the final cut is a RANKED cut, not an arbitrary position slice).
        if world_model is not None:
            try:
                if tool_registry is not None:
                    executable_tools = set(tool_registry._registry.keys())
                else:
                    # ONE runtime ToolRegistry (P0 #20) — never a fresh one.
                    from app.cognition.tool_registry import get_shared_registry
                    executable_tools = set(get_shared_registry()._registry.keys())

                NATIVE_EXECUTABLE_CAPS = {
                    "open_application", "launch_app", "web_search", "search_files",
                    "phone_command", "make_phone_call", "send_sms", "screen_capture",
                    "opsec_audit", "daily_briefing", "investigate", "diagnostic",
                    "formulate_answer", "answer", "workflow_execute"
                }

                try:
                    from app.tools.manifest import get_tool_manifest as _gtm
                    manifest = _gtm()
                except Exception:
                    manifest = {}

                lowered = (user_text or "").lower()
                text_tokens = {t for t in re.findall(r"[a-z_]+", lowered) if len(t) > 2}
                words = set(re.findall(r"[a-z_]+", lowered))
                ranked: List[Tuple[float, Any, str]] = []
                for cap in world_model.find_entities(entity_type="capability"):
                    cap_name = str(getattr(cap, "name", "") or "").lower().replace(" ", "_")
                    if not cap_name:
                        continue
                    # AVAILABILITY (hard): a capability must have an active
                    # handler before it can become a candidate.
                    is_executable = (cap_name in executable_tools) or (cap_name in NATIVE_EXECUTABLE_CAPS) or any(ec in cap_name for ec in NATIVE_EXECUTABLE_CAPS)
                    if not is_executable:
                        app_logger.warning(f"CandidateSynthesizer: Skipping non-executable capability entity '{cap.name}'")
                        continue
                    entry = manifest.get(cap_name) or {}
                    # AVAILABILITY (soft, honest — P0 #21): NOT_CHECKED is
                    # NOT AVAILABLE. A KNOWN-missing dependency (available
                    # False) loses its candidate slot; an unchecked one
                    # (available None) stays a candidate but carries its
                    # honest state downstream so the planner can probe before
                    # committing and the owner sees the risk before execution.
                    # ONE canonical interpretation (P0 review #1): the
                    # registry's interpret_availability — dicts, booleans and
                    # no-kwarg checkers all keep their verbatim meaning.
                    try:
                        from app.cognition.tool_registry import interpret_availability
                        _status = interpret_availability(entry.get("availability"), probe=False)
                    except Exception:
                        _status = {"available": None, "status": "not_checked"}
                    availability_state = "available"
                    if _status.get("available") is False:
                        continue
                    if _status.get("available") is None:
                        availability_state = "not_checked"

                    # 1. SEMANTIC RELEVANCE to this goal (name + entity
                    # description + manifest description token overlap).
                    cap_attr = getattr(cap, "attributes", None)
                    try:
                        cap_desc = str((cap_attr or {}).get("description", "") or "")
                    except Exception:
                        cap_desc = ""
                    hay = f"{cap_name.replace('_', ' ')} {cap_desc} {str(entry.get('description', '') or '')}".lower()
                    cap_tokens = {t for t in re.findall(r"[a-z_]+", hay) if len(t) > 2}
                    score = float(len(text_tokens & cap_tokens))
                    name_words = set(cap_name.split("_")) - {"and", "the"}
                    if name_words and name_words <= words:
                        score += 2.0
                    # 2. SAFETY: prefer lower safety levels (less destructive,
                    # more autonomous). Unknown level (custom hotloaded tool)
                    # is treated as gated.
                    try:
                        safety = float(entry.get("safety_level", 2) or 0)
                    except Exception:
                        safety = 2.0
                    score -= 0.75 * safety
                    # 3. HISTORICAL SUCCESS: episodic lessons that name this
                    # capability, plus the entity's recorded confidence.
                    if cap_name in lesson_text or cap_name.replace("_", " ") in lesson_text:
                        score += 1.5
                    try:
                        score += min(float(getattr(cap, "confidence", 1.0) or 0.0), 1.0)
                    except Exception:
                        pass
                    # 4. RESOURCE COST: honored when the executor records a
                    # duration on the entity ('avg_duration_s'); no-op until
                    # such data exists.
                    try:
                        cost = float((cap_attr or {}).get("avg_duration_s", 0) or 0)
                    except Exception:
                        cost = 0.0
                    score -= min(cost, 2.0)
                    ranked.append((score, cap, cap_name, availability_state))

                ranked.sort(key=lambda item: item[0], reverse=True)
                existing_actions = {c.get("action_type") for c in candidates}
                # availability_state is carried THROUGH the sort (P1 review):
                # it is per-capability evidence. Reading the loop variable
                # after sorting attached the LAST capability's state to every
                # candidate — a not_checked capability could be labeled
                # 'available' (and the planner would skip its probe).
                for score, cap, cap_name, availability_state in ranked[:max(candidate_breadth(user_text, complexity), 8)]:
                    if cap_name in existing_actions:
                        continue
                    candidates.append({
                        "name": f"Dynamic Capability: {cap.name}",
                        "action_type": cap_name,
                        "payload": {
                            "query": user_text,
                            "action_type": cap_name,
                            # NOT_CHECKED != AVAILABLE: carried verbatim so the
                            # ActionPlanner probes before committing (P0 #21).
                            "availability": availability_state,
                        },
                        "source": "world_model_capability",
                        "score": score,
                    })
                    existing_actions.add(cap_name)
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
        # (word-boundary matching: bare substrings misroute — 'call' matched
        # 'called' and sent a PC file question to the mobile_phone domain)
        if _has_any_word(text_lower, ["why", "how come", "find out", "find whether", "find if", "check if", "investigate", "where is", "does file", "error", "crash", "failed", "won't open", "can't open"]):
            intent_type = "information_need"
            domain = "diagnostic"
            goal = f"Investigate cause or evidence for: '{user_text[:60]}'"
            outcome = "Diagnostic evidence gathered and reported"
            unknowns = ["underlying error cause", "evidence availability"]
            req_caps = ["filesystem.search", "system.probe"]

        # 1.5 Manifest-category domains: route to the manifest's own
        # vocabulary (coding/data/pdf/finance/git/...). Runs BEFORE the
        # legacy action branches so 'write a python script to organize my
        # files' is a CODE task, not a filesystem/desktop_os task.
        manifest_hit = cls._detect_manifest_domain(text_lower)
        if manifest_hit is not None:
            manifest_domain, manifest_caps = manifest_hit
            domain = manifest_domain
            req_caps = manifest_caps
            # Action-ish verbs in a manifest-domain request make it an
            # action intent; questions stay knowledge queries.
            if _has_any_word(text_lower, [
                "write", "create", "generate", "build", "make", "run",
                "execute", "analyze", "analyse", "send", "merge", "split",
                "convert", "extract", "fill", "summarize", "summarise",
            ]):
                intent_type = "action_intent"
                goal = f"Accomplish {manifest_domain} task: '{user_text[:60]}'"
                outcome = f"{manifest_domain} capability applied to the owner's request"
                success_conditions = [f"{manifest_domain}_result_delivered = true"]

        # 2. Operational Action Commands SECOND
        elif _has_any_word(text_lower, ["open", "launch", "start", "run", "search", "call", "sms", "photo", "screenshot", "briefing", "play", "find"]):
            intent_type = "action_intent"
            if _has_any_word(text_lower, ["phone", "mobile", "call", "sms", "battery", "charged"]):
                domain = "mobile_phone"
                goal = f"Execute mobile phone operation: '{user_text[:60]}'"
                outcome = "Mobile phone action completed via ADB"
                req_caps = ["phone.adb", "phone.control"]
            elif _has_any_word(text_lower, ["youtube", "google", "search web"]):
                domain = "web_research"
                goal = f"Perform web search or research: '{user_text[:60]}'"
                outcome = "Web search results retrieved"
                req_caps = ["browser.open", "web.search"]
            elif _has_any_word(text_lower, ["find", "file", "ordinary", "document", "song"]):
                domain = "filesystem"
                goal = f"Locate or inspect local file: '{user_text[:60]}'"
                outcome = "Matching file path identified"
                req_caps = ["filesystem.search", "filesystem.read"]
            elif _has_any_word(text_lower, ["screenshot", "screen"]):
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
        if complexity in ["main", "deep"] or is_ambiguous_collision:
            try:
                system_prompt = (
                    "You are a Goal Representation v2 Decomposition Engine. Parse user input into JSON with keys: "
                    "'primary_intent_type' (action_intent, information_need, knowledge_query), "
                    "'target_domain' (a capability domain such as desktop_os, filesystem, web_research, mobile_phone, vision_desktop, diagnostic, conversation, or a manifest category like code/data/finance; use 'unknown' when uncertain — never guess), "
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
                    max_tokens=output_budget("structured", "fast")
                )
                if (
                    llm_res
                    and llm_res.get("success") is not False
                    and not llm_res.get("simulated")
                    and llm_res.get("choices")
                ):
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
            domain, user_text, memory_store=memory_store, world_model=world_model,
            tool_registry=tool_registry, complexity=complexity
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
