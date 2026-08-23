"""Owner clients may recover only the exact payload bound to an active grant."""

from unittest.mock import patch

from app.cognition.approval_store import ApprovalStore
from app.cognition.owner_control import AuthorizationStore
from app.main import list_authorizations_endpoint


def test_reviewed_grant_lists_exact_executable_scope():
    approvals = ApprovalStore()
    grants = AuthorizationStore()
    payload = {"title": "Exact title", "body": "Exact body"}
    request = approvals.add("conversation", "create_note", payload, "Owner review")
    with patch("app.cognition.owner_control.authorization_store", grants):
        decided = approvals.decide(request.action_id, True)

    with (
        patch("app.main.authorization_store", grants),
        patch("app.cognition.approval_store.approval_store", approvals),
    ):
        result = list_authorizations_endpoint()

    assert len(result["authorizations"]) == 1
    listed = result["authorizations"][0]
    assert listed["authorization_id"] == decided.authorization_id
    assert listed["scope_recoverable"] is True
    assert listed["payload"] == payload
    assert listed["payload_sha256"] == grants.list_active()[0].payload_sha256


def test_direct_or_payload_mismatched_grant_does_not_invent_scope():
    approvals = ApprovalStore()
    grants = AuthorizationStore()
    request = approvals.add(
        "conversation", "create_note", {"title": "Reviewed"}, "Owner review"
    )
    mismatched = grants.issue(
        "create_note", {"title": "Different"}, source_approval_id=request.action_id
    )
    direct = grants.issue("create_note", {"title": "Caller retained this"})

    with (
        patch("app.main.authorization_store", grants),
        patch("app.cognition.approval_store.approval_store", approvals),
    ):
        result = list_authorizations_endpoint()

    by_id = {item["authorization_id"]: item for item in result["authorizations"]}
    for grant in (mismatched, direct):
        assert by_id[grant.authorization_id]["scope_recoverable"] is False
        assert "payload" not in by_id[grant.authorization_id]
