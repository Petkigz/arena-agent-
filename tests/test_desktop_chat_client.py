"""Tests for the desktop chat WebSocket client (GUI-free parsing logic)."""

import json

from desktop.chat_client import DesktopChatClient


def _client():
    return DesktopChatClient(ws_url="ws://unused", conversation_id="conv-1")


def test_parse_conversation_list():
    c = _client()
    seen = []
    c.on_conversation_list = seen.append
    c._handle_text(json.dumps({
        "type": "conversation_list",
        "conversations": [
            {"id": "a", "title": "First"},
            {"conversation_id": "b", "title": "Second"},
            {"id": "", "title": "ignored"},
        ],
    }))
    assert seen == [[("a", "First"), ("b", "Second")]]


def test_parse_history():
    c = _client()
    seen = []
    c.on_history = lambda cid, h: seen.append((cid, h))
    c._handle_text(json.dumps({
        "type": "conversation_history",
        "conversation_id": "conv-1",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    }))
    assert seen == [("conv-1", [("user", "hi"), ("assistant", "hello")])]


def test_parse_streamed_tokens():
    c = _client()
    tokens = []
    c.on_token = lambda t, d: tokens.append((t, d))
    c._handle_text(json.dumps({"type": "message_token", "token": "Hello", "done": False}))
    c._handle_text(json.dumps({"type": "message_token", "token": " world", "done": True}))
    assert tokens == [("Hello", False), (" world", True)]


def test_parse_created():
    c = _client()
    seen = []
    c.on_created = lambda cid, t: seen.append((cid, t))
    c._handle_text(json.dumps({"type": "conversation_created", "conversation_id": "x", "title": "New"}))
    assert seen == [("x", "New")]
