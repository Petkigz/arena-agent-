import pytest
from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import MemoryLearner, Lesson

def test_reflection_and_memory_learning(tmp_path):
    store = MemoryStore(tmp_path / "test_reflection.db")
    learner = MemoryLearner(store)

    # 1. Process outcome reflection
    record = learner.process_outcome_reflection(
        task_title="Open Firefox Browser",
        goal="Launch browser for search",
        outcome_summary="Firefox launched successfully.",
        surprisal=0.0
    )

    assert record.kind == "lesson"
    assert "Open Firefox Browser" in record.content
    assert record.importance >= 0.5
