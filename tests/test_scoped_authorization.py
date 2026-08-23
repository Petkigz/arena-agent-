"""Scoped authorization grants are exact, short-lived, revocable, and single-use."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.cognition.action_proposal import ActionGate, ActionProposal
from app.cognition.approval_store import ApprovalStore
from app.cognition.owner_control import AuthorizationStore, OwnerControlStore


def test_grant_is_bound_to_exact_action_and_payload():
    store = AuthorizationStore()
    payload = {"to": "owner@example.test", "body": "approved text"}
    grant = store.issue("send_email", payload)

    assert store.validate(grant.authorization_id, "send_email", payload).valid is True
    assert store.validate(grant.authorization_id, "send_message", payload).valid is False
    assert store.validate(
        grant.authorization_id,
        "send_email",
        {"to": "other@example.test", "body": "approved text"},
    ).valid is False


def test_expired_grant_is_invalid():
    store = AuthorizationStore()
    payload = {"path": "README.md"}
    grant = store.issue("read_file", payload)
    grant.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

    assert store.validate(grant.authorization_id, "read_file", payload).valid is False


def test_grant_is_single_use_and_revocable():
    store = AuthorizationStore()
    payload = {"path": "README.md"}
    grant = store.issue("read_file", payload)

    assert store.consume(grant.authorization_id, "read_file", payload).valid is True
    assert store.consume(grant.authorization_id, "read_file", payload).valid is False

    second = store.issue("read_file", payload)
    assert store.revoke(second.authorization_id) is True
    assert store.validate(second.authorization_id, "read_file", payload).valid is False


def test_approval_mints_one_scoped_grant_without_mutating_payload():
    grants = AuthorizationStore()
    approvals = ApprovalStore()
    payload = {"to": "owner@example.test", "body": "exact"}
    request = approvals.add(
        "conv-1",
        "send_email",
        payload,
        "Level 3",
        goal_text="Send the verified report",
        proposal_id="proposal_original",
        recommendation_reason="Fastest delivery option",
        alternatives_considered=[{"action_type": "save_draft", "rank": 2}],
        predicted_outcome={"message": "delivered"},
    )

    with patch("app.cognition.owner_control.authorization_store", grants):
        decided = approvals.decide(request.action_id, True, note="approved once")

    assert decided is not None
    assert decided.authorization_id is not None
    assert decided.payload == payload
    assert decided.decision_note == "approved once"
    assert decided.goal_text == "Send the verified report"
    assert decided.proposal_id == "proposal_original"
    assert decided.alternatives_considered[0]["action_type"] == "save_draft"
    assert grants.validate(decided.authorization_id, "send_email", payload).valid is True

    # A repeated approval decision is idempotent and cannot mint another grant.
    first_id = decided.authorization_id
    with patch("app.cognition.owner_control.authorization_store", grants):
        repeated = approvals.decide(request.action_id, True)
    assert repeated.authorization_id == first_id
    assert len(grants.list_active()) == 1


def test_exact_grant_can_cross_approval_gate_once(tmp_path):
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.update({"mode": "approve_every_action"})
    grants = AuthorizationStore()
    payload = {"file_path": "README.md"}
    grant = grants.issue("read_file", payload)

    proposal = ActionProposal(
        action_type="read_file",
        payload=payload,
        authorization_id=grant.authorization_id,
    )
    with (
        patch("app.cognition.action_proposal.owner_control_store", policy),
        patch("app.cognition.action_proposal.authorization_store", grants),
        patch("app.tools.manifest.get_tool_manifest", return_value={"read_file": {"safety_level": 0}}),
        patch(
            "app.cognition.action_proposal.HardwareMonitor.get_hardware_stats",
            return_value={"ram_used_percent": 20.0},
        ),
    ):
        first = ActionGate.evaluate_proposal(proposal)
        replay = ActionGate.evaluate_proposal(ActionProposal(
            action_type="read_file",
            payload=payload,
            authorization_id=grant.authorization_id,
        ))

    assert first.allowed is True
    assert replay.allowed is False
    assert replay.gate_name == "authorization_gate"


def test_grant_cannot_override_emergency_pause(tmp_path):
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.set_paused(True)
    grants = AuthorizationStore()
    payload = {"file_path": "README.md"}
    grant = grants.issue("read_file", payload)
    proposal = ActionProposal(
        action_type="read_file",
        payload=payload,
        authorization_id=grant.authorization_id,
    )

    with (
        patch("app.cognition.action_proposal.owner_control_store", policy),
        patch("app.cognition.action_proposal.authorization_store", grants),
    ):
        result = ActionGate.evaluate_proposal(proposal)

    assert result.allowed is False
    assert result.requires_approval is False
    assert "pause" in result.reason.lower()
    # A hard denial does not consume the grant, but the live emergency-pause API
    # revokes all active grants as an additional defense.
    assert grants.validate(grant.authorization_id, "read_file", payload).valid is True
