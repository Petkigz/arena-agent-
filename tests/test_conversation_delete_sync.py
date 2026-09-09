"""Owner live report 2026-09-09 — "when I delete the conversations they
don't synchronise the deletion."

Root cause, verified in code: the web store's removeConversation only
filtered LOCAL state (frontend/src/stores/conversationStore.ts), the
backend had no delete at all (no DB method, no WS handler), so the
conversation resurrected from the server previews at the next hydrate —
in every UI.

Contracts pinned here:
- the database is the source of truth: delete_conversation removes
  every message row of ONE conversation and touches no other;
- the WS handler deletes, drops the in-memory history, acks the caller
  AND broadcasts `conversation_deleted` to every connected UI;
- a missing conversation_id is an honest error frame, never a crash;
- the desktop client routes the `conversation_deleted` frame to its
  on_deleted callback (the app refreshes the sidebar and, if the dead
  room was on screen, clears it).
"""

from __future__ import annotations

import asyncio
import json

import pytest

import backend.message_router as mr
from app.database import DatabaseManager


class _FakeWSManager:
    def __init__(self):
        self.sent = []
        self.broadcasts = []

    async def send_to_connection(self, websocket, payload):
        self.sent.append(payload)

    async def broadcast_to_all(self, payload):
        self.broadcasts.append(payload)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    database = DatabaseManager(str(tmp_path / "conv.db"))
    fake_mgr = _FakeWSManager()
    monkeypatch.setattr(mr, "db", database)
    monkeypatch.setattr(mr, "ws_manager", fake_mgr)
    monkeypatch.setattr(mr, "_conversation_histories", {})
    router = mr.MessageRouter(runtime=object())
    return database, fake_mgr, router


# ── the database is the source of truth ─────────────────────────────────────
def test_delete_removes_every_row_of_one_conversation_only(env):
    database, _, _ = env
    database.add_conversation_message("conv_a", "user", "hello there")
    database.add_conversation_message("conv_a", "assistant", "hi!")
    database.add_conversation_message("conv_b", "user", "keep me")
    deleted = database.delete_conversation("conv_a")
    assert deleted == 2
    assert database.get_conversation_messages("conv_a") == []
    assert len(database.get_conversation_messages("conv_b")) == 1
    previews = {p["id"] for p in database.get_conversation_previews()}
    assert previews == {"conv_b"}, "the deleted conversation leaves the previews"


def test_delete_of_an_unknown_conversation_is_honest(env):
    database, _, _ = env
    assert database.delete_conversation("never_existed") == 0


# ── the WS handler synchronizes every UI ────────────────────────────────────
def test_handler_deletes_acks_and_broadcasts(env):
    database, fake_mgr, router = env
    database.add_conversation_message("conv_x", "user", "doomed")
    mr._conversation_histories["conv_x"] = [{"role": "user", "content": "doomed"}]
    asyncio.run(router._handle_delete_conversation(
        object(), {"type": "delete_conversation", "conversation_id": "conv_x"}))
    assert database.get_conversation_messages("conv_x") == []
    assert "conv_x" not in mr._conversation_histories, \
        "the in-memory history is dropped with the rows"
    ack = fake_mgr.sent[0]
    assert ack["type"] == "conversation_deleted"
    assert ack["conversation_id"] == "conv_x"
    assert ack["deleted_messages"] == 1
    assert fake_mgr.broadcasts == [
        {"type": "conversation_deleted", "conversation_id": "conv_x"}]


def test_handler_requires_a_conversation_id(env):
    _, fake_mgr, router = env
    asyncio.run(router._handle_delete_conversation(
        object(), {"type": "delete_conversation"}))
    assert fake_mgr.sent[0]["type"] == "error"
    assert fake_mgr.broadcasts == []


def test_the_router_registers_the_handler(env):
    _, _, router = env
    # the dispatch table must know the new verb
    asyncio.run(router.handle_message(
        object(), {"type": "delete_conversation", "conversation_id": ""}))


# ── the desktop client hears the deletion ───────────────────────────────────
def test_desktop_client_routes_the_deleted_frame():
    from desktop.chat_client import DesktopChatClient as ChatClient

    client = ChatClient()
    heard = []
    client.on_deleted = heard.append
    client._handle_text(json.dumps(
        {"type": "conversation_deleted", "conversation_id": "conv_z"}))
    assert heard == ["conv_z"]


def test_desktop_client_can_ask_for_a_deletion():
    from desktop.chat_client import DesktopChatClient as ChatClient

    client = ChatClient()
    sent = []
    client._send = sent.append  # capture instead of the socket
    client.delete_conversation("conv_z")
    assert sent == [{"type": "delete_conversation",
                     "conversation_id": "conv_z"}]
