import pytest
from app.tasks import TaskManager, TaskCreate, TaskUpdate

def test_task_resumption():
    # 1. Create multi-step task
    task = TaskManager.create_task(TaskCreate(
        title="Multi-Step Research Project",
        goal="Gather data and generate report",
        plan=["Search web", "Scrape text", "Draft report"]
    ))
    assert task.id is not None
    assert task.status == "queued"

    # 2. Simulate interrupted step
    TaskManager.update_task(task.id, TaskUpdate(status="in_progress", current_step=1, checkpoint="Interrupted during scrape"))

    # 3. Resume interrupted tasks
    res_data = TaskManager.resume_interrupted_tasks()
    assert res_data["success"] is True
    assert res_data["resumed_tasks_count"] >= 1

    # Cleanup
    TaskManager.delete_task(task.id)
