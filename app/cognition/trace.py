"""CognitiveTrace Model for Request Tracing & Telemetry."""

from __future__ import annotations
import time
from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class CognitiveTrace:
    user_input: str
    complexity_requested: str = "fast"
    session_id: Optional[str] = None
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)
    vram_pressure_at_start: float = 0.0
    ram_pressure_at_start: float = 0.0
    route_chosen: str = "master_agent_orchestrator"
    model_used: str = "unknown"
    actions_executed: List[str] = field(default_factory=list)
    assistant_reply: str = ""
    latency_ms: float = 0.0
    is_finalized: bool = False

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = f"sess_{uuid4().hex[:8]}"

    def finalize(self, reply: str, actions: List[str], latency: float) -> None:
        self.assistant_reply = reply
        self.actions_executed = actions
        self.latency_ms = round(latency, 2)
        self.is_finalized = True
