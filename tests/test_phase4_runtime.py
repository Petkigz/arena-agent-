from app.cognition.memory_learning import Lesson
from app.cognition.runtime import CognitiveRuntime


def test_runtime_owns_memory_and_learning(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    episode = runtime.learning.record_episode("Opened a test page", task_id="t1", success=True)
    assert runtime.memory.get(episode.memory_id).task_id == "t1"
    created = runtime.learning.consolidate([], semantic_facts=["The test page is reachable"], lessons=[Lesson("Reuse the working navigation path", 0.7)])
    assert len(created) == 2


def test_runtime_memory_is_persistent(tmp_path):
    path = str(tmp_path / "arena.db")
    first = CognitiveRuntime(db_path=path)
    first.learning.record_episode("Persistent experience", task_id="t2")
    second = CognitiveRuntime(db_path=path)
    assert second.memory.search("Persistent experience", limit=1)
