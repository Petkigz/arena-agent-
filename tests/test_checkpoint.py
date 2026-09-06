import json

import pytest

from app.cognition.blackboard import Blackboard
from app.cognition.checkpoint import CheckpointSchemaError, CognitiveCheckpointStore
from app.cognition.cognitive_state import CognitiveState


def test_checkpoint_round_trip(tmp_path):
    store = CognitiveCheckpointStore(tmp_path)
    state = CognitiveState()
    board = Blackboard()
    board.set("goal", "test", source="unit_test", confidence=1.0)

    path = store.save(state, board, ontology_revision=3)
    restored = store.load()

    assert path.exists()
    assert restored is not None
    assert restored["schema_version"] == 2
    assert restored["ontology_revision"] == 3
    assert restored["blackboard"]["goal"]["value"] == "test"


def _write_v1(path, *, state=None, blackboard=None):
    payload = {
        "schema_version": 1,
        "saved_at": "2026-01-01T00:00:00+00:00",
        "state": state or {"goal": "old"},
        "blackboard": blackboard or {"goal": {"value": "test", "source": "unit_test"}},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_supported_v1_migration_preserves_state_and_records_history(tmp_path):
    store = CognitiveCheckpointStore(tmp_path)
    source = _write_v1(tmp_path / "active.json")

    before = store.load()
    assert before["schema_version"] == 1
    migrated = store.migrate()

    assert migrated["schema_version"] == 2
    assert migrated["ontology_revision"] == 1
    assert migrated["state"] == source["state"]
    assert migrated["blackboard"] == source["blackboard"]
    history = store.migration_history()
    assert len(history) == 1
    assert history[0]["event_type"] == "migration"
    assert (tmp_path / history[0]["backup"]).read_text() == json.dumps(source)


def test_checkpoint_migration_rollback_restores_exact_prior_bytes(tmp_path):
    store = CognitiveCheckpointStore(tmp_path)
    original = _write_v1(tmp_path / "active.json")
    original_bytes = json.dumps(original).encode()

    store.migrate()
    restored = store.rollback()

    assert restored["schema_version"] == 1
    assert (tmp_path / "active.json").read_bytes() == original_bytes
    assert [row["event_type"] for row in store.migration_history()] == [
        "migration", "rollback"
    ]


def test_unsupported_or_ambiguous_checkpoint_fails_closed(tmp_path):
    store = CognitiveCheckpointStore(tmp_path)
    (tmp_path / "active.json").write_text(
        json.dumps({"schema_version": 99, "state": {}, "blackboard": {}, "saved_at": "now"})
    )
    with pytest.raises(CheckpointSchemaError, match="supported versions"):
        store.load()

    (tmp_path / "ambiguous.json").write_text(
        json.dumps({"schema_version": 1, "state": {}, "blackboard": {}})
    )
    with pytest.raises(CheckpointSchemaError, match="missing required fields"):
        store.load("ambiguous")


def test_checkpoint_rollback_refuses_after_unrelated_overwrite(tmp_path):
    store = CognitiveCheckpointStore(tmp_path)
    _write_v1(tmp_path / "active.json")
    store.migrate()
    (tmp_path / "active.json").write_text(
        json.dumps({
            "schema_version": 2,
            "ontology_revision": 1,
            "saved_at": "later",
            "state": {},
            "blackboard": {},
        })
    )

    with pytest.raises(RuntimeError, match="changed after migration"):
        store.rollback()
