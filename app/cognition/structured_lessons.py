"""Phase 1C: Structured Lesson Extraction & Behavior Change.

Extracts deterministic structured lessons from task outcomes without
requiring LLM calls. Lessons are indexed by (task_type, action_type,
failure_type) and influence future strategy selection.

The system can answer "why did this fail before?" and act on the answer
by adjusting CounterfactualSimulator weights and suggesting corrective actions.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Failure Type Classification ────────────────────────────────────────

FAILURE_TYPES = {
    "process_not_running": "Target process was not found running after launch",
    "process_crashed": "Target process started but crashed immediately",
    "file_not_found": "Requested file or resource was not found",
    "gate_blocked": "Action blocked by safety policy gate",
    "evidence_missing": "Insufficient perception evidence to verify outcome",
    "permission_denied": "OS-level permission denied for the action",
    "device_offline": "External device (phone/ADB) was offline or unreachable",
    "timeout": "Action exceeded time bounds",
    "unsupported_command": "Command or capability not recognized",
    "execution_error": "Generic execution error",
    "unknown": "Unable to classify failure cause",
}

CORRECTIVE_ACTIONS = {
    "process_not_running": "Verify application is installed; try alternative launch method",
    "process_crashed": "Check system resources; try relaunch with reduced scope",
    "file_not_found": "Expand search scope; try web_search or diagnostic fallback",
    "gate_blocked": "Request user approval or reduce action risk level",
    "evidence_missing": "Run diagnostic probe to gather evidence before retrying",
    "permission_denied": "Check file permissions or request elevated access",
    "device_offline": "Verify device connectivity before retrying",
    "timeout": "Reduce task scope or use faster model for routine operations",
    "unsupported_command": "Use alternative capability or request user clarification",
    "execution_error": "Retry with different parameters or escalate to user",
    "unknown": "Run investigation probe to gather more evidence",
}


@dataclass(frozen=True)
class StructuredLesson:
    """A deterministic lesson extracted from a task outcome."""
    lesson_id: str
    task_type: str              # e.g. "action_intent", "search_intent"
    action_type: str            # e.g. "open_application", "search_files"
    outcome: str                # "success", "failed", "blocked", "deferred", "waiting_for_evidence"
    failure_type: str           # classified failure cause (empty for success)
    root_cause: str             # human-readable explanation
    corrective_action: str      # what to try differently next time
    goal_text: str              # original user request (truncated)
    confidence: float           # how confident in this lesson (0.0-1.0)
    latency_ms: float           # how long the task took
    surprisal: float            # prediction error
    timestamp: str = field(default_factory=_now)


class LessonStore:
    """
    SQLite-backed store for structured lessons.
    Indexes lessons by (task_type, action_type, failure_type) for fast retrieval.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._lessons: List[StructuredLesson] = []
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS structured_lessons (
                lesson_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                action_type TEXT NOT NULL,
                outcome TEXT NOT NULL,
                failure_type TEXT NOT NULL DEFAULT '',
                root_cause TEXT NOT NULL DEFAULT '',
                corrective_action TEXT NOT NULL DEFAULT '',
                goal_text TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.5,
                latency_ms REAL NOT NULL DEFAULT 0.0,
                surprisal REAL NOT NULL DEFAULT 0.0,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lessons_task_action
            ON structured_lessons(task_type, action_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lessons_failure_type
            ON structured_lessons(failure_type)
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""SELECT lesson_id, task_type, action_type, outcome, failure_type,
            root_cause, corrective_action, goal_text, confidence, latency_ms, surprisal, timestamp
            FROM structured_lessons ORDER BY timestamp""")
        for row in cursor.fetchall():
            self._lessons.append(StructuredLesson(
                lesson_id=row[0], task_type=row[1], action_type=row[2],
                outcome=row[3], failure_type=row[4], root_cause=row[5],
                corrective_action=row[6], goal_text=row[7], confidence=row[8],
                latency_ms=row[9], surprisal=row[10], timestamp=row[11]
            ))
        conn.close()

    def _save_to_db(self, lesson: StructuredLesson) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO structured_lessons
            (lesson_id, task_type, action_type, outcome, failure_type,
             root_cause, corrective_action, goal_text, confidence, latency_ms, surprisal, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (lesson.lesson_id, lesson.task_type, lesson.action_type,
              lesson.outcome, lesson.failure_type, lesson.root_cause,
              lesson.corrective_action, lesson.goal_text, lesson.confidence,
              lesson.latency_ms, lesson.surprisal, lesson.timestamp))
        conn.commit()
        conn.close()

    # ── Deterministic Lesson Extraction ────────────────────────────────

    @classmethod
    def classify_failure_type(
        cls,
        final_state: str,
        failed_conditions: List[str],
        reply_text: str,
        action_type: str = ""
    ) -> str:
        """
        Deterministically classify why a task failed based on verification results.
        No LLM required — uses structured signals from GoalVerifier.
        """
        reply_lower = reply_text.lower()
        state_lower = final_state.lower() if final_state else ""

        # State-based classification
        if "blocked" in state_lower:
            return "gate_blocked"
        if "waiting_for_evidence" in state_lower or "unknown" in state_lower:
            return "evidence_missing"
        if "deferred" in state_lower:
            return "evidence_missing"

        # Reply-text-based classification (ordered by specificity)
        if any(k in reply_lower for k in ["crashed", "segfault", "fatal error", "core dumped"]):
            return "process_crashed"
        if any(k in reply_lower for k in ["permission denied", "access denied", "eacces"]):
            return "permission_denied"
        if any(k in reply_lower for k in ["device offline", "no devices", "device not found"]):
            return "device_offline"
        if any(k in reply_lower for k in ["timed out", "timeout", "deadline exceeded"]):
            return "timeout"
        if any(k in reply_lower for k in ["unsupported", "not recognized", "unknown command"]):
            return "unsupported_command"
        if any(k in reply_lower for k in ["not found", "no such file", "does not exist", "file not found"]):
            return "file_not_found"
        if any(k in reply_lower for k in ["not running", "process not found", "cannot find application"]):
            return "process_not_running"

        # Failed conditions analysis
        for fc in failed_conditions:
            fc_lower = fc.lower()
            if "process" in fc_lower and ("running" in fc_lower or "not_running" in fc_lower):
                return "process_not_running"
            if "file" in fc_lower and ("found" in fc_lower or "path" in fc_lower):
                return "file_not_found"
            if "blocked" in fc_lower:
                return "gate_blocked"

        return "execution_error" if "failed" in state_lower else "unknown"

    def extract_lesson(
        self,
        task_type: str,
        action_type: str,
        final_state: str,
        verified_success: bool,
        failed_conditions: List[str],
        reply_text: str,
        goal_text: str = "",
        latency_ms: float = 0.0,
        surprisal: float = 0.0
    ) -> StructuredLesson:
        """
        Extract a structured lesson from a task outcome.
        Works for both successes and failures.
        """
        if verified_success:
            outcome = "success"
            failure_type = ""
            root_cause = ""
            corrective_action = ""
            confidence = 0.8
        else:
            failure_type = self.classify_failure_type(
                final_state, failed_conditions, reply_text, action_type
            )
            outcome = final_state.lower() if final_state else "failed"
            root_cause = FAILURE_TYPES.get(failure_type, "Unknown failure")
            corrective_action = CORRECTIVE_ACTIONS.get(failure_type, "Investigate further")
            # Higher surprisal = more surprising failure = more valuable lesson
            confidence = min(1.0, 0.5 + surprisal * 0.5)

        lesson = StructuredLesson(
            lesson_id=uuid4().hex[:12],
            task_type=task_type,
            action_type=action_type,
            outcome=outcome,
            failure_type=failure_type,
            root_cause=root_cause,
            corrective_action=corrective_action,
            goal_text=goal_text[:200],
            confidence=confidence,
            latency_ms=latency_ms,
            surprisal=surprisal
        )
        self._lessons.append(lesson)
        self._save_to_db(lesson)
        return lesson

    # ── Query Interface ────────────────────────────────────────────────

    def query_lessons(
        self,
        task_type: Optional[str] = None,
        action_type: Optional[str] = None,
        failure_type: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 10
    ) -> List[StructuredLesson]:
        """Query lessons by any combination of filters."""
        results = self._lessons
        if task_type:
            results = [l for l in results if l.task_type == task_type]
        if action_type:
            results = [l for l in results if l.action_type == action_type]
        if failure_type:
            results = [l for l in results if l.failure_type == failure_type]
        if outcome:
            results = [l for l in results if l.outcome == outcome]
        return results[-limit:]

    def query_failures(
        self, task_type: str, action_type: Optional[str] = None
    ) -> List[StructuredLesson]:
        """Get all failure lessons for a task type, optionally filtered by action."""
        results = [
            l for l in self._lessons
            if l.task_type == task_type and l.outcome != "success"
        ]
        if action_type:
            results = [l for l in results if l.action_type == action_type]
        return results

    def what_went_wrong(self, task_type: str, action_type: str) -> Optional[Dict[str, Any]]:
        """
        Answer: 'Why did this fail before?'
        Returns the most recent failure lesson with context.
        """
        failures = self.query_failures(task_type, action_type)
        if not failures:
            return None

        latest = failures[-1]
        return {
            "failure_type": latest.failure_type,
            "root_cause": latest.root_cause,
            "corrective_action": latest.corrective_action,
            "times_failed": len(failures),
            "last_failure": latest.timestamp,
            "goal_text": latest.goal_text,
            "confidence": latest.confidence,
        }

    def corrective_suggestion(self, task_type: str, action_type: str) -> Optional[str]:
        """Get the most relevant corrective action for a strategy."""
        info = self.what_went_wrong(task_type, action_type)
        if info:
            return info["corrective_action"]
        return None

    def lesson_influence(self, task_type: str, action_type: str) -> float:
        """
        Return a weight adjustment for CounterfactualSimulator based on lessons.
        - No failure lessons → 1.0 (neutral)
        - Few failures → mild penalty
        - Repeated failures of same type → strong penalty
        - Mixed failure types → moderate penalty
        """
        failures = self.query_failures(task_type, action_type)
        if not failures:
            return 1.0

        # Count by failure type
        type_counts: Dict[str, int] = {}
        for f in failures:
            type_counts[f.failure_type] = type_counts.get(f.failure_type, 0) + 1

        total = len(failures)
        max_type_count = max(type_counts.values())

        # Repeated same-type failures are worse than diverse failures
        repetition_factor = max_type_count / total

        # Base penalty from total failures (capped)
        base_penalty = min(0.3, total * 0.05)

        # Extra penalty for repeated same-type failures
        repetition_penalty = repetition_factor * min(0.2, total * 0.03)

        adjustment = 1.0 - base_penalty - repetition_penalty
        return max(0.3, min(1.0, adjustment))

    def total_lessons(self) -> int:
        return len(self._lessons)

    def failure_summary(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """Summary of all failure patterns."""
        failures = [l for l in self._lessons if l.outcome != "success"]
        if task_type:
            failures = [l for l in failures if l.task_type == task_type]

        type_counts: Dict[str, int] = {}
        action_counts: Dict[str, int] = {}
        for f in failures:
            type_counts[f.failure_type] = type_counts.get(f.failure_type, 0) + 1
            action_counts[f.action_type] = action_counts.get(f.action_type, 0) + 1

        return {
            "total_failures": len(failures),
            "by_failure_type": type_counts,
            "by_action_type": action_counts,
            "most_common_failure": max(type_counts, key=type_counts.get) if type_counts else None,
            "most_failing_action": max(action_counts, key=action_counts.get) if action_counts else None,
        }
