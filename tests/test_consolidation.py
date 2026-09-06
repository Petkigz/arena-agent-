import sqlite3

import pytest

from app.cognition.consolidation import ConsolidationCoordinator, ConsolidationError
from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore


def _episode(store, task_id, success, suffix):
    return store.add(
        "episodic",
        f"verified episode {suffix}",
        source="goal_verifier",
        task_id=task_id,
        outcome="achieved" if success else "failed",
        success=success,
        importance=0.8,
    )


def test_consolidation_replays_conflicts_preserves_unknown_and_derives_gist(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    _episode(memory, "conflict-task", True, "success")
    _episode(memory, "conflict-task", False, "failure")
    first_success = _episode(memory, "stable-task", True, "one")
    second_success = _episode(memory, "stable-task", True, "two")
    calibrator = ConfidenceCalibrator(tmp_path / "calibration.db")
    for outcome in (True, False, True):
        calibrator.record("search_files", 0.8, outcome, goal_type="search")

    coordinator = ConsolidationCoordinator(tmp_path / "consolidation.db")
    result = coordinator.run(memory, calibrator=calibrator, max_tasks=20)

    assert result["status"] == "completed"
    assert result["conflicts_replayed"] == 1
    assert result["gists_created"] == 1
    assert result["calibration_refreshed"] is True
    conflict_events = [
        event for event in coordinator.events(result["run_id"])
        if event["event_type"] == "conflict_replayed"
    ]
    assert conflict_events[0]["status"] == "requires_fresh_evidence"
    assert conflict_events[0]["detail"]["resolution"] == "not_resolved"
    assert conflict_events[0]["detail"]["unknown_preserved"] is True
    gist = memory.find_exact(
        "semantic",
        "Derived verified gist for task stable-task: verified episode one | verified episode two. "
        "This is a consolidated historical pattern, not a current observation.",
    )
    assert gist is not None
    assert memory.consolidation_targets(first_success.memory_id)
    assert memory.consolidation_targets(second_success.memory_id)

    repeated = coordinator.run(memory, calibrator=calibrator, max_tasks=20)
    assert repeated["gists_created"] == 0
    assert len(coordinator.history()) == 2


def test_consolidation_persists_and_rejects_unsupported_store(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    coordinator = ConsolidationCoordinator(tmp_path / "consolidation.db")
    result = coordinator.run(memory, calibrator=None)
    reopened = ConsolidationCoordinator(tmp_path / "consolidation.db")
    assert reopened.history()[0]["run_id"] == result["run_id"]
    assert reopened.events(result["run_id"])[0]["event_type"] == "calibration_refresh"

    with sqlite3.connect(tmp_path / "unsupported.db") as conn:
        conn.execute(
            "CREATE TABLE consolidation_meta "
            "(singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO consolidation_meta VALUES (1, 99)")
    with pytest.raises(ConsolidationError, match="unsupported consolidation store"):
        ConsolidationCoordinator(tmp_path / "unsupported.db")


def test_consolidation_does_not_create_gist_from_single_or_mixed_evidence(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    _episode(memory, "single-task", True, "only")
    _episode(memory, "mixed-task", True, "success")
    _episode(memory, "mixed-task", False, "failure")
    coordinator = ConsolidationCoordinator(tmp_path / "consolidation.db")

    result = coordinator.run(memory)

    assert result["gists_created"] == 0
    assert any(event["event_type"] == "gist_skipped" for event in coordinator.events(result["run_id"]))
