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

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            set_parts = []
            params = []
            for k, v in updates.items():
                if k == "plan":
                    set_parts.append("plan = ?")
                    params.append(json.dumps(v))
                else:
                    set_parts.append(f"{k} = ?")
                    params.append(v)
            
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

    def get_memories(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT * FROM memories WHERE category = ? ORDER BY last_reviewed DESC", (category,))
            else:
                cursor.execute("SELECT * FROM memories ORDER BY last_reviewed DESC")
            return [dict(row) for row in cursor.fetchall()]

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

db = DatabaseManager()
