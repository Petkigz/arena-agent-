import pytest
from app.tasks import TaskManager, TaskCreate, TaskUpdate
from app.database import db

def test_task_manager_operations():
    # Create
    task_in = TaskCreate(
        title="Check system memory",
        goal="Ensure RAM allocation is correct",
        priority="high",
        plan=["Get RAM", "Check settings"]
    )
    
    task = TaskManager.create_task(task_in)
    assert task.id is not None
    assert task.title == "Check system memory"
    assert task.status == "queued"
    
    # Retrieve
    retrieved = TaskManager.get_task(task.id)
    assert retrieved is not None
    assert retrieved.goal == "Ensure RAM allocation is correct"
    
    # Update
    updates = TaskUpdate(status="running", current_step=1, checkpoint="Checked current RAM")
    updated = TaskManager.update_task(task.id, updates)
    assert updated is not None
    assert updated.status == "running"
    assert updated.current_step == 1
    assert updated.checkpoint == "Checked current RAM"
    
    # List all
    tasks = TaskManager.get_all_tasks(status="running")
    assert len(tasks) >= 1
    assert any(t.id == task.id for t in tasks)
    
    # Delete
    assert TaskManager.delete_task(task.id) is True
    assert TaskManager.get_task(task.id) is None

def test_acquire_skill_for_task():
    # First save a memory skill
    db.create_memory({
        "content": "Vocal EQ Skill: High pass at 80Hz, cut boxy frequencies at 300Hz, boost air at 10kHz.",
        "category": "learned_skill",
        "source": "https://youtube.com/watch?v=vocal_eq_test",
        "confidence": 0.95
    })

    # Create task requiring vocal eq
    task_in = TaskCreate(
        title="Mix vocal track in DAW",
        goal="Apply vocal EQ and compression settings",
        priority="high",
        plan=["Load DAW project", "Apply EQ settings"]
    )
    task = TaskManager.create_task(task_in)

    # Acquire skill
    res = TaskManager.acquire_skill_for_task(task.id)
    assert res["success"] is True
    assert res["skill_result"]["source"] == "sqlite_memory"

    # Cleanup
    TaskManager.delete_task(task.id)
