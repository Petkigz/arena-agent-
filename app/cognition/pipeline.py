"""Single-Path Pipeline Bridge delegating strictly to CognitivePipeline."""

from __future__ import annotations
from typing import Optional, Dict, Any
from app.cognition.cognitive_pipeline import CognitivePipeline

class PipelineBridge:
    @staticmethod
    def process_chat(user_text: str, complexity: str = "fast", session_id: Optional[str] = None) -> Dict[str, Any]:
        return CognitivePipeline.process_chat(user_text, complexity=complexity, session_id=session_id)
