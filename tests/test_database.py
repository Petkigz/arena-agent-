import os
import tempfile
from pathlib import Path
from app.database import DatabaseManager

def test_db_manager_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_assistant.db"
        test_db = DatabaseManager(db_path=str(db_path))
        
        # Test Task CRUD
        task_data = {
            "id": "task-test-123",
            "title": "Test Title",
            "goal": "Test Goal",
            "status": "queued",
            "priority": "high",
            "plan": ["Step 1", "Step 2"],
            "current_step": 0,
            "checkpoint": "Starting",
        }
        
        # Create
        assert test_db.create_task(task_data) is True
        
        # Read
        retrieved = test_db.get_task("task-test-123")
        assert retrieved is not None
        assert retrieved["title"] == "Test Title"
        assert retrieved["plan"] == ["Step 1", "Step 2"]
        
        # Update
        assert test_db.update_task("task-test-123", {"status": "running", "current_step": 1}) is True
        retrieved_updated = test_db.get_task("task-test-123")
        assert retrieved_updated["status"] == "running"
        assert retrieved_updated["current_step"] == 1
        
        # List
        all_tasks = test_db.get_all_tasks()
        assert len(all_tasks) == 1
        
        # Delete
        assert test_db.delete_task("task-test-123") is True
        assert test_db.get_task("task-test-123") is None

def test_db_manager_memories_and_audit():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_assistant_2.db"
        test_db = DatabaseManager(db_path=str(db_path))
        
        # Create memory
        mem_id = test_db.create_memory({
            "content": "Prefers dark mode",
            "category": "ui_preference",
            "source": "user",
            "confidence": 0.95
        })
        assert isinstance(mem_id, int)
        
        # List memories
        mems = test_db.get_memories()
        assert len(mems) == 1
        assert mems[0]["content"] == "Prefers dark mode"
        
        # Create Audit Log
        log_id = test_db.create_audit_log("test_action", "success", "All passed")
        assert isinstance(log_id, int)
        
        logs = test_db.get_audit_logs()
        assert len(logs) == 1
        assert logs[0]["action"] == "test_action"
