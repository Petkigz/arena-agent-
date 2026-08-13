"""Cognitive Pipeline Enforcer for Unified Local Execution."""

from __future__ import annotations
import uuid
from typing import Dict, Any, List, Optional

from app.cognition.blackboard import Blackboard
from app.cognition.cognitive_state import CognitiveState
from app.cognition.prompt_slicer import PromptSlicerEngine
from app.cognition.tool_registry import ToolRegistry
from app.agents.master_agent import MasterAgentOrchestrator
from app.utils.logger import app_logger

class CognitivePipeline:
    """Enforces closed-loop cognition across all incoming user prompts and tool calls."""

    def __init__(self) -> None:
        self.registry = ToolRegistry()

    def process_request(self, user_text: str, session_id: Optional[str] = None, complexity: str = "fast") -> Dict[str, Any]:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        app_logger.info(f"CognitivePipeline processing request for session '{session_id}': {user_text[:60]}")

        # 1. Instruction Slicing & Context Setup
        prompt_ctx = PromptSlicerEngine.slice_context_for_task(user_text)

        # 2. Master Agent Execution through Gatekeeper
        agent_res = MasterAgentOrchestrator.process_user_task(user_text, complexity=complexity)

        return {
            "success": True,
            "session_id": session_id,
            "user_text": user_text,
            "assistant_reply": agent_res.get("assistant_reply", "Done."),
            "executed_actions": agent_res.get("executed_actions", []),
            "prompt_slicer_rules": prompt_ctx.selected_instructions,
            "model_used": agent_res.get("model_used", "")
        }
