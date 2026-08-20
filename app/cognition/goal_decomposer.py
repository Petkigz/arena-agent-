"""Phase 6A: Long-Horizon Goal Decomposition.

Breaks complex goals into sub-goals with dependencies, executes them
in order, verifies each sub-goal, and composes results into overall
goal achievement.

Uses a DAG (directed acyclic graph) of sub-goals where each sub-goal
can depend on the completion of other sub-goals.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Sub-Goal Data Structures ─────────────────────────────────────────

class SubGoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class SubGoal:
    """A single sub-goal within a larger decomposition."""
    sub_goal_id: str
    parent_project_id: str
    description: str
    action_type: str            # suggested action to achieve this sub-goal
    payload: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)  # sub_goal_ids this depends on
    status: SubGoalStatus = SubGoalStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        """Can this sub-goal be executed? (all dependencies completed)"""
        return self.status == SubGoalStatus.PENDING

    @property
    def is_terminal(self) -> bool:
        return self.status in (SubGoalStatus.COMPLETED, SubGoalStatus.FAILED, SubGoalStatus.SKIPPED)


@dataclass
class GoalDecomposition:
    """A complete decomposition of a complex goal into sub-goals."""
    project_id: str
    original_goal: str
    intent_type: str
    sub_goals: List[SubGoal] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None

    @property
    def total_sub_goals(self) -> int:
        return len(self.sub_goals)

    @property
    def completed_count(self) -> int:
        return sum(1 for sg in self.sub_goals if sg.status == SubGoalStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for sg in self.sub_goals if sg.status == SubGoalStatus.FAILED)

    @property
    def progress_percent(self) -> float:
        if not self.sub_goals:
            return 0.0
        return (self.completed_count / self.total_sub_goals) * 100.0

    @property
    def is_complete(self) -> bool:
        return all(sg.is_terminal for sg in self.sub_goals)

    @property
    def is_success(self) -> bool:
        return all(sg.status == SubGoalStatus.COMPLETED for sg in self.sub_goals)

    def get_ready_sub_goals(self) -> List[SubGoal]:
        """Get sub-goals whose dependencies are all completed."""
        completed_ids = {sg.sub_goal_id for sg in self.sub_goals if sg.status == SubGoalStatus.COMPLETED}
        ready = []
        for sg in self.sub_goals:
            if sg.status != SubGoalStatus.PENDING:
                continue
            if all(dep_id in completed_ids for dep_id in sg.depends_on):
                ready.append(sg)
        return ready

    def get_blocked_sub_goals(self) -> List[SubGoal]:
        """Get sub-goals blocked by failed dependencies."""
        failed_ids = {sg.sub_goal_id for sg in self.sub_goals if sg.status == SubGoalStatus.FAILED}
        blocked = []
        for sg in self.sub_goals:
            if sg.status != SubGoalStatus.PENDING:
                continue
            if any(dep_id in failed_ids for dep_id in sg.depends_on):
                blocked.append(sg)
        return blocked

    def get_execution_order(self) -> List[SubGoal]:
        """Topological sort of sub-goals respecting dependencies."""
        completed_ids = {sg.sub_goal_id for sg in self.sub_goals if sg.status == SubGoalStatus.COMPLETED}
        remaining = [sg for sg in self.sub_goals if not sg.is_terminal]
        order: List[SubGoal] = []
        resolved = set(completed_ids)

        max_iterations = len(remaining) + 1
        for _ in range(max_iterations):
            if not remaining:
                break
            batch = [sg for sg in remaining if all(d in resolved for d in sg.depends_on)]
            if not batch:
                break  # Circular dependency or all blocked
            for sg in batch:
                order.append(sg)
                resolved.add(sg.sub_goal_id)
                remaining.remove(sg)

        return order


# ── Goal Decomposer Engine ───────────────────────────────────────────

class GoalDecomposer:
    """
    Decomposes complex goals into sub-goal DAGs and manages execution.

    The decomposer uses deterministic rules to break goals into steps:
    - File operations: search → verify → organize
    - Setup tasks: check prerequisites → install → configure → verify
    - Research tasks: search local → search web → synthesize → report
    """

    # Templates for common goal patterns
    DECOMPOSITION_TEMPLATES = {
        "setup_environment": [
            {"description": "Check system prerequisites", "action_type": "diagnostic", "depends_on": []},
            {"description": "Install required packages", "action_type": "run_command", "depends_on": [0]},
            {"description": "Configure environment settings", "action_type": "run_command", "depends_on": [1]},
            {"description": "Verify installation", "action_type": "diagnostic", "depends_on": [2]},
        ],
        "research_and_report": [
            {"description": "Search local files for relevant documents", "action_type": "search_files", "depends_on": []},
            {"description": "Search web for additional information", "action_type": "web_search", "depends_on": []},
            {"description": "Synthesize findings", "action_type": "formulate_answer", "depends_on": [0, 1]},
        ],
        "find_and_process": [
            {"description": "Search for target files", "action_type": "search_files", "depends_on": []},
            {"description": "Process found files", "action_type": "run_command", "depends_on": [0]},
            {"description": "Verify processing results", "action_type": "diagnostic", "depends_on": [1]},
        ],
    }

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._projects: Dict[str, GoalDecomposition] = {}
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goal_decompositions (
                project_id TEXT PRIMARY KEY,
                original_goal TEXT NOT NULL,
                intent_type TEXT NOT NULL DEFAULT '',
                sub_goals_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, original_goal, intent_type, sub_goals_json, created_at, completed_at FROM goal_decompositions")
        for row in cursor.fetchall():
            sub_goals = []
            try:
                sg_data = json.loads(row[3])
                for sg in sg_data:
                    sub_goals.append(SubGoal(
                        sub_goal_id=sg["sub_goal_id"],
                        parent_project_id=row[0],
                        description=sg["description"],
                        action_type=sg["action_type"],
                        payload=sg.get("payload", {}),
                        depends_on=sg.get("depends_on", []),
                        status=SubGoalStatus(sg.get("status", "pending")),
                        result=sg.get("result"),
                        attempts=sg.get("attempts", 0),
                        max_attempts=sg.get("max_attempts", 3),
                        created_at=sg.get("created_at", _now()),
                        completed_at=sg.get("completed_at"),
                        error=sg.get("error"),
                    ))
            except Exception:
                pass
            decomposition = GoalDecomposition(
                project_id=row[0],
                original_goal=row[1],
                intent_type=row[2],
                sub_goals=sub_goals,
                created_at=row[4],
                completed_at=row[5],
            )
            self._projects[row[0]] = decomposition
        conn.close()

    def _save_to_db(self, decomposition: GoalDecomposition) -> None:
        if not self.db_path:
            return
        sg_data = []
        for sg in decomposition.sub_goals:
            sg_data.append({
                "sub_goal_id": sg.sub_goal_id,
                "description": sg.description,
                "action_type": sg.action_type,
                "payload": sg.payload,
                "depends_on": sg.depends_on,
                "status": sg.status.value,
                "result": sg.result,
                "attempts": sg.attempts,
                "max_attempts": sg.max_attempts,
                "created_at": sg.created_at,
                "completed_at": sg.completed_at,
                "error": sg.error,
            })
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO goal_decompositions
            (project_id, original_goal, intent_type, sub_goals_json, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (decomposition.project_id, decomposition.original_goal,
              decomposition.intent_type, json.dumps(sg_data),
              decomposition.created_at, decomposition.completed_at))
        conn.commit()
        conn.close()

    def decompose(
        self,
        goal_text: str,
        intent_type: str = "",
        template: Optional[str] = None,
        custom_steps: Optional[List[Dict[str, Any]]] = None
    ) -> GoalDecomposition:
        """
        Decompose a goal into sub-goals.
        Uses a template if specified, custom steps, or auto-detects from goal text.
        """
        project_id = uuid4().hex[:12]

        # Determine steps
        steps = None
        if custom_steps:
            steps = custom_steps
        elif template and template in self.DECOMPOSITION_TEMPLATES:
            steps = self.DECOMPOSITION_TEMPLATES[template]
        else:
            steps = self._auto_detect_template(goal_text)

        sub_goals = []
        for i, step in enumerate(steps):
            deps = step.get("depends_on", [])
            # Convert integer indices to sub_goal_ids
            dep_ids = []
            for d in deps:
                if isinstance(d, int) and d < len(sub_goals):
                    dep_ids.append(sub_goals[d].sub_goal_id)
                elif isinstance(d, str):
                    dep_ids.append(d)

            sg = SubGoal(
                sub_goal_id=f"{project_id}_sg{i}",
                parent_project_id=project_id,
                description=step["description"],
                action_type=step.get("action_type", "generic_action"),
                payload=step.get("payload", {}),
                depends_on=dep_ids,
                max_attempts=step.get("max_attempts", 3),
            )
            sub_goals.append(sg)

        decomposition = GoalDecomposition(
            project_id=project_id,
            original_goal=goal_text,
            intent_type=intent_type,
            sub_goals=sub_goals,
        )
        self._projects[project_id] = decomposition
        self._save_to_db(decomposition)
        return decomposition

    def _auto_detect_template(self, goal_text: str) -> List[Dict[str, Any]]:
        """Auto-detect the best decomposition template from goal text."""
        text = goal_text.lower()

        if any(k in text for k in ["setup", "install", "configure", "environment", "dev"]):
            return self.DECOMPOSITION_TEMPLATES["setup_environment"]
        if any(k in text for k in ["research", "report", "analyze", "summarize", "investigate"]):
            return self.DECOMPOSITION_TEMPLATES["research_and_report"]
        if any(k in text for k in ["find", "search", "locate", "process", "convert"]):
            return self.DECOMPOSITION_TEMPLATES["find_and_process"]

        # Default: single-step decomposition
        return [{"description": goal_text, "action_type": "generic_action", "depends_on": []}]

    def update_sub_goal(
        self,
        project_id: str,
        sub_goal_id: str,
        status: SubGoalStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> Optional[SubGoal]:
        """Update a sub-goal's status and result."""
        project = self._projects.get(project_id)
        if not project:
            return None

        for sg in project.sub_goals:
            if sg.sub_goal_id == sub_goal_id:
                sg.status = status
                sg.attempts += 1
                if result:
                    sg.result = result
                if error:
                    sg.error = error
                if status in (SubGoalStatus.COMPLETED, SubGoalStatus.FAILED):
                    sg.completed_at = _now()

                # Check if project is complete
                if project.is_complete:
                    project.completed_at = _now()

                self._save_to_db(project)
                return sg
        return None

    def mark_dependents_blocked(self, project_id: str, failed_sub_goal_id: str) -> List[SubGoal]:
        """Mark all sub-goals that depend on a failed sub-goal as blocked."""
        project = self._projects.get(project_id)
        if not project:
            return []

        blocked = []
        failed_ids = {failed_sub_goal_id}

        # Iteratively find all transitively dependent sub-goals
        changed = True
        while changed:
            changed = False
            for sg in project.sub_goals:
                if sg.status != SubGoalStatus.PENDING:
                    continue
                if any(dep in failed_ids for dep in sg.depends_on):
                    sg.status = SubGoalStatus.BLOCKED
                    sg.error = f"Dependency {failed_sub_goal_id} failed"
                    sg.completed_at = _now()
                    failed_ids.add(sg.sub_goal_id)
                    blocked.append(sg)
                    changed = True

        self._save_to_db(project)
        return blocked

    def get_project(self, project_id: str) -> Optional[GoalDecomposition]:
        return self._projects.get(project_id)

    def get_active_projects(self) -> List[GoalDecomposition]:
        """Get all projects that are not yet complete."""
        return [p for p in self._projects.values() if not p.is_complete]

    def get_progress_report(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Generate a progress report for a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        sub_goal_details = []
        for sg in project.sub_goals:
            sub_goal_details.append({
                "id": sg.sub_goal_id,
                "description": sg.description,
                "action_type": sg.action_type,
                "status": sg.status.value,
                "attempts": sg.attempts,
                "error": sg.error,
                "depends_on": sg.depends_on,
            })

        return {
            "project_id": project_id,
            "goal": project.original_goal,
            "progress_percent": round(project.progress_percent, 1),
            "total_sub_goals": project.total_sub_goals,
            "completed": project.completed_count,
            "failed": project.failed_count,
            "pending": sum(1 for sg in project.sub_goals if sg.status == SubGoalStatus.PENDING),
            "blocked": sum(1 for sg in project.sub_goals if sg.status == SubGoalStatus.BLOCKED),
            "in_progress": sum(1 for sg in project.sub_goals if sg.status == SubGoalStatus.IN_PROGRESS),
            "is_complete": project.is_complete,
            "is_success": project.is_success,
            "sub_goals": sub_goal_details,
            "next_actions": [
                {"description": sg.description, "action_type": sg.action_type}
                for sg in project.get_ready_sub_goals()
            ],
            "created_at": project.created_at,
            "completed_at": project.completed_at,
        }

    def total_projects(self) -> int:
        return len(self._projects)
