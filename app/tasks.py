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

    @staticmethod
    def resume_interrupted_tasks() -> Dict[str, Any]:
        """
        Scans SQLite database for tasks in 'queued', 'in_progress', or 'failed' state,
        restores cognitive checkpoints, and resumes multi-step execution from the exact step.
        """
        all_tasks = TaskManager.get_all_tasks()
        resumed = []

        for task in all_tasks:
            if task.status in ["queued", "in_progress", "failed"] and task.plan:
                # Calculate resume step
                step_to_resume = task.current_step if task.current_step < len(task.plan) else 0
                step_description = task.plan[step_to_resume]

                checkpoint_msg = f"Resumed at step {step_to_resume + 1}/{len(task.plan)}: '{step_description}'"
                TaskManager.update_task(task.id, TaskUpdate(
                    status="in_progress",
                    current_step=step_to_resume,
                    checkpoint=checkpoint_msg
                ))

                db.create_audit_log("resume_task", "success", f"Resumed task '{task.id}' ({task.title}) at step {step_to_resume + 1}", level=1)
                resumed.append({"task_id": task.id, "title": task.title, "resumed_step": step_to_resume + 1, "checkpoint": checkpoint_msg})

        return {
            "success": True,
            "resumed_tasks_count": len(resumed),
            "resumed_tasks": resumed
        }

    @staticmethod
    def acquire_skill_for_task(task_id: str) -> Dict[str, Any]:
        """
        Triggers the autonomous skill lookup/acquisition loop for a task.
        Checks SQLite memory first; if missing, searches YouTube, extracts transcript,
        saves to SQLite memory, and updates the task checkpoint.
        """
        task = TaskManager.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        from app.skill_acquisition import SkillAcquisitionManager
        res = SkillAcquisitionManager.auto_acquire_skill_for_task(task.title, task.goal)
        
        # Update task checkpoint with skill acquisition details
        new_checkpoint = f"Skill Status: {res.get('source')}. {res.get('summary', '')[:200]}"
        TaskManager.update_task(task_id, TaskUpdate(checkpoint=new_checkpoint))
        
        return {
            "success": True,
            "task_id": task_id,
            "skill_result": res
        }
