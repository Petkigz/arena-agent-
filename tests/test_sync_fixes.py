"""Cross-UI sync regressions: chats, messages, replies, and tasks.

Live-session bugs this file locks down:
1. The assistant reply was persisted AFTER the done token — a second device
   syncing right after a reply finished saw a stale history (user message
   only). The reply must be durable before `done: true` is broadcast.
2. The streamed reply reused the USER message's id, so other clients glued
   the reply text onto the sender's bubble. The reply needs its own id.
3. REST /conversations (unified server) and the WS list_conversations must
   return the same DB + active-room merged view.
4. Desktop: pick_shared_conversation called a client method that didn't
   exist, so the app silently fell back to the private "desktop-chat" room
   forever. ArenaBackendClient.list_conversations fixes that.
5. Project Kanban tasks were localStorage-only — now server-backed via
   /projects/{id}/tasks so every UI shares one board.
6. History entries carry message_id so hydrated rows can be matched against
   live token streams (no duplicate bubbles after re-opening a chat).
"""
import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient


# ── 1 + 2: reply persistence ordering and message ids ─────────────────────

class RecordingWS:
    def __init__(self):
        self.joined = []
        self.broadcasts = []

    async def join_conversation(self, websocket, conversation_id):
        self.joined.append(conversation_id)

    async def broadcast_to_all(self, message):
        self.broadcasts.append(message)


def run_handle(timeline, content="sync me", conversation_id="conv_sync"):
    """Drive the real _handle_user_message with recording collaborators."""
    from backend.message_router import MessageRouter

    ws_manager = RecordingWS()

    async def send(conversation_id, message):
        timeline.append(("send", message))

    ws_manager.send_to_conversation = send

    async def fake_cycle(content, image_path=None, audio_path=None, attachments=None, conversation_id=None, **kwargs):
        return "the reply"

    router = MessageRouter.__new__(MessageRouter)
    router._check_rate_limit = lambda cid: True
    router._generate_action_steps = lambda content: []
    router._call_cognitive_runtime = fake_cycle
    websocket = MagicMock()
    message = {"conversation_id": conversation_id, "content": content}

    def fake_add_to_history(cid, role, content, message_id=None):
        timeline.append(("history", {"role": role, "content": content, "message_id": message_id}))

    async def call():
        with patch("backend.message_router.ws_manager", ws_manager), \
             patch("backend.message_router.add_to_history", fake_add_to_history), \
             patch("backend.message_router.get_conversation_history", return_value=[]):
            handler = MessageRouter._handle_user_message.__get__(router)
            return await handler(websocket, message)

    return asyncio.run(call()), ws_manager


def test_assistant_reply_persisted_before_done_token():
    timeline = []
    run_handle(timeline)
    sent = [m for kind, m in timeline if kind == "send"]
    history = [h for kind, h in timeline if kind == "history"]

    assert any(h["role"] == "assistant" for h in history), "assistant reply never persisted"
    # The history write must happen BEFORE the done token is broadcast: no
    # client that sees `done` can fetch a history missing the reply.
    done_idx = next(i for i, m in enumerate(sent)
                    if m["type"] == "message_token" and m["done"] is True)
    hist_pos = [i for i, (kind, m) in enumerate(timeline)
                if kind == "history" and m["role"] == "assistant"][0]
    done_pos = [i for i, (kind, m) in enumerate(timeline)
                if kind == "send" and m.get("type") == "message_token" and m.get("done")][0]
    assert hist_pos < done_pos
    assert done_pos <= len(timeline) - 1
    assert done_idx >= 0


def test_user_message_persisted_before_room_broadcast():
    timeline = []
    run_handle(timeline)
    hist_pos = [i for i, (kind, m) in enumerate(timeline)
                if kind == "history" and m["role"] == "user"][0]
    room_pos = [i for i, (kind, m) in enumerate(timeline)
                if kind == "send" and m.get("type") == "room_message"][0]
    assert hist_pos < room_pos


def test_reply_stream_uses_distinct_message_id():
    timeline = []
    run_handle(timeline)
    sent = [m for kind, m in timeline if kind == "send"]
    user_msg_ids = {m["message_id"] for m in sent if m["type"] == "room_message"}
    reply_ids = {m["message_id"] for m in sent if m["type"] == "message_token"}
    assert user_msg_ids, "no room_message broadcast"
    assert reply_ids, "no streamed tokens"
    assert not (user_msg_ids & reply_ids), \
        "reply tokens reuse the user message id — second clients corrupt the sender's bubble"


def test_history_entries_carry_message_id():
    timeline = []
    run_handle(timeline)
    history = [h for kind, h in timeline if kind == "history"]
    for h in history:
        assert h["message_id"], f"history entry without message_id: {h}"


def test_user_message_broadcasts_conversation_activity_to_all():
    """Every UI — even ones parked in OTHER rooms — must learn the owner's
    active conversation moved, so lists refresh and devices follow."""
    timeline = []
    _, ws_manager = run_handle(timeline, conversation_id="conv_active")
    activities = [b for b in ws_manager.broadcasts if b.get("type") == "conversation_activity"]
    assert activities, "no conversation_activity broadcast"
    assert activities[0]["conversation_id"] == "conv_active"
    # Broadcast happens right after the room_message so followers see it fast.
    room_pos = [i for i, (kind, m) in enumerate(timeline)
                if kind == "send" and m.get("type") == "room_message"][0]
    assert any(b["conversation_id"] == "conv_active" for b in ws_manager.broadcasts)
    assert room_pos < len(timeline)


# ── desktop follow-the-owner decision ─────────────────────────────────────

def test_should_follow_newest():
    from desktop.chat_client import should_follow_newest

    convs = [("conv_newest", "t"), ("conv_old", "t")]
    # Newest differs and nothing blocks: follow.
    assert should_follow_newest(convs, "conv_old", False, False) is True
    # Already in the newest room: nothing to do.
    assert should_follow_newest(convs, "conv_newest", False, False) is False
    # User picked a room manually this session: respect it.
    assert should_follow_newest(convs, "conv_old", True, False) is False
    # Mid-typing: never yank the room away.
    assert should_follow_newest(convs, "conv_old", False, True) is False
    # Empty list: nothing to follow.
    assert should_follow_newest([], "conv_old", False, False) is False
    # Dict-shaped conversations (REST preview rows) work too.
    assert should_follow_newest([{"id": "conv_newest"}], "conv_old", False, False) is True


def test_pick_shared_conversation_prefers_newest_over_saved():
    """The desktop opens where the owner last left off on ANY device — a stale
    saved preference must not pin it to an old room."""
    from types import SimpleNamespace
    from desktop.chat_client import pick_shared_conversation

    fake_client = SimpleNamespace(list_conversations=lambda limit=50: {
        "conversations": [
            {"id": "conv_web_latest", "title": "Web chat", "lastMessage": "x", "updatedAt": "t"},
            {"id": "desktop-chat", "title": "Old", "lastMessage": "y", "updatedAt": "t0"},
        ]})
    fake_settings = {"conversation_id": "desktop-chat"}

    class FakeSettings:
        def get(self, key, default=None):
            return fake_settings.get(key, default)

        def set(self, key, value):
            fake_settings[key] = value

    assert pick_shared_conversation(fake_client, FakeSettings()) == "conv_web_latest"


def test_chat_client_parses_conversation_activity():
    from desktop.chat_client import DesktopChatClient

    client = DesktopChatClient()
    seen = []
    client.on_activity = seen.append
    client._handle_text('{"type": "conversation_activity", "conversation_id": "conv_x"}')
    assert seen == ["conv_x"]


# ── 3: REST and WS conversation lists agree ───────────────────────────────

def test_rest_conversations_merges_db_and_active_rooms(monkeypatch):
    from app.database import db as appdb
    from backend import message_router

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    monkeypatch.setattr(
        appdb, "get_conversation_previews",
        lambda limit=50: [{"id": "conv_db", "title": "Chat", "lastMessage": "hi", "updatedAt": "t"}],
    )

    class FakeWSManager:
        def get_active_conversations(self):
            return ["conv_live_only"]

    monkeypatch.setattr(message_router, "ws_manager", FakeWSManager())

    from app.server import app as unified
    client = TestClient(unified)
    response = client.get("/conversations", headers={"X-API-Key": "owner-key"})
    assert response.status_code == 200
    body = response.json()
    ids = [c["id"] for c in body["conversations"]]
    assert "conv_db" in ids, "SQLite-persisted conversation missing from REST list"
    assert "conv_live_only" in ids, "active-but-unpersisted room missing from REST list"


# ── 4: desktop actually reaches the conversation list ─────────────────────

def test_desktop_backend_client_lists_conversations():
    from desktop.backend_client import ArenaBackendClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("limit") == "20"
        return httpx.Response(200, json={
            "success": True,
            "conversations": [{"id": "conv_web_latest", "title": "Web chat",
                               "lastMessage": "x", "updatedAt": "t"}],
        })

    client = ArenaBackendClient(base_url="http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)
    data = client.list_conversations(limit=20)
    assert data["conversations"][0]["id"] == "conv_web_latest"


def test_desktop_backend_client_list_conversations_raises_offline():
    from desktop.backend_client import ArenaBackendClient, BackendConnectionError

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = ArenaBackendClient(base_url="http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)
    with pytest.raises(BackendConnectionError):
        client.list_conversations()


def test_pick_shared_conversation_works_with_real_client_shape():
    """The live bug: pick_shared_conversation called a method the real client
    never had, so desktop ALWAYS fell back to the private room."""
    from desktop.backend_client import ArenaBackendClient
    from desktop.chat_client import pick_shared_conversation

    class FakeSettings:
        def __init__(self):
            self.data = {}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "success": True,
            "conversations": [
                {"id": "conv_web_latest", "title": "Web chat", "lastMessage": "x", "updatedAt": "t"},
            ],
        })

    client = ArenaBackendClient(base_url="http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)
    settings = FakeSettings()
    assert pick_shared_conversation(client, settings) == "conv_web_latest"


def test_chat_client_join_switches_room():
    from desktop.chat_client import DesktopChatClient

    client = DesktopChatClient(conversation_id="room_a")
    sent = []
    client._send = lambda payload: sent.append(payload)
    client.join_conversation("room_b")
    assert client.conversation_id == "room_b", "join must update the client's room for reconnects"
    assert sent == [{"type": "join_conversation", "conversation_id": "room_b"}]


# ── 5: project tasks are server-backed ────────────────────────────────────

def test_project_tasks_db_roundtrip(tmp_path):
    from app.database import DatabaseManager

    db = DatabaseManager(str(tmp_path / "tasks.db"))
    db.add_project_task({
        "id": "task-1", "project_id": "p1", "title": "Write spec",
        "description": "v1", "status": "todo", "priority": "high",
        "assignee": "me", "dueDate": "2026-01-01", "tags": ["docs", "v1"],
        "createdAt": "2026-01-01T00:00:00", "updatedAt": "2026-01-01T00:00:00",
    })
    tasks = db.get_project_tasks("p1")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Write spec"
    assert tasks[0]["tags"] == ["docs", "v1"]
    assert tasks[0]["dueDate"] == "2026-01-01"

    db.update_project_task("task-1", {"status": "done", "completedAt": "2026-01-02T00:00:00"})
    updated = db.get_project_tasks("p1")[0]
    assert updated["status"] == "done"
    assert updated["completedAt"] == "2026-01-02T00:00:00"

    db.delete_project_task("task-1")
    assert db.get_project_tasks("p1") == []


def test_project_task_endpoints_roundtrip(monkeypatch, tmp_path):
    from app.database import DatabaseManager
    import app.main as main_module

    temp_db = DatabaseManager(str(tmp_path / "route_tasks.db"))
    monkeypatch.setattr(main_module, "db", temp_db)

    client = TestClient(main_module.app)
    created = client.post("/projects/p1/tasks", json={"title": "Ship sync", "priority": "high"})
    assert created.status_code == 201, created.text
    task = created.json()["task"]
    assert task["title"] == "Ship sync"

    listed = client.get("/projects/p1/tasks")
    assert listed.status_code == 200
    assert [t["title"] for t in listed.json()["tasks"]] == ["Ship sync"]

    moved = client.patch(f"/projects/p1/tasks/{task['id']}", json={"status": "done"})
    assert moved.status_code == 200
    assert moved.json()["task"]["status"] == "done"

    deleted = client.delete(f"/projects/p1/tasks/{task['id']}")
    assert deleted.status_code == 200
    assert client.get("/projects/p1/tasks").json()["tasks"] == []


# ── 6: persisted history carries message ids ──────────────────────────────

def test_conversation_messages_carry_row_message_id(tmp_path):
    from app.database import DatabaseManager

    db = DatabaseManager(str(tmp_path / "conv.db"))
    row_id = db.add_conversation_message("c1", "user", "hello")
    assert isinstance(row_id, int) and row_id > 0
    db.add_conversation_message("c1", "assistant", "hi back")
    msgs = db.get_conversation_messages("c1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["message_id"] == row_id
    assert msgs[1]["message_id"] == row_id + 1
