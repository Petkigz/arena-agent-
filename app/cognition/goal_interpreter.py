"""Semantic Goal & Intent Representation Layer."""

from __future__ import annotations
import re
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.utils.logger import app_logger

@dataclass
class SemanticGoalRepresentation:
    user_query: str
    primary_intent_type: str  # 'action_intent', 'information_need', 'knowledge_query'
    target_domain: str        # 'desktop_os', 'filesystem', 'web_research', 'mobile_phone', 'vision_desktop', 'conversation'
    parsed_goal_summary: str
    recommended_candidates: List[Dict[str, Any]] = field(default_factory=list)

class SemanticGoalInterpreter:
    """
    Semantic Goal & Intent Representation Layer.
    Interprets natural language user goals into structured SemanticGoalRepresentation
    for ReasoningCycle and ActionPlanner.
    """

    @classmethod
    def interpret_goal(cls, user_text: str, complexity: str = "fast") -> SemanticGoalRepresentation:
        text_lower = user_text.lower().strip()

        intent_type = "knowledge_query"
        domain = "conversation"
        candidates = []

        # 1. Diagnostic, Research & Information Gathering queries FIRST
        if any(k in text_lower for k in ["why ", "how come", "find out", "find whether", "find if", "check if", "investigate", "where is", "does file", "error", "crash", "failed", "won't open", "can't open"]):
            intent_type = "information_need"
            domain = "diagnostic"
            candidates.append({"name": "Diagnostic Investigation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}})
            candidates.append({"name": "Filesystem Search Probe", "action_type": "search_files", "payload": {"query": user_text, "action_type": "search_files"}})

        # 2. Direct Operational Action Commands SECOND
        elif any(k in text_lower for k in ["open", "launch", "start", "run", "search", "call", "sms", "photo", "screenshot", "briefing", "play", "find"]):
            intent_type = "action_intent"
            if "phone" in text_lower or "mobile" in text_lower or "call" in text_lower or "sms" in text_lower or "battery" in text_lower or "charged" in text_lower:
                domain = "mobile_phone"
                candidates.append({"name": "Android ADB Phone Command", "action_type": "phone_command", "payload": {"query": user_text, "action_type": "phone_command"}})
            elif "youtube" in text_lower or "google" in text_lower or "search web" in text_lower:
                domain = "web_research"
                candidates.append({"name": "Web Search & Browser Research", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
            elif "find" in text_lower or "file" in text_lower or "ordinary" in text_lower or "document" in text_lower or "song" in text_lower:
                domain = "filesystem"
                candidates.append({"name": "Local Filesystem Search", "action_type": "search_files", "payload": {"query": user_text, "action_type": "search_files"}})
                candidates.append({"name": "Web Research Fallback", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})
            elif "screenshot" in text_lower or "screen" in text_lower:
                domain = "vision_desktop"
                candidates.append({"name": "Desktop Screen Capture & Vision", "action_type": "screen_capture", "payload": {"query": user_text, "action_type": "screen_capture"}})
            else:
                domain = "desktop_os"
                candidates.append({"name": "Desktop Application Launch", "action_type": "open_application", "payload": {"query": user_text, "action_type": "open_application"}})
                candidates.append({"name": "Web Browser Fallback Search", "action_type": "web_search", "payload": {"query": user_text, "action_type": "web_search"}})

        # 3. Direct Conversational Q&A DEFAULT
        else:
            intent_type = "knowledge_query"
            domain = "conversation"
            candidates.append({"name": "Direct Conversational Answer", "action_type": "formulate_answer", "payload": {"query": user_text, "action_type": "formulate_answer"}})

        # LLM-Assisted Semantic Goal Decomposition Path when complexity == "main"
        if complexity == "main":
            try:
                system_prompt = (
                    "You are a semantic goal decomposition engine. Parse user input into JSON with keys: "
                    "'primary_intent_type' (action_intent, information_need, knowledge_query), "
                    "'target_domain' (desktop_os, filesystem, web_research, mobile_phone, vision_desktop, diagnostic, conversation), "
                    "'parsed_goal_summary' (1 sentence summary)."
                )
                llm_res = llm_client.generate_chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Parse goal: '{user_text}'"}
                    ],
                    complexity="fast",
                    max_tokens=150
                )
                if llm_res.get("choices"):
                    content = llm_res["choices"][0]["message"]["content"]
                    json_match = re.search(r'\{[^{}]*\}', content)
                    if json_match:
                        parsed_json = json.loads(json_match.group(0))
                        intent_type = parsed_json.get("primary_intent_type", intent_type)
                        domain = parsed_json.get("target_domain", domain)
                        summary = parsed_json.get("parsed_goal_summary", f"Goal Domain [{domain.upper()}]: '{user_text[:70]}'")
                        return SemanticGoalRepresentation(
                            user_query=user_text,
                            primary_intent_type=intent_type,
                            target_domain=domain,
                            parsed_goal_summary=summary,
                            recommended_candidates=candidates
                        )
            except Exception as e:
                app_logger.warning(f"LLM-assisted goal decomposition fallback: {e}")

        summary = f"Goal Domain [{domain.upper()}]: '{user_text[:70]}' | Candidate Strategies: {len(candidates)}"
        app_logger.info(f"SemanticGoalInterpreter: Intent='{intent_type}', Domain='{domain}', Candidates={len(candidates)}")

        return SemanticGoalRepresentation(
            user_query=user_text,
            primary_intent_type=intent_type,
            target_domain=domain,
            parsed_goal_summary=summary,
            recommended_candidates=candidates
        )
