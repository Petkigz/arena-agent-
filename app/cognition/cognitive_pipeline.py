"""Cognitive Pipeline Enforcer delegating strictly to CognitiveRuntime Composition Root."""

from __future__ import annotations
import uuid
from typing import Dict, Any, List, Optional
from app.cognition.runtime import CognitiveRuntime
from app.utils.logger import app_logger

class CognitivePipeline:
    """Enforces closed-loop cognition across all incoming user prompts and tool calls via CognitiveRuntime."""

    @classmethod
    def process_chat(cls, user_text: str, complexity: str = "fast", session_id: Optional[str] = None) -> Dict[str, Any]:
        return cls.process_request(user_text, session_id=session_id, complexity=complexity)

    @classmethod
    def process_request(cls, user_text: str, session_id: Optional[str] = None, complexity: str = "fast") -> Dict[str, Any]:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        app_logger.info(f"CognitivePipeline routing request for session '{session_id}' to CognitiveRuntime...")

        runtime = CognitiveRuntime.get_instance()
        res = runtime.process_cognitive_cycle(user_text, complexity=complexity, session_id=session_id)

        return {
            "success": True,
            "session_id": res.get("session_id", session_id),
            "trace_id": res.get("trace_id", f"trace_{uuid.uuid4().hex[:8]}"),
            "user_text": user_text,
            "assistant_reply": res.get("assistant_reply", "Done."),
            "executed_actions": res.get("executed_actions", []),
            "latency_ms": res.get("latency_ms", 0.0),
            "model_used": res.get("model_used", "fast")
        }
