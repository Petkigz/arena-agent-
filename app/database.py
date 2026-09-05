import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from app.config import settings
from app.utils.logger import app_logger

class DatabaseManager:
    def __init__(self, db_path: str = str(settings.DB_PATH)):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Create Tasks Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    plan TEXT,  -- JSON serialized list of steps
                    current_step INTEGER DEFAULT 0,
                    checkpoint TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # 2. Create Memories Table (SQLite-based permanent storage)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    last_reviewed TEXT NOT NULL
                )
            """)
            
            # 3. Create Audit Logs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT,
                    level INTEGER DEFAULT 0
                )
            """)

            # 4. Create Conversations Table (persistent chat history)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_conv ON conversations(conversation_id)")

            # 5. Create Project Tasks Table (Kanban tasks inside projects, synced
            # across all UIs — web, desktop, Android all read/write this store).
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'todo',
                    priority TEXT NOT NULL DEFAULT 'medium',
                    assignee TEXT DEFAULT '',
                    due_date TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_tasks_project ON project_tasks(project_id)")

            conn.commit()
            app_logger.info("SQLite database initialized successfully.")

    # Task CRUD operations
    def create_task(self, task_data: Dict[str, Any]) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            plan_json = json.dumps(task_data.get("plan", []))
            now = datetime.utcnow().isoformat()
            
            cursor.execute("""
                INSERT INTO tasks (id, title, goal, status, priority, plan, current_step, checkpoint, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_data["id"],
                task_data["title"],
                task_data["goal"],
                task_data.get("status", "queued"),
                task_data.get("priority", "medium"),
                plan_json,
                task_data.get("current_step", 0),
                task_data.get("checkpoint", ""),
                task_data.get("created_at", now),
                task_data.get("updated_at", now)
            ))
            conn.commit()
            return True

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                res = dict(row)
                res["plan"] = json.loads(res["plan"]) if res["plan"] else []
                return res
            return None

    def get_all_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
                cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            rows = cursor.fetchall()
            tasks = []
            for row in rows:
                t = dict(row)
                t["plan"] = json.loads(t["plan"]) if t["plan"] else []
                tasks.append(t)
            return tasks

    # Allowed columns for task updates (whitelist to prevent SQL injection)
    _TASK_UPDATE_COLUMNS = {
        "title", "description", "status", "priority", "plan",
        "checkpoint", "tags", "updated_at", "due_date", "assignee",
        "current_step",
    }

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            set_parts = []
            params = []
            for k, v in updates.items():
                if k not in self._TASK_UPDATE_COLUMNS:
                    continue  # Skip unknown columns to prevent SQL injection
                if k == "plan":
                    set_parts.append("plan = ?")
                    params.append(json.dumps(v))
                elif k == "tags":
                    set_parts.append("tags = ?")
                    params.append(json.dumps(v) if isinstance(v, list) else v)
                else:
                    set_parts.append(f"{k} = ?")
                    params.append(v)
            
            if not set_parts:
                return False

            params.append(task_id)
            query = f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    # Memory Operations
    def create_memory(self, memory_data: Dict[str, Any]) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO memories (content, category, source, confidence, created_at, last_reviewed)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                memory_data["content"],
                memory_data["category"],
                memory_data.get("source", "user"),
                memory_data.get("confidence", 1.0),
                now,
                now
            ))
            conn.commit()
            return cursor.lastrowid

    def get_memories(
        self,
        category: Optional[str] = None,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return memories newest-first, optionally as a deterministic page."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            params: List[Any] = []
            query = "SELECT * FROM memories"
            if category:
                query += " WHERE category = ?"
                params.append(category)
            query += " ORDER BY last_reviewed DESC, id DESC"
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([max(1, int(limit)), max(0, int(offset))])
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def count_memories(self, category: Optional[str] = None) -> int:
        """Count memories using the same optional category filter as paging."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    "SELECT COUNT(*) FROM memories WHERE category = ?", (category,)
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM memories")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def delete_memory(self, memory_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    # Audit Logs
    def create_audit_log(self, action: str, status: str, details: str, level: int = 0) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO audit_logs (timestamp, action, status, details, level)
                VALUES (?, ?, ?, ?, ?)
            """, (now, action, status, details, level))
            conn.commit()
            return cursor.lastrowid

    def get_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # Conversations (persistent chat history)
    def add_conversation_message(self, conversation_id: str, role: str, content: str) -> Optional[int]:
        """Insert a chat message; returns the new row id (used as message_id
        so every UI can dedupe hydrated history against live token streams)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO conversations (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, role, content, now))
            conn.commit()
            return cursor.lastrowid

    def get_conversation_messages(
        self, conversation_id: str, limit: Optional[int] = 50,
    ) -> List[Dict[str, str]]:
        """`limit=None` returns the FULL history (the server-side chat
        export needs every message — the owner report 2026-09-05: a
        client-side export can only export what it hydrated, capped at
        the last 50, with hydration-time timestamps)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, role, content, created_at FROM conversations "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            )
            rows = cursor.fetchall()
            # Return the most recent `limit` messages, preserving order. The row
            # id is exposed as message_id for cross-client dedupe; created_at
            # is the message's REAL time (exports show it, not hydration time).
            selected = rows if limit is None else rows[-limit:]
            return [
                {"message_id": r["id"], "role": r["role"],
                 "content": r["content"], "created_at": r["created_at"]}
                for r in selected
            ]

    def get_conversation_ids(self) -> List[str]:
        """Distinct conversation IDs, most recently active first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT conversation_id, MAX(id) AS last_id FROM conversations "
                "GROUP BY conversation_id ORDER BY last_id DESC"
            )
            return [row["conversation_id"] for row in cursor.fetchall()]

    def get_conversation_previews(self, limit: int = 50) -> List[Dict[str, Any]]:
        """One preview row per conversation: id, title (first user message), lastMessage, updatedAt."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT conversation_id FROM conversations GROUP BY conversation_id ORDER BY MAX(id) DESC LIMIT ?",
                (limit,),
            )
            conv_ids = [row["conversation_id"] for row in cursor.fetchall()]

        previews = []
        for cid in conv_ids:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT role, content, created_at FROM conversations "
                    "WHERE conversation_id = ? ORDER BY id ASC",
                    (cid,),
                )
                rows = cursor.fetchall()
            if not rows:
                continue
            first_user = next((r["content"] for r in rows if r["role"] == "user"), None)
            last = rows[-1]
            previews.append({
                "id": cid,
                "title": (first_user[:40] + ("…" if len(first_user) > 40 else "")) if first_user else "New Conversation",
                "lastMessage": last["content"][:80],
                "updatedAt": last["created_at"],
            })
        return previews

    # Project tasks (Kanban board — synced across all UIs)
    def add_project_task(self, task: Dict[str, Any]) -> bool:
        """Insert a project task. `id` is client-supplied (task-<ts>) so the
        creating UI can match its optimistic copy against the server row."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO project_tasks
                    (id, project_id, title, description, status, priority,
                     assignee, due_date, tags, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task["id"],
                task["project_id"],
                task["title"],
                task.get("description", ""),
                task.get("status", "todo"),
                task.get("priority", "medium"),
                task.get("assignee", ""),
                task.get("dueDate", ""),
                json.dumps(task.get("tags", [])),
                task.get("createdAt", now),
                task.get("updatedAt", now),
                task.get("completedAt"),
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_project_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM project_tasks WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            )
            return [self._project_task_row(r) for r in cursor.fetchall()]

    def update_project_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            fields, values = [], []
            column_map = {
                "title": "title", "description": "description", "status": "status",
                "priority": "priority", "assignee": "assignee", "dueDate": "due_date",
                "completedAt": "completed_at",
            }
            for key, column in column_map.items():
                if key in updates:
                    fields.append(f"{column} = ?")
                    values.append(updates[key])
            if "tags" in updates:
                fields.append("tags = ?")
                values.append(json.dumps(updates["tags"]))
            if not fields:
                return False
            fields.append("updated_at = ?")
            values.append(datetime.utcnow().isoformat())
            values.append(task_id)
            cursor.execute(
                f"UPDATE project_tasks SET {', '.join(fields)} WHERE id = ?", values
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_project_task(self, task_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM project_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _project_task_row(r) -> Dict[str, Any]:
        row = dict(r)
        try:
            row["tags"] = json.loads(row.get("tags") or "[]")
        except (TypeError, ValueError):
            row["tags"] = []
        row["dueDate"] = row.pop("due_date", "")
        row["createdAt"] = row.get("created_at", "")
        row["updatedAt"] = row.get("updated_at", "")
        row["completedAt"] = row.get("completed_at") or None
        return row

db = DatabaseManager()
