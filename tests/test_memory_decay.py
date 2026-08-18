import pytest
from app.cognition.memory import MemoryStore

def test_memory_decay_and_prune(tmp_path):
    store = MemoryStore(tmp_path / "test_decay.db")
    store.add("episodic", "Old stale memory entry", importance=0.08)
    store.add("lesson", "Important lesson learned", importance=0.95)

    pruned = store.apply_memory_decay_and_prune(decay_rate=0.1, max_records=1)
    assert isinstance(pruned, int)
