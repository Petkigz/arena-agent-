"""Cognitive Pipeline Trace & Session Tracker with Hardware Telemetry."""

from __future__ import annotations
import time
import uuid
import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger

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
        self._persist_trace_to_db()

    def _persist_trace_to_db(self):
        """
        P1-G: Persists full cognitive trace telemetry (hardware pressure, model used, actions, latency) to SQLite.
        """
        try:
            conn = sqlite3.connect(str(settings.DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_traces (
                    trace_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    assistant_reply TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    vram_pressure REAL,
                    ram_pressure REAL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                INSERT OR REPLACE INTO cognitive_traces
                (trace_id, session_id, user_input, assistant_reply, actions_json, model_used, latency_ms, vram_pressure, ram_pressure, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.trace_id,
                self.session_id or "default",
                self.user_input,
                self.assistant_reply,
                json.dumps(self.actions_executed),
                self.model_used,
                self.latency_ms,
                self.vram_pressure_at_start,
                self.ram_pressure_at_start,
                self.created_at
            ))
            conn.commit()
            conn.close()
            audit_logger.info(f"Persisted CognitiveTrace [{self.trace_id[:8]}] (Latency: {self.latency_ms:.0f}ms)")
        except Exception as e:
            app_logger.warning(f"CognitiveTrace persistence notice: {e}")
