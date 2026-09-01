"""Task-list tools: the TaskManager surface as manifest capabilities.

DIAG D3 (live 2026-09-01, owner review item 3): 'Create a task: review
the quarterly budget report (diag-xxxxxx), with priority high.' executed
budget_summary — a finance lookalike — because NO task-creation
capability existed in the registry, and the goal interpreter classified
the request as finance (the word 'budget' in the task's DESCRIPTION
dragged the domain). The wrong capability was not just selected; it was
REQUIRED by the goal representation.

TaskManager.create_task existed all along (app/tasks.py, HTTP-exposed)
but was never registered as a tool, so the cognition pipeline could not
reach it. This adapter closes that gap: a DB row is the ground truth.
"""

from typing import Any, Dict

from app.utils.logger import app_logger

_VALID_PRIORITIES = ("low", "medium", "high", "urgent")


def create_task(title: str = "", goal: str = "",
                priority: str = "medium") -> Dict[str, Any]:
    """Create a task in the owner's persistent task list.

    Payload keys (the N2 arity contract — these ARE the handler's real
    parameters): 'title' (required), 'goal' (optional, defaults to the
    title), 'priority' (low/medium/high/urgent, default medium — an
    unknown value falls back to medium rather than failing the whole
    creation).
    """
    clean_title = str(title or "").strip()
    if not clean_title:
        return {"success": False,
                "error": "create_task requires a non-empty 'title'"}
    clean_priority = str(priority or "medium").strip().lower()
    if clean_priority not in _VALID_PRIORITIES:
        clean_priority = "medium"
    try:
        from app.tasks import TaskManager, TaskCreate
        task = TaskManager.create_task(TaskCreate(
            title=clean_title[:300],
            goal=str(goal or "").strip()[:1000] or clean_title[:300],
            priority=clean_priority,
        ))
        app_logger.info(
            f"create_task: task '{task.id}' ({task.priority}) "
            f"created in the persistent task list.")
        return {
            "success": True,
            "task_id": task.id,
            "title": task.title,
            "priority": task.priority,
            "status": task.status,
        }
    except Exception as exc:
        app_logger.error(f"create_task failed: {exc}")
        return {"success": False, "error": f"create_task failed: {exc}"}
