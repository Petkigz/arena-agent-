from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import Lesson, MemoryLearner
from app.memory.reflection_engine import ReflectionEngine


def test_memory_round_trip_and_search(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    item = store.add("episodic", "Chrome crashed while opening the dashboard", importance=0.8, tags=["chrome", "dashboard"])
    assert store.get(item.memory_id).content.startswith("Chrome crashed")
    results = store.search("dashboard chrome")
    assert results and results[0].memory_id == item.memory_id


def test_learning_promotes_explicit_knowledge(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    learner = MemoryLearner(store)
    episode = learner.record_episode("A test succeeded", success=True)
    created = learner.consolidate(
        [episode],
        semantic_facts=["The test environment supports the probe"],
        procedures=["Check the probe before escalating"],
        lessons=[Lesson("Prefer the probe before escalating", 0.8)],
    )
    assert {item.kind for item in created} == {"semantic", "procedural", "lesson"}


def test_reflection_handles_llm_unavailable():
    """Test that reflection gracefully handles LLM unavailability."""
    result = ReflectionEngine.reflect_on_task_execution(
        task_title="Test Task",
        task_goal="Test goal",
        outcome_summary="Task completed with unknown result"
    )
    # Should return a result dict even if LLM fails
    assert isinstance(result, dict)
    assert "task_title" in result
    assert result["task_title"] == "Test Task"
