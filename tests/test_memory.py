from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import Lesson, MemoryLearner
from app.cognition.reflection import ReflectionEngine


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
    created = learner.consolidate([episode], semantic_facts=["The test environment supports the probe"], lessons=[Lesson("Prefer the probe before escalating", 0.8)])
    assert {item.kind for item in created} == {"semantic", "lesson"}


def test_reflection_does_not_invent_a_lesson():
    reflection = ReflectionEngine().reflect([], summary="Task completed", unresolved=("Need confirmation",))
    assert reflection.lesson is None
    assert reflection.unresolved == ("Need confirmation",)
