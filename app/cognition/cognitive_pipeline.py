"""Cognitive Pipeline Enforcer for Unified Local Execution."""

from __future__ import annotations
import uuid
from typing import Dict, Any, List, Optional
from app.cognition.runtime import CognitiveRuntime
from app.utils.logger import app_logger

class CognitivePipeline:
    """Enforces single-path closed-loop cognition by delegating strictly to CognitiveRuntime."""

    @classmethod
    def process_chat(cls, user_text: str, complexity: str = "fast", session_id: Optional[str] = None) -> Dict[str, Any]:
        return cls.process_request(user_text, session_id=session_id, complexity=complexity)

    @classmethod
    def process_request(cls, user_text: str, session_id: Optional[str] = None, complexity: str = "fast") -> Dict[str, Any]:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        app_logger.info(f"CognitivePipeline delegating request for session '{session_id}' to CognitiveRuntime...")

        runtime = CognitiveRuntime.get_instance()
        res = runtime.process_unified_thought_cycle(user_text, complexity=complexity)

        return {
            "success": True,
            "session_id": session_id,
            "trace_id": f"trace_{uuid.uuid4().hex[:8]}",
            "user_text": user_text,
            "assistant_reply": res.get("assistant_reply", "Done."),
            "executed_actions": res.get("executed_actions", []),
            "model_used": res.get("active_focus", "MasterAgent")
        }
