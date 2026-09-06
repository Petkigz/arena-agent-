"""Phase 3: typed memory retrieval is routed through the active runtime store."""

from app.cognition.memory import MemoryStore


def test_retrieval_keeps_memory_kinds_visible_and_bounded(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    common = "browser launch project recovery strategy"
    records = [
        store.add("semantic", f"Durable fact: {common}", source="owner_note"),
        store.add("procedural", f"Procedure: {common}", source="verified_procedure"),
        store.add("lesson", f"Lesson: {common}", source="reflection"),
        store.add(
            "episodic",
            f"Episode: {common}",
            source="goal_verifier",
            task_id="task-123456789",
            outcome="achieved",
            success=True,
        ),
    ]

    retrieved = store.retrieve_context_records(common, limit=4, per_kind=1)

    assert {record.kind for record in retrieved} == {
        "semantic",
        "procedural",
        "lesson",
        "episodic",
    }
    assert len(retrieved) == 4
    rendered = store.render_context(retrieved)
    assert "historical records, not current observation" in rendered
    assert "provenance=goal_verifier, task task-123456789" in rendered
    assert "verified_success=True" in rendered


def test_retrieval_does_not_return_unrelated_memory(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    matching = store.add("semantic", "project browser recovery", source="owner_note")
    store.add("lesson", "recipe ingredients and cooking", source="reflection")

    retrieved = store.retrieve_context_records("project browser recovery", limit=4)

    assert [record.memory_id for record in retrieved] == [matching.memory_id]
