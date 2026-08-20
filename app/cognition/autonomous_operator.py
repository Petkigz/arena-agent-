"""Phase 6C: Autonomous Operation with Oversight.

Manages autonomous execution of approved task classes with periodic
progress reporting and escalation when uncertain or blocked.

The operator:
- Runs approved task classes without asking for permission each time
- Reports progress at configurable intervals
- Escalates to the owner when blocked, uncertain, or hitting policy limits
- Maintains an audit trail of all autonomous decisions
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Autonomous Operation Data Structures ─────────────────────────────

class EscalationReason(str, Enum):
    BLOCKED = "blocked"                     # Cannot proceed (gate, permission, resource)
    UNCERTAIN = "uncertain"                 # Low confidence, needs human judgment
    REPEATED_FAILURE = "repeated_failure"   # Same task failed multiple times
    POLICY_LIMIT = "policy_limit"           # Hit a configured limit
    NOVEL_SITUATION = "novel_situation"     # Encountered something never seen before
    RESOURCE_EXHAUSTED = "resource_exhausted"  # Budget/time/attempt limit reached
    OWNER_REQUESTED = "owner_requested"     # Owner explicitly asked for review


class TaskApproval(str, Enum):
    APPROVED = "approved"           # Can run autonomously
    REQUIRES_APPROVAL = "requires_approval"  # Needs owner confirmation
    DENIED = "denied"              # Not allowed


@dataclass(frozen=True)
class AutonomousTask:
    """A task queued for autonomous execution."""
    task_id: str
    description: str
    action_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: str = "normal"    # low, normal, high, critical
    project_id: Optional[str] = None
    approval: TaskApproval = TaskApproval.APPROVED
    created_at: str = field(default_factory=_now)


@dataclass
class ProgressReport:
    """Periodic progress report during autonomous operation."""
    report_id: str
    project_id: Optional[str]
    period_start: str
    period_end: str
    tasks_completed: int
    tasks_failed: int
    tasks_pending: int
    current_task: Optional[str]
    overall_progress: float     # 0.0-1.0
    issues: List[str] = field(default_factory=list)
    next_planned: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)


@dataclass
class Escalation:
    """An escalation to the owner for human intervention."""
    escalation_id: str
    task_id: Optional[str]
    project_id: Optional[str]
    reason: EscalationReason
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""
    resolved: bool = False
    resolution: Optional[str] = None
    created_at: str = field(default_factory=_now)
    resolved_at: Optional[str] = None


@dataclass
class AuditEntry:
    """Audit trail entry for autonomous decisions."""
    entry_id: str
    timestamp: str
    decision_type: str       # "execute", "skip", "escalate", "approve", "retry"
    task_id: Optional[str]
    description: str
    confidence: float = 0.0
    reasoning: str = ""


# ── Autonomous Operator ──────────────────────────────────────────────

class AutonomousOperator:
    """
    Manages autonomous task execution with oversight.

    Configuration:
    - approved_actions: set of action_types that can run without approval
    - max_consecutive_failures: escalate after this many failures
    - report_interval_tasks: report progress every N tasks
    - max_autonomous_duration_ms: max time before mandatory check-in
    """

    DEFAULT_APPROVED_ACTIONS = {
        "search_files", "web_search", "diagnostic", "investigate",
        "formulate_answer", "knowledge_query",
    }

    def __init__(
        self,
        db_path: Optional[str] = None,
        approved_actions: Optional[Set[str]] = None,
        max_consecutive_failures: int = 3,
        report_interval_tasks: int = 5,
        max_autonomous_duration_ms: int = 300000,  # 5 minutes
    ) -> None:
        self.db_path = db_path
        self._approved_actions = approved_actions or set(self.DEFAULT_APPROVED_ACTIONS)
        self._max_consecutive_failures = max_consecutive_failures
        self._report_interval = report_interval_tasks
        self._max_duration_ms = max_autonomous_duration_ms

        self._task_queue: List[AutonomousTask] = []
        self._completed: List[AutonomousTask] = []
        self._failed: List[AutonomousTask] = []
        self._escalations: List[Escalation] = []
        self._audit_log: List[AuditEntry] = []
        self._reports: List[ProgressReport] = []
        self._consecutive_failures: int = 0
        self._tasks_since_report: int = 0
        self._session_start: Optional[str] = None
        self._is_operating: bool = False

        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_audit (
                entry_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                task_id TEXT,
                description TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                reasoning TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_escalations (
                escalation_id TEXT PRIMARY KEY,
                task_id TEXT,
                project_id TEXT,
                reason TEXT NOT NULL,
                description TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                suggested_action TEXT NOT NULL DEFAULT '',
                resolved INTEGER NOT NULL DEFAULT 0,
                resolution TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT entry_id, timestamp, decision_type, task_id, description, confidence, reasoning FROM autonomous_audit ORDER BY timestamp")
        for row in cursor.fetchall():
            self._audit_log.append(AuditEntry(
                entry_id=row[0], timestamp=row[1], decision_type=row[2],
                task_id=row[3], description=row[4], confidence=row[5], reasoning=row[6]
            ))
        cursor.execute("SELECT escalation_id, task_id, project_id, reason, description, context_json, suggested_action, resolved, resolution, created_at, resolved_at FROM autonomous_escalations ORDER BY created_at")
        for row in cursor.fetchall():
            self._escalations.append(Escalation(
                escalation_id=row[0], task_id=row[1], project_id=row[2],
                reason=EscalationReason(row[3]), description=row[4],
                context=json.loads(row[5] or "{}"), suggested_action=row[6],
                resolved=bool(row[7]), resolution=row[8],
                created_at=row[9], resolved_at=row[10]
            ))
        conn.close()

    def _save_audit(self, entry: AuditEntry) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""INSERT OR REPLACE INTO autonomous_audit
            (entry_id, timestamp, decision_type, task_id, description, confidence, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entry.entry_id, entry.timestamp, entry.decision_type, entry.task_id,
             entry.description, entry.confidence, entry.reasoning))
        conn.commit()
        conn.close()

    def _save_escalation(self, esc: Escalation) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""INSERT OR REPLACE INTO autonomous_escalations
            (escalation_id, task_id, project_id, reason, description, context_json,
             suggested_action, resolved, resolution, created_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (esc.escalation_id, esc.task_id, esc.project_id, esc.reason.value,
             esc.description, json.dumps(esc.context), esc.suggested_action,
             int(esc.resolved), esc.resolution, esc.created_at, esc.resolved_at))
        conn.commit()
        conn.close()

    def _audit(self, decision_type: str, description: str,
               task_id: Optional[str] = None, confidence: float = 0.0,
               reasoning: str = "") -> AuditEntry:
        entry = AuditEntry(
            entry_id=uuid4().hex[:12],
            timestamp=_now(),
            decision_type=decision_type,
            task_id=task_id,
            description=description,
            confidence=confidence,
            reasoning=reasoning,
        )
        self._audit_log.append(entry)
        self._save_audit(entry)
        return entry

    # ── Task Approval ─────────────────────────────────────────────────

    def check_approval(self, action_type: str) -> TaskApproval:
        """Check if an action type is approved for autonomous execution."""
        if action_type in self._approved_actions:
            return TaskApproval.APPROVED
        return TaskApproval.REQUIRES_APPROVAL

    def approve_action(self, action_type: str) -> None:
        """Add an action type to the approved set."""
        self._approved_actions.add(action_type)
        self._audit("approve", f"Approved '{action_type}' for autonomous execution")

    def deny_action(self, action_type: str) -> None:
        """Explicitly deny an action type."""
        self._approved_actions.discard(action_type)
        self._audit("deny", f"Denied '{action_type}' for autonomous execution")

    # ── Task Queue Management ─────────────────────────────────────────

    def queue_task(
        self,
        description: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        project_id: Optional[str] = None
    ) -> AutonomousTask:
        """Add a task to the autonomous execution queue."""
        approval = self.check_approval(action_type)
        task = AutonomousTask(
            task_id=uuid4().hex[:12],
            description=description,
            action_type=action_type,
            payload=payload or {},
            priority=priority,
            project_id=project_id,
            approval=approval,
        )
        self._task_queue.append(task)
        self._audit("queue", f"Queued task: {description}", task_id=task.task_id)
        return task

    def get_next_task(self) -> Optional[AutonomousTask]:
        """Get the next approved task from the queue (highest priority first)."""
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        approved = [t for t in self._task_queue if t.approval == TaskApproval.APPROVED]
        if not approved:
            return None
        approved.sort(key=lambda t: priority_order.get(t.priority, 2))
        return approved[0]

    def get_pending_approval_tasks(self) -> List[AutonomousTask]:
        """Get tasks waiting for owner approval."""
        return [t for t in self._task_queue if t.approval == TaskApproval.REQUIRES_APPROVAL]

    # ── Task Completion / Failure ─────────────────────────────────────

    def record_completion(self, task_id: str, result: Optional[Dict] = None) -> bool:
        """Record a task as completed."""
        for i, task in enumerate(self._task_queue):
            if task.task_id == task_id:
                self._task_queue.pop(i)
                self._completed.append(task)
                self._consecutive_failures = 0
                self._tasks_since_report += 1
                self._audit("execute", f"Completed: {task.description}",
                           task_id=task_id, confidence=1.0)
                return True
        return False

    def record_failure(self, task_id: str, error: str = "") -> Optional[Escalation]:
        """Record a task as failed. May trigger escalation."""
        for i, task in enumerate(self._task_queue):
            if task.task_id == task_id:
                self._task_queue.pop(i)
                self._failed.append(task)
                self._consecutive_failures += 1
                self._tasks_since_report += 1
                self._audit("execute", f"Failed: {task.description} — {error}",
                           task_id=task_id, confidence=0.0)

                # Check escalation conditions
                if self._consecutive_failures >= self._max_consecutive_failures:
                    return self._escalate(
                        task_id=task_id,
                        project_id=task.project_id,
                        reason=EscalationReason.REPEATED_FAILURE,
                        description=f"{self._consecutive_failures} consecutive task failures",
                        context={"failed_tasks": [t.description for t in self._failed[-self._max_consecutive_failures:]]},
                        suggested_action="Review failed tasks and adjust strategy"
                    )
                return None
        return None

    # ── Escalation ───────────────────────────────────────────────────

    def escalate(
        self,
        reason: EscalationReason,
        description: str,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
        context: Optional[Dict] = None,
        suggested_action: str = ""
    ) -> Escalation:
        """Manually escalate to the owner."""
        return self._escalate(task_id, project_id, reason, description, context or {}, suggested_action)

    def _escalate(
        self, task_id, project_id, reason, description, context, suggested_action
    ) -> Escalation:
        esc = Escalation(
            escalation_id=uuid4().hex[:12],
            task_id=task_id,
            project_id=project_id,
            reason=reason,
            description=description,
            context=context,
            suggested_action=suggested_action,
        )
        self._escalations.append(esc)
        self._save_escalation(esc)
        self._audit("escalate", f"Escalation: {description}",
                    task_id=task_id, reasoning=reason.value)
        return esc

    def resolve_escalation(self, escalation_id: str, resolution: str) -> bool:
        """Resolve an escalation (owner has addressed the issue)."""
        for esc in self._escalations:
            if esc.escalation_id == escalation_id:
                esc.resolved = True
                esc.resolution = resolution
                esc.resolved_at = _now()
                self._save_escalation(esc)
                self._audit("resolve", f"Resolved escalation: {resolution}",
                           task_id=esc.task_id)
                self._consecutive_failures = 0  # Reset on resolution
                return True
        return False

    # ── Progress Reporting ────────────────────────────────────────────

    def should_report(self) -> bool:
        """Check if a progress report is due."""
        return self._tasks_since_report >= self._report_interval

    def generate_report(self, project_id: Optional[str] = None) -> ProgressReport:
        """Generate a progress report."""
        report = ProgressReport(
            report_id=uuid4().hex[:12],
            project_id=project_id,
            period_start=self._session_start or _now(),
            period_end=_now(),
            tasks_completed=len(self._completed),
            tasks_failed=len(self._failed),
            tasks_pending=len(self._task_queue),
            current_task=self._task_queue[0].description if self._task_queue else None,
            overall_progress=self._compute_progress(),
            issues=[f"{self._consecutive_failures} consecutive failures"] if self._consecutive_failures > 0 else [],
            next_planned=[t.description for t in self._task_queue[:3]],
        )
        self._reports.append(report)
        self._tasks_since_report = 0
        return report

    def _compute_progress(self) -> float:
        total = len(self._completed) + len(self._failed) + len(self._task_queue)
        if total == 0:
            return 0.0
        return len(self._completed) / total

    # ── Session Management ────────────────────────────────────────────

    def start_autonomous_session(self) -> None:
        """Start an autonomous operation session."""
        self._session_start = _now()
        self._is_operating = True
        self._audit("session_start", "Autonomous operation session started")

    def stop_autonomous_session(self, reason: str = "completed") -> None:
        """Stop the autonomous operation session."""
        self._is_operating = False
        self._audit("session_end", f"Autonomous session ended: {reason}")

    @property
    def is_operating(self) -> bool:
        return self._is_operating

    # ── Status Queries ────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get current autonomous operation status."""
        unresolved = [e for e in self._escalations if not e.resolved]
        return {
            "is_operating": self._is_operating,
            "queue_size": len(self._task_queue),
            "approved_in_queue": len([t for t in self._task_queue if t.approval == TaskApproval.APPROVED]),
            "pending_approval": len([t for t in self._task_queue if t.approval == TaskApproval.REQUIRES_APPROVAL]),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "consecutive_failures": self._consecutive_failures,
            "unresolved_escalations": len(unresolved),
            "total_audit_entries": len(self._audit_log),
            "reports_generated": len(self._reports),
            "approved_actions": sorted(self._approved_actions),
        }

    def get_audit_trail(self, limit: int = 50) -> List[AuditEntry]:
        return self._audit_log[-limit:]

    def get_unresolved_escalations(self) -> List[Escalation]:
        return [e for e in self._escalations if not e.resolved]
