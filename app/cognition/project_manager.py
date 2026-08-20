"""Phase 6B: Multi-Session Project Management.

Projects span multiple sessions with persistent state. Progress is tracked
across sessions and context is restored on resume.

A Project is a high-level container for related work that persists across
multiple cognitive sessions. It tracks milestones, decisions, and context
so the system can pick up where it left off.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Project Data Structures ──────────────────────────────────────────

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


@dataclass
class Milestone:
    """A significant checkpoint in a project."""
    milestone_id: str
    description: str
    status: str = "pending"     # pending, reached, skipped
    reached_at: Optional[str] = None
    notes: str = ""


@dataclass
class SessionRecord:
    """Record of work done in a single session."""
    session_id: str
    started_at: str
    ended_at: Optional[str] = None
    tasks_completed: List[str] = field(default_factory=list)
    tasks_failed: List[str] = field(default_factory=list)
    decisions_made: List[str] = field(default_factory=list)
    notes: str = ""
    duration_ms: float = 0.0


@dataclass
class Project:
    """A persistent project that spans multiple sessions."""
    project_id: str
    name: str
    description: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    priority: str = "normal"    # low, normal, high, critical
    milestones: List[Milestone] = field(default_factory=list)
    sessions: List[SessionRecord] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)  # free-form context
    tags: List[str] = field(default_factory=list)
    decomposition_id: Optional[str] = None  # linked GoalDecomposition
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    @property
    def total_tasks_completed(self) -> int:
        return sum(len(s.tasks_completed) for s in self.sessions)

    @property
    def total_tasks_failed(self) -> int:
        return sum(len(s.tasks_failed) for s in self.sessions)

    @property
    def milestones_reached(self) -> int:
        return sum(1 for m in self.milestones if m.status == "reached")

    @property
    def milestones_total(self) -> int:
        return len(self.milestones)

    @property
    def progress_percent(self) -> float:
        if not self.milestones:
            return 0.0
        return (self.milestones_reached / self.milestones_total) * 100.0

    @property
    def current_session(self) -> Optional[SessionRecord]:
        """Get the active (un-ended) session, if any."""
        for s in reversed(self.sessions):
            if s.ended_at is None:
                return s
        return None


# ── Project Manager ──────────────────────────────────────────────────

class ProjectManager:
    """
    Manages persistent projects that span multiple sessions.
    Projects survive across restarts and track all progress.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._projects: Dict[str, Project] = {}
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                priority TEXT NOT NULL DEFAULT 'normal',
                milestones_json TEXT NOT NULL DEFAULT '[]',
                sessions_json TEXT NOT NULL DEFAULT '[]',
                context_json TEXT NOT NULL DEFAULT '{}',
                tags_json TEXT NOT NULL DEFAULT '[]',
                decomposition_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""SELECT project_id, name, description, status, priority,
            milestones_json, sessions_json, context_json, tags_json,
            decomposition_id, created_at, updated_at, completed_at
            FROM projects ORDER BY updated_at DESC""")
        for row in cursor.fetchall():
            milestones = []
            for m in json.loads(row[5] or "[]"):
                milestones.append(Milestone(
                    milestone_id=m["milestone_id"],
                    description=m["description"],
                    status=m.get("status", "pending"),
                    reached_at=m.get("reached_at"),
                    notes=m.get("notes", ""),
                ))
            sessions = []
            for s in json.loads(row[6] or "[]"):
                sessions.append(SessionRecord(
                    session_id=s["session_id"],
                    started_at=s["started_at"],
                    ended_at=s.get("ended_at"),
                    tasks_completed=s.get("tasks_completed", []),
                    tasks_failed=s.get("tasks_failed", []),
                    decisions_made=s.get("decisions_made", []),
                    notes=s.get("notes", ""),
                    duration_ms=s.get("duration_ms", 0),
                ))
            project = Project(
                project_id=row[0],
                name=row[1],
                description=row[2],
                status=ProjectStatus(row[3]),
                priority=row[4],
                milestones=milestones,
                sessions=sessions,
                context=json.loads(row[7] or "{}"),
                tags=json.loads(row[8] or "[]"),
                decomposition_id=row[9],
                created_at=row[10],
                updated_at=row[11],
                completed_at=row[12],
            )
            self._projects[row[0]] = project
        conn.close()

    def _save_to_db(self, project: Project) -> None:
        if not self.db_path:
            return
        ms_json = json.dumps([{
            "milestone_id": m.milestone_id,
            "description": m.description,
            "status": m.status,
            "reached_at": m.reached_at,
            "notes": m.notes,
        } for m in project.milestones])
        sess_json = json.dumps([{
            "session_id": s.session_id,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "tasks_completed": s.tasks_completed,
            "tasks_failed": s.tasks_failed,
            "decisions_made": s.decisions_made,
            "notes": s.notes,
            "duration_ms": s.duration_ms,
        } for s in project.sessions])
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO projects
            (project_id, name, description, status, priority, milestones_json,
             sessions_json, context_json, tags_json, decomposition_id,
             created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project.project_id, project.name, project.description,
              project.status.value, project.priority, ms_json, sess_json,
              json.dumps(project.context), json.dumps(project.tags),
              project.decomposition_id, project.created_at, project.updated_at,
              project.completed_at))
        conn.commit()
        conn.close()

    def create_project(
        self,
        name: str,
        description: str = "",
        priority: str = "normal",
        milestones: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        decomposition_id: Optional[str] = None
    ) -> Project:
        """Create a new project."""
        project_id = uuid4().hex[:12]
        ms = []
        if milestones:
            for desc in milestones:
                ms.append(Milestone(
                    milestone_id=uuid4().hex[:8],
                    description=desc,
                ))

        project = Project(
            project_id=project_id,
            name=name,
            description=description,
            priority=priority,
            milestones=ms,
            tags=tags or [],
            context=context or {},
            decomposition_id=decomposition_id,
        )
        self._projects[project_id] = project
        self._save_to_db(project)
        return project

    def start_session(self, project_id: str) -> Optional[SessionRecord]:
        """Start a new work session within a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        session = SessionRecord(
            session_id=uuid4().hex[:8],
            started_at=_now(),
        )
        project.sessions.append(session)
        project.updated_at = _now()
        self._save_to_db(project)
        return session

    def end_session(
        self,
        project_id: str,
        session_id: str,
        notes: str = ""
    ) -> Optional[SessionRecord]:
        """End a work session."""
        project = self._projects.get(project_id)
        if not project:
            return None

        for session in project.sessions:
            if session.session_id == session_id:
                session.ended_at = _now()
                session.notes = notes
                if session.started_at:
                    try:
                        start = datetime.fromisoformat(session.started_at)
                        end = datetime.fromisoformat(session.ended_at)
                        session.duration_ms = (end - start).total_seconds() * 1000
                    except Exception:
                        pass
                project.updated_at = _now()
                self._save_to_db(project)
                return session
        return None

    def record_task_completion(
        self, project_id: str, session_id: str, task_description: str
    ) -> bool:
        """Record a completed task in a session."""
        project = self._projects.get(project_id)
        if not project:
            return False
        for session in project.sessions:
            if session.session_id == session_id:
                session.tasks_completed.append(task_description)
                project.updated_at = _now()
                self._save_to_db(project)
                return True
        return False

    def record_task_failure(
        self, project_id: str, session_id: str, task_description: str
    ) -> bool:
        """Record a failed task in a session."""
        project = self._projects.get(project_id)
        if not project:
            return False
        for session in project.sessions:
            if session.session_id == session_id:
                session.tasks_failed.append(task_description)
                project.updated_at = _now()
                self._save_to_db(project)
                return True
        return False

    def record_decision(
        self, project_id: str, session_id: str, decision: str
    ) -> bool:
        """Record a decision made during a session."""
        project = self._projects.get(project_id)
        if not project:
            return False
        for session in project.sessions:
            if session.session_id == session_id:
                session.decisions_made.append(decision)
                project.updated_at = _now()
                self._save_to_db(project)
                return True
        return False

    def reach_milestone(self, project_id: str, milestone_id: str, notes: str = "") -> bool:
        """Mark a milestone as reached."""
        project = self._projects.get(project_id)
        if not project:
            return False
        for ms in project.milestones:
            if ms.milestone_id == milestone_id:
                ms.status = "reached"
                ms.reached_at = _now()
                ms.notes = notes
                project.updated_at = _now()
                self._save_to_db(project)
                return True
        return False

    def update_context(self, project_id: str, context: Dict[str, Any]) -> bool:
        """Update project context (merge with existing)."""
        project = self._projects.get(project_id)
        if not project:
            return False
        project.context.update(context)
        project.updated_at = _now()
        self._save_to_db(project)
        return True

    def complete_project(self, project_id: str) -> bool:
        """Mark a project as completed."""
        project = self._projects.get(project_id)
        if not project:
            return False
        project.status = ProjectStatus.COMPLETED
        project.completed_at = _now()
        project.updated_at = _now()
        self._save_to_db(project)
        return True

    def get_resume_context(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate context needed to resume a project in a new session.
        Includes: last session summary, pending milestones, project context.
        """
        project = self._projects.get(project_id)
        if not project:
            return None

        last_session = project.sessions[-1] if project.sessions else None
        pending_milestones = [m for m in project.milestones if m.status == "pending"]

        return {
            "project_id": project_id,
            "project_name": project.name,
            "description": project.description,
            "status": project.status.value,
            "progress_percent": round(project.progress_percent, 1),
            "total_sessions": project.total_sessions,
            "last_session": {
                "tasks_completed": last_session.tasks_completed if last_session else [],
                "tasks_failed": last_session.tasks_failed if last_session else [],
                "decisions": last_session.decisions_made if last_session else [],
                "notes": last_session.notes if last_session else "",
            } if last_session else None,
            "pending_milestones": [m.description for m in pending_milestones],
            "context": project.context,
            "tags": project.tags,
            "total_completed": project.total_tasks_completed,
            "total_failed": project.total_tasks_failed,
        }

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def get_active_projects(self) -> List[Project]:
        return [p for p in self._projects.values() if p.status == ProjectStatus.ACTIVE]

    def get_projects_by_tag(self, tag: str) -> List[Project]:
        return [p for p in self._projects.values() if tag in p.tags]

    def total_projects(self) -> int:
        return len(self._projects)
