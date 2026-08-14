"""Cognitive Pipeline Trace & Session Tracker."""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class CognitiveTrace:
    user_input: str
    complexity_requested: str = "fast"
    session_id: Optional[str] = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:8]}")
    route_chosen: str = "CognitivePipeline"
    vram_pressure_at_start: float = 0.0
    ram_pressure_at_start: float = 0.0
    assistant_reply: str = ""
    actions_executed: List[str] = field(default_factory=list)
    model_used: str = "fast"
    latency_ms: float = 0.0
    is_finalized: bool = False
    created_at: str = field(default_factory=_now)

    def finalize(self, reply: str, actions: List[str], latency: float):
        self.assistant_reply = reply
        self.actions_executed = actions
        self.latency_ms = latency
        self.is_finalized = True
