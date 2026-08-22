"""Owner control plane: policy persistence and authority over every action."""

from unittest.mock import patch

import pytest

from app.cognition.action_proposal import ActionGate, ActionProposal
from app.cognition.owner_control import ControlMode, OwnerControlStore


def test_default_policy_preserves_bounded_autonomy(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")

    assert store.evaluate("read_file", 0).allowed is True
    assert store.evaluate("open_application", 2).allowed is True
    sensitive = store.evaluate("send_email", 3)
    assert sensitive.allowed is False
    assert sensitive.requires_approval is True


def test_owner_can_require_approval_for_every_action(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")
    store.update({"mode": ControlMode.APPROVE_EVERY_ACTION.value})

    decision = store.evaluate("read_file", 0)
    assert decision.allowed is False
    assert decision.requires_approval is True


def test_observe_and_suggest_modes_never_offer_execution_authority(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")
    for mode in (ControlMode.OBSERVE_ONLY, ControlMode.SUGGEST_ONLY):
        store.update({"mode": mode.value})
        decision = store.evaluate("read_file", 0)
        assert decision.allowed is False
        assert decision.requires_approval is False


def test_custom_mode_is_allowlist_and_blocklist_is_absolute(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")
    store.update({
        "mode": "custom",
        "custom_autonomous_actions": ["read_file"],
        "blocked_actions": ["delete_file"],
    })

    assert store.evaluate("read_file", 0).allowed is True
    outside = store.evaluate("web_search", 0)
    assert outside.allowed is False and outside.requires_approval is True
    blocked = store.evaluate("delete_file", 0)
    assert blocked.allowed is False and blocked.requires_approval is False


def test_emergency_pause_persists_across_restart(tmp_path):
    path = tmp_path / "control.json"
    store = OwnerControlStore(path)
    updated = store.set_paused(True)

    assert updated.paused is True
    restored = OwnerControlStore(path)
    assert restored.get_policy().paused is True
    assert restored.evaluate("read_file", 0).allowed is False


def test_malformed_policy_fails_closed(tmp_path):
    path = tmp_path / "control.json"
    path.write_text("{not-json", encoding="utf-8")

    store = OwnerControlStore(path)
    assert store.get_policy().paused is True


def test_unknown_update_field_is_rejected(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")
    with pytest.raises(ValueError):
        store.update({"secret_override": True})


def test_action_gate_obeys_stricter_owner_mode(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")
    store.update({"mode": "approve_every_action"})
    proposal = ActionProposal(action_type="read_file", payload={"file_path": "README.md"})

    with patch("app.cognition.action_proposal.owner_control_store", store):
        result = ActionGate.evaluate_proposal(proposal)

    assert result.allowed is False
    assert result.requires_approval is True
    assert result.gate_name == "owner_control_gate"
    assert proposal.decision_stage == "awaiting_authorization"


def test_action_gate_emergency_pause_precedes_prediction_and_resources(tmp_path):
    store = OwnerControlStore(tmp_path / "control.json")
    store.set_paused(True)
    proposal = ActionProposal(action_type="read_file", payload={"file_path": "README.md"})

    with (
        patch("app.cognition.action_proposal.owner_control_store", store),
        patch("app.cognition.action_proposal.HardwareMonitor.get_hardware_stats") as hardware,
        patch("app.cognition.action_proposal.PredictionEngine.predict_action") as prediction,
    ):
        result = ActionGate.evaluate_proposal(proposal)

    assert result.allowed is False
    assert result.requires_approval is False
    assert "pause" in result.reason.lower()
    hardware.assert_not_called()
    prediction.assert_not_called()
