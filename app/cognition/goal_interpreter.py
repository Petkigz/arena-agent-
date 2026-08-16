"""Semantic Goal & Intent Representation Layer."""

from __future__ import annotations
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
    Interprets natural language user goals, producing a structured SemanticGoalRepresentation
    for ReasoningCycle and ActionPlanner.
    """

    @classmethod
    def interpret_goal(cls, user_text: str, complexity: str = "fast") -> SemanticGoalRepresentation:
        text_lower = user_text.lower().strip()

        intent_type = "knowledge_query"
        domain = "conversation"
        candidates = []

        # 1. Diagnostic, Research & Information Gathering queries
        if any(k in text_lower for k in ["why ", "how come", "find out", "check if", "investigate", "where is", "does file", "error", "crash", "failed", "won't open", "can't open"]):
            intent_type = "information_need"
            domain = "diagnostic"
            candidates.append({"name": "Diagnostic Investigation Probe", "action_type": "investigate", "payload": {"query": user_text, "action_type": "investigate"}})
            candidates.append({"name": "Filesystem Search Probe", "action_type": "search_files", "payload": {"query": user_text, "action_type": "search_files"}})

        # 2. Operational Action Commands
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

        # 3. Direct Conversational Q&A
        else:
            intent_type = "knowledge_query"
            domain = "conversation"
            candidates.append({"name": "Direct Conversational Answer", "action_type": "formulate_answer", "payload": {"query": user_text, "action_type": "formulate_answer"}})

        app_logger.info(f"SemanticGoalInterpreter parsed goal: Intent='{intent_type}', Domain='{domain}', Candidates={len(candidates)}")

        return SemanticGoalRepresentation(
            user_query=user_text,
            primary_intent_type=intent_type,
            target_domain=domain,
            parsed_goal_summary=f"Parsed goal in domain '{domain}': {user_text[:80]}",
            recommended_candidates=candidates
        )
