"""Exact response → trace correlation survives streaming, history, and restart."""

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from app.database import DatabaseManager
from app.cognition.trace import CognitiveTrace
import backend.message_router as mr


@pytest.fixture
def chat_store(tmp_path, monkeypatch):
    from app.config import settings

    path = tmp_path / "chat.db"
    store = DatabaseManager(str(path))
    monkeypatch.setattr(settings, "DB_PATH", path)
    monkeypatch.setattr(mr, "db", store)
    monkeypatch.setattr(mr, "_conversation_histories", {})
    return store


def test_legacy_database_migration_is_additive_and_repeatable(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        conn.execute(
            "INSERT INTO conversations VALUES (1, 'old', 'assistant', 'Old answer', '2026-01-01')"
        )
    DatabaseManager(str(path))
    reopened = DatabaseManager(str(path))
    assert reopened.get_conversation_messages("old") == [{
        "message_id": 1, "role": "assistant", "content": "Old answer",
        "created_at": "2026-01-01",
    }]


def test_streamed_ids_and_trace_links_survive_history_cache_reset(chat_store):
    mr.add_to_history("chat-a", "user", "A question", message_id="msg-question")
    mr.add_to_history(
        "chat-a", "assistant", "An answer", message_id="msg-answer", trace_id="trace-a",
    )
    before = mr.get_conversation_history("chat-a")
    assert before[1]["trace_id"] == "trace-a"
    mr._conversation_histories.clear()
    after = mr.get_conversation_history("chat-a")
    assert [item["message_id"] for item in after] == ["msg-question", "msg-answer"]
    assert after[1]["trace_id"] == "trace-a"
    assert "trace_id" not in after[0]
    assert all(item["created_at"] for item in after)
    # Opening another DatabaseManager is the on-disk/restart contract, not
    # merely another reference to the router's in-memory cache.
    assert DatabaseManager(chat_store.db_path).get_conversation_messages("chat-a") == after


def test_trace_binding_cannot_be_attached_to_user_row(chat_store):
    with pytest.raises(ValueError, match="Only assistant"):
        chat_store.add_conversation_message("chat", "user", "hi", trace_id="trace-wrong")
    assert chat_store.get_conversation_messages("chat") == []


class RecordingSockets:
    def __init__(self, store):
        self.events = []
        self.store = store

    async def send_to_conversation(self, conversation_id, event):
        if event["type"] == "cognitive_metadata":
            # Any client seeing metadata can already hydrate its exact reply.
            persisted = self.store.get_conversation_messages(conversation_id)
            reply = next(item for item in persisted if item["message_id"] == event["message_id"])
            assert reply["role"] == "assistant"
            assert reply["trace_id"] == event["trace_id"]
        self.events.append(event)

    async def broadcast_to_all(self, event):
        self.events.append(event)

    async def join_conversation(self, *args):
        pass


def test_two_replies_bind_separate_durable_traces_and_matching_token_ids(chat_store, monkeypatch):
    traces = []

    def cycle(user_text, session_id, **kwargs):
        trace = CognitiveTrace(user_input=user_text, session_id=session_id)
        trace.finalize(reply=f"Answer: {user_text}", actions=[], latency=1, goal_verified=False)
        traces.append(trace)
        return {"assistant_reply": trace.assistant_reply, "trace_id": trace.trace_id}

    sockets = RecordingSockets(chat_store)
    monkeypatch.setattr(mr, "ws_manager", sockets)
    router = mr.MessageRouter(SimpleNamespace(process_cognitive_cycle=cycle))
    monkeypatch.setattr(router, "_generate_action_steps", lambda _: [])
    monkeypatch.setattr(router, "_tokenize_response", lambda text: [text])

    async def scenario():
        for question in ("first question", "second question"):
            await router._handle_user_message(None, {
                "conversation_id": "chat-a", "content": question,
                # Client-supplied metadata must not be used as trace authority.
                "trace_id": "owner-injected-trace",
            })

    asyncio.run(scenario())
    metadata = [event for event in sockets.events if event["type"] == "cognitive_metadata"]
    tokens = [event for event in sockets.events if event["type"] == "message_token"]
    assert len(metadata) == len(tokens) == 2
    assert [event["trace_id"] for event in metadata] == [trace.trace_id for trace in traces]
    assert metadata[0]["message_id"] != metadata[1]["message_id"]
    assert [event["message_id"] for event in metadata] == [event["message_id"] for event in tokens]
    mr._conversation_histories.clear()
    replies = [item for item in mr.get_conversation_history("chat-a") if item["role"] == "assistant"]
    assert [item["trace_id"] for item in replies] == [trace.trace_id for trace in traces]
    assert [item["message_id"] for item in replies] == [event["message_id"] for event in metadata]


@pytest.mark.parametrize("broken_result", [None, RuntimeError("provider failure"), {"assistant_reply": "No trace"}])
def test_failed_or_traceless_cycle_cannot_reuse_previous_trace(chat_store, monkeypatch, broken_result):
    def cycle(**kwargs):
        if isinstance(broken_result, Exception):
            raise broken_result
        return broken_result

    sockets = RecordingSockets(chat_store)
    monkeypatch.setattr(mr, "ws_manager", sockets)
    router = mr.MessageRouter(SimpleNamespace(process_cognitive_cycle=cycle))
    router._last_cognitive_results["chat-a"] = {"trace_id": "stale-trace"}
    monkeypatch.setattr(router, "_generate_action_steps", lambda _: [])
    monkeypatch.setattr(router, "_tokenize_response", lambda text: [text])
    asyncio.run(router._handle_user_message(None, {"conversation_id": "chat-a", "content": "New question"}))
    assert not any(event["type"] == "cognitive_metadata" for event in sockets.events)
    assert all("trace_id" not in item for item in chat_store.get_conversation_messages("chat-a"))
