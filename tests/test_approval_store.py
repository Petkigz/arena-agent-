"""
Approval-store + action_approval flow tests (the previously-dead message).
"""

import asyncio
from unittest.mock import AsyncMock, patch

from app.cognition.approval_store import ApprovalStore, approval_store
from backend.message_router import MessageRouter


def test_approval_store_add_decide():
    store = ApprovalStore()
    req = store.add("conv-1", "send_email", {"to": "a@b.com"}, "Level 3")
    assert req.status == "pending"
    assert len(store.list_pending()) == 1

    decided = store.decide(req.action_id, approved=True, note="ok")
    assert decided.status == "approved"
    assert store.list_pending() == []


def test_approval_store_unknown_id():
    store = ApprovalStore()
    assert store.decide("nope", True) is None


def test_message_router_handles_action_approval():
    router = MessageRouter(runtime=None)  # type: ignore
    ws = object()  # a non-None fake websocket so the send branch is taken

    # Seed a pending request.
    req = approval_store.add("conv-1", "send_email", {"to": "a@b.com"}, "Level 3")

    with patch("backend.message_router.ws_manager.send_to_connection", new_callable=AsyncMock) as mock_send:
        asyncio.run(router._handle_action_approval(ws, {
            "type": "action_approval",
            "actionId": req.action_id,
            "approved": True,
        }))

    assert approval_store.get(req.action_id).status == "approved"
    mock_send.assert_awaited_once()


def test_message_router_action_approval_unknown_id():
    router = MessageRouter(runtime=None)  # type: ignore
    ws = object()
    with patch("backend.message_router.ws_manager.send_to_connection", new_callable=AsyncMock) as mock_send:
        asyncio.run(router._handle_action_approval(ws, {
            "type": "action_approval",
            "actionId": "does_not_exist",
            "approved": True,
        }))
    mock_send.assert_awaited_once()
    args, _ = mock_send.call_args
    assert args[1]["status"] == "not_found"
