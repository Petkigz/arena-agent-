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
    ontology_revision: int = 1
    vram_pressure_at_start: float = 0.0
    ram_pressure_at_start: float = 0.0
    attention_focus: str = ""
    belief_confidence: float = 1.0
    predicted_outcome: Dict[str, Any] = field(default_factory=dict)
    gate_decision: str = "passed"
    assistant_reply: str = ""
    actions_executed: List[str] = field(default_factory=list)
    prediction_surprisal: float = 0.0
    reflection_lesson: str = ""
    goal_verified: bool = True
    goal_lifecycle_state: str = ""  # e.g. 'achieved', 'waiting_for_evidence', 'deferred'
    epistemic_presentation: Dict[str, Any] = field(default_factory=dict)
    grounding_result: Dict[str, Any] = field(default_factory=dict)
    retrieved_memories: List[Dict[str, Any]] = field(default_factory=list)
    hypothesis_state: Dict[str, Any] = field(default_factory=dict)
    compute_policy: Dict[str, Any] = field(default_factory=dict)
    strategy_goal_type: str = ""
    strategy_action_type: str = ""
    resource_allocation: Dict[str, Any] = field(default_factory=dict)
    criticality_review: Dict[str, Any] = field(default_factory=dict)
    route_comparison: Dict[str, Any] = field(default_factory=dict)
    model_used: str = "fast"
    latency_ms: float = 0.0
    is_finalized: bool = False
    created_at: str = field(default_factory=_now)

    def finalize(
        self,
        reply: str,
        actions: List[str],
        latency: float,
        surprisal: float = 0.0,
        lesson: str = "",
        gate_decision: str = "passed",
        goal_verified: bool = True,
        goal_lifecycle_state: str = "",
        epistemic_presentation: Optional[Dict[str, Any]] = None,
        grounding_result: Optional[Dict[str, Any]] = None,
    ):
        self.assistant_reply = reply
        self.actions_executed = actions
        self.latency_ms = latency
        self.prediction_surprisal = surprisal
        self.reflection_lesson = lesson
        self.gate_decision = gate_decision
        self.goal_verified = goal_verified
        if goal_lifecycle_state:
            self.goal_lifecycle_state = goal_lifecycle_state
        if epistemic_presentation is not None:
            self.epistemic_presentation = dict(epistemic_presentation)
        if grounding_result is not None:
            self.grounding_result = dict(grounding_result)
        self.is_finalized = True
        self._persist_trace_to_db()

    @classmethod
    def record_usefulness_feedback(
        cls,
        trace_id: str,
        *,
        usefulness: str,
        outcome_signal: str = "",
        retrieval_useful: Optional[bool] = None,
        note: str = "",
    ) -> Dict[str, Any]:
        """Append an owner usefulness event to the trace database.

        Usefulness is deliberately stored separately from correctness or goal
        verification.  A helpful but incomplete answer, a correct answer that
        required clarification, and an incorrect answer are different signals;
        this event never rewrites epistemic state or execution truth.
        """
        allowed_usefulness = {"helpful", "partially_helpful", "not_helpful"}
        allowed_signals = {
            "",
            "task_completed",
            "clarification_requested",
            "correction_followup",
            "abandoned",
            "unknown",
        }
        usefulness = str(usefulness or "").strip().lower()
        outcome_signal = str(outcome_signal or "").strip().lower()
        if usefulness not in allowed_usefulness:
            raise ValueError(
                "usefulness must be one of: helpful, partially_helpful, not_helpful"
            )
        if outcome_signal not in allowed_signals:
            raise ValueError(
                "outcome_signal must be one of: task_completed, "
                "clarification_requested, correction_followup, abandoned, unknown"
            )
        note = str(note or "").strip()[:2000]
        feedback_id = f"feedback_{uuid.uuid4().hex[:12]}"
        created_at = _now()
        try:
            with sqlite3.connect(str(settings.DB_PATH)) as conn:
                try:
                    trace_exists = conn.execute(
                        "SELECT 1 FROM cognitive_traces WHERE trace_id = ? LIMIT 1",
                        (str(trace_id),),
                    ).fetchone()
                except sqlite3.OperationalError as exc:
                    if "no such table" in str(exc).lower():
                        raise KeyError(f"unknown trace_id: {trace_id}") from exc
                    raise
                if trace_exists is None:
                    raise KeyError(f"unknown trace_id: {trace_id}")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cognitive_trace_usefulness (
                        feedback_id TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        usefulness TEXT NOT NULL,
                        outcome_signal TEXT NOT NULL DEFAULT '',
                        retrieval_useful INTEGER,
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT INTO cognitive_trace_usefulness
                    (feedback_id, trace_id, usefulness, outcome_signal,
                     retrieval_useful, note, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    feedback_id,
                    str(trace_id),
                    usefulness,
                    outcome_signal,
                    None if retrieval_useful is None else int(bool(retrieval_useful)),
                    note,
                    created_at,
                ))
                conn.commit()
        except KeyError:
            raise
        except Exception as exc:
            app_logger.warning(f"CognitiveTrace usefulness feedback failed: {exc}")
            raise RuntimeError(f"could not record usefulness feedback: {exc}") from exc
        return {
            "feedback_id": feedback_id,
            "trace_id": str(trace_id),
            "usefulness": usefulness,
            "outcome_signal": outcome_signal,
            "retrieval_useful": retrieval_useful,
            "note": note,
            "created_at": created_at,
        }

    @classmethod
    def list_usefulness_feedback(cls, trace_id: str) -> List[Dict[str, Any]]:
        """Return owner usefulness events without mixing in correctness fields."""
        try:
            with sqlite3.connect(str(settings.DB_PATH)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT feedback_id, trace_id, usefulness, outcome_signal,
                           retrieval_useful, note, created_at
                    FROM cognitive_trace_usefulness
                    WHERE trace_id = ?
                    ORDER BY created_at ASC
                """, (str(trace_id),)).fetchall()
            return [
                {
                    **dict(row),
                    "retrieval_useful": (
                        None if row["retrieval_useful"] is None
                        else bool(row["retrieval_useful"])
                    ),
                }
                for row in rows
            ]
        except sqlite3.OperationalError:
            # The trace may predate feedback support; absence is an empty
            # measurement set, not evidence that the response was useful.
            return []
        except Exception as exc:
            app_logger.warning(f"CognitiveTrace usefulness feedback read failed: {exc}")
            return []

    @classmethod
    def update_persisted_reply(cls, trace_id: str, reply: str) -> bool:
        """Update only the owner-visible reply for a post-cycle delivery notice.

        Prospective reminders can become due at the turn boundary before the
        regular cognitive cycle finishes. Keeping this narrow update separate
        preserves the existing trace fields and does not add private reasoning
        to the persisted explanation surface.
        """
        try:
            with sqlite3.connect(str(settings.DB_PATH)) as conn:
                cursor = conn.execute(
                    "UPDATE cognitive_traces SET assistant_reply=? WHERE trace_id=?",
                    (str(reply or ""), str(trace_id)),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            app_logger.warning(f"CognitiveTrace reply update notice: {exc}")
            return False

    def _persist_trace_to_db(self):
        """
        P1-G: Persists full cognitive trace telemetry (intermediate states, hardware pressure, model used, actions, latency) to SQLite.
        """
        try:
            conn = sqlite3.connect(str(settings.DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_traces (
                    trace_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    ontology_revision INTEGER NOT NULL DEFAULT 1,
                    assistant_reply TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    vram_pressure REAL,
                    ram_pressure REAL,
                    attention_focus TEXT,
                    belief_confidence REAL,
                    gate_decision TEXT,
                    prediction_surprisal REAL,
                    reflection_lesson TEXT,
                    goal_verified INTEGER,
                    goal_lifecycle_state TEXT,
                    epistemic_presentation_json TEXT NOT NULL DEFAULT '{}',
                    grounding_result_json TEXT NOT NULL DEFAULT '{}',
                    retrieved_memories_json TEXT NOT NULL DEFAULT '[]',
                    hypothesis_state_json TEXT NOT NULL DEFAULT '{}',
                    compute_policy_json TEXT NOT NULL DEFAULT '{}',
                    strategy_goal_type TEXT NOT NULL DEFAULT '',
                    strategy_action_type TEXT NOT NULL DEFAULT '',
                    resource_allocation_json TEXT NOT NULL DEFAULT '{}',
                    criticality_review_json TEXT NOT NULL DEFAULT '{}',
                    route_comparison_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            # Migration: older DBs predate later columns; CREATE TABLE IF NOT
            # EXISTS won't add them, so patch EVERY missing column in.
            cols = {r[1] for r in cursor.execute("PRAGMA table_info(cognitive_traces)").fetchall()}
            for column, ddl in (
                ("ontology_revision", "INTEGER NOT NULL DEFAULT 1"),
                ("attention_focus", "TEXT"),
                ("belief_confidence", "REAL"),
                ("gate_decision", "TEXT"),
                ("prediction_surprisal", "REAL"),
                ("reflection_lesson", "TEXT"),
                ("goal_verified", "INTEGER"),
                ("goal_lifecycle_state", "TEXT"),
                ("epistemic_presentation_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("grounding_result_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("retrieved_memories_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("hypothesis_state_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("compute_policy_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("strategy_goal_type", "TEXT NOT NULL DEFAULT ''"),
                ("strategy_action_type", "TEXT NOT NULL DEFAULT ''"),
                ("resource_allocation_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("criticality_review_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("route_comparison_json", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                if column not in cols:
                    cursor.execute(f"ALTER TABLE cognitive_traces ADD COLUMN {column} {ddl}")
            cursor.execute("""
                INSERT OR REPLACE INTO cognitive_traces
                (trace_id, session_id, user_input, ontology_revision, assistant_reply, actions_json, model_used, latency_ms, vram_pressure, ram_pressure, attention_focus, belief_confidence, gate_decision, prediction_surprisal, reflection_lesson, goal_verified, goal_lifecycle_state, epistemic_presentation_json, grounding_result_json, retrieved_memories_json, hypothesis_state_json, compute_policy_json, strategy_goal_type, strategy_action_type, resource_allocation_json, criticality_review_json, route_comparison_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.trace_id,
                self.session_id or "default",
                self.user_input,
                int(self.ontology_revision),
                self.assistant_reply,
                json.dumps(self.actions_executed),
                self.model_used,
                self.latency_ms,
                self.vram_pressure_at_start,
                self.ram_pressure_at_start,
                self.attention_focus,
                self.belief_confidence,
                self.gate_decision,
                self.prediction_surprisal,
                self.reflection_lesson,
                1 if self.goal_verified else 0,
                self.goal_lifecycle_state,
                json.dumps(self.epistemic_presentation, default=str),
                json.dumps(self.grounding_result, default=str),
                json.dumps(self.retrieved_memories, default=str),
                json.dumps(self.hypothesis_state, default=str),
                json.dumps(self.compute_policy, default=str),
                self.strategy_goal_type,
                self.strategy_action_type,
                json.dumps(self.resource_allocation, default=str),
                json.dumps(self.criticality_review, default=str),
                json.dumps(self.route_comparison, default=str),
                self.created_at
            ))
            conn.commit()
            conn.close()
            audit_logger.info(f"Persisted CognitiveTrace [{self.trace_id[:8]}] (Latency: {self.latency_ms:.0f}ms)")
        except Exception as e:
            app_logger.warning(f"CognitiveTrace persistence notice: {e}")
