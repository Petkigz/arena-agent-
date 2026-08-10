from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from app.database import db
from app.utils.logger import app_logger

class TaskCreate(BaseModel):
    title: str
    goal: str
    priority: str = "medium"
    plan: Optional[List[str]] = Field(default_factory=list)

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    plan: Optional[List[str]] = None
    current_step: Optional[int] = None
    checkpoint: Optional[str] = None

class Task(BaseModel):
    id: str
    title: str
    goal: str
    status: str
    priority: str
    plan: List[str]
    current_step: int = 0
    checkpoint: Optional[str] = None
    created_at: str
    updated_at: str

class TaskManager:
    @staticmethod
    def create_task(task_in: TaskCreate) -> Task:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow().isoformat()
        
        task_data = {
            "id": task_id,
            "title": task_in.title,
            "goal": task_in.goal,
            "status": "queued",
            "priority": task_in.priority,
            "plan": task_in.plan or [],
            "current_step": 0,
            "checkpoint": "Task created. Initializing...",
            "created_at": now,
            "updated_at": now
        }
        
        db.create_task(task_data)
        app_logger.info(f"Task {task_id} successfully created and persistent in SQLite.")
        db.create_audit_log("create_task", "success", f"Task {task_id}: {task_in.title}", level=0)
        return Task(**task_data)

    @staticmethod
    def get_task(task_id: str) -> Optional[Task]:
        task_data = db.get_task(task_id)
        if task_data:
            return Task(**task_data)
        return None

    @staticmethod
    def get_all_tasks(status: Optional[str] = None) -> List[Task]:
        tasks_data = db.get_all_tasks(status=status)
        return [Task(**t) for t in tasks_data]

    @staticmethod
    def update_task(task_id: str, updates_in: TaskUpdate) -> Optional[Task]:
        updates = {k: v for k, v in updates_in.model_dump().items() if v is not None}
        if not updates:
            return TaskManager.get_task(task_id)
            
        success = db.update_task(task_id, updates)
        if success:
            app_logger.info(f"Task {task_id} updated: {updates}")
            db.create_audit_log("update_task", "success", f"Task {task_id}: {updates}", level=0)
            return TaskManager.get_task(task_id)
        return None

    @staticmethod
    def delete_task(task_id: str) -> bool:
        success = db.delete_task(task_id)
        if success:
            app_logger.info(f"Task {task_id} deleted.")
            db.create_audit_log("delete_task", "success", f"Task {task_id}", level=2)
        return success
