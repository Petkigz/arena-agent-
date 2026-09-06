"""Versioned user-state contracts: provenance, precedence, expiry, and history."""

from datetime import datetime, timedelta, timezone

import pytest

from app.cognition.user_state import UserStateStore


def test_explicit_owner_state_overrides_inferred_and_is_preserved(tmp_path):
    store = UserStateStore(tmp_path / "user_state.db")

    inferred = store.set_attribute(
        "communication_style",
        "brief",
        source_type="inferred",
        confidence=0.6,
        evidence_ids=["trace:inference-1"],
    )
    assert inferred["success"] is True

    explicit = store.set_attribute(
        "communication_style",
        "detailed",
        source_type="explicit_owner",
        confidence=1.0,
        evidence_ids=["owner:turn-2"],
    )
    assert explicit["success"] is True
    assert explicit["state"]["version"] == 2

    blocked = store.set_attribute(
        "communication_style",
        "terse",
        source_type="inferred",
        confidence=0.99,
        evidence_ids=["trace:inference-2"],
    )
    assert blocked["success"] is False
    assert blocked["updated"] is False
    assert store.get("communication_style")["value"] == "detailed"
    assert store.get("communication_style")["source_type"] == "explicit_owner"

    history = store.history("communication_style")
    assert [item["version"] for item in reversed(history)] == [1, 2]
    assert [item["source_type"] for item in reversed(history)] == ["inferred", "explicit_owner"]


def test_explicit_owner_update_can_replace_old_explicit_state(tmp_path):
    store = UserStateStore(tmp_path / "user_state.db")
    first = store.set_attribute(
        "accessibility.needs_large_text",
        False,
        source_type="explicit_owner",
        evidence_ids=["owner:turn-1"],
    )
    second = store.set_attribute(
        "accessibility.needs_large_text",
        True,
        source_type="explicit_owner",
        evidence_ids=["owner:turn-5"],
    )
    assert first["state"]["version"] == 1
    assert second["state"]["version"] == 2
    assert store.get("accessibility.needs_large_text")["value"] is True


def test_expired_state_is_not_in_runtime_context(tmp_path):
    store = UserStateStore(tmp_path / "user_state.db")
    expiry = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store.set_attribute(
        "current_task",
        "old task",
        source_type="explicit_owner",
        evidence_ids=["owner:turn-1"],
        expires_at=expiry,
    )

    record = store.get("current_task")
    assert record["is_expired"] is True
    assert store.get("current_task", include_expired=False) is None
    assert store.snapshot()["attributes"] == []
    assert store.compact_context() == ""

    refreshed = store.set_attribute(
        "current_task",
        "new task",
        source_type="inferred",
        confidence=0.5,
        evidence_ids=["trace:after-expiry"],
    )
    assert refreshed["success"] is True
    assert store.get("current_task")["value"] == "new task"


def test_state_updates_require_provenance_and_valid_confidence(tmp_path):
    store = UserStateStore(tmp_path / "user_state.db")
    with pytest.raises(ValueError):
        store.set_attribute("goal", "x", source_type="model_guess", evidence_ids=["x"])
    with pytest.raises(ValueError):
        store.set_attribute("goal", "x", source_type="inferred", confidence=1.1, evidence_ids=["x"])
    with pytest.raises(ValueError):
        store.set_attribute("goal", "x", source_type="inferred", confidence=0.5)


def test_snapshot_context_marks_owner_state_as_evidence_linked(tmp_path):
    store = UserStateStore(tmp_path / "user_state.db")
    store.set_attribute(
        "preferences.response_length",
        "concise",
        source_type="explicit_owner",
        evidence_ids=["owner:turn-9"],
        affects_action_selection=False,
    )
    snapshot = store.snapshot()
    assert snapshot["state_version"] == 1
    assert snapshot["attributes"][0]["evidence_ids"] == ["owner:turn-9"]
    assert "explicit_owner" in store.compact_context()
    assert "concise" in store.compact_context()
