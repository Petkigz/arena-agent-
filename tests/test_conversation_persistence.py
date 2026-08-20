"""
Phase 4d guards: conversation history survives restarts (SQLite persistence),
and an end-to-end chat message flows through the full cognitive runtime.
"""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.database import DatabaseManager
import backend.message_router as mr


@pytest.fixture
def clean_db(tmp_path):
    """A DatabaseManager bound to a temp file, isolated from the module-level db."""
    db_path = str(tmp_path / "assistant.db")
    return DatabaseManager(db_path=db_path)


def test_conversation_messages_roundtrip(clean_db):
    clean_db.add_conversation_message("conv_1", "user", "hello")
    clean_db.add_conversation_message("conv_1", "assistant", "hi there")

    messages = clean_db.get_conversation_messages("conv_1")
    assert messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_conversation_messages_respect_limit(clean_db):
    for i in range(60):
        clean_db.add_conversation_message("conv_2", "user", f"msg {i}")

    messages = clean_db.get_conversation_messages("conv_2", limit=50)
    assert len(messages) == 50
    # Oldest messages trimmed, newest preserved.
    assert messages[0]["content"] == "msg 10"
    assert messages[-1]["content"] == "msg 59"


def test_router_history_survives_restart(clean_db, monkeypatch):
    """Clearing the in-memory cache must NOT lose history — it reloads from SQLite."""
    # Point the router at the temp DB and clear its in-memory cache.
    monkeypatch.setattr(mr, "db", clean_db)
    mr._conversation_histories.clear()

    mr.add_to_history("conv_3", "user", "remember me")
    mr.add_to_history("conv_3", "assistant", "ok, remembered")

    # Simulate a restart: wipe the in-memory cache only.
    mr._conversation_histories.clear()

    history = mr.get_conversation_history("conv_3")
    assert history == [
        {"role": "user", "content": "remember me"},
        {"role": "assistant", "content": "ok, remembered"},
    ]


def test_end_to_end_chat_flows_through_runtime(tmp_path):
    """A chat message routed via _call_cognitive_runtime returns a runtime reply."""
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
    from app.cognition.reasoning_loop import CycleTrace

    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    router = mr.MessageRouter(runtime=runtime)

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ANSWER, confidence=0.9, reason="answer")]
    )
    fake_llm = {"choices": [{"message": {"content": "the runtime answered"}, "index": 0}], "model": "fast"}

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch.object(runtime, "_integrate_phase_modules"), \
         patch("app.llm.llm_client.generate_chat_completion", return_value=fake_llm):

        reply = asyncio.run(router._call_cognitive_runtime("what time is it?"))

    assert reply == "the runtime answered"


def test_conversation_previews_and_ids(clean_db):
    clean_db.add_conversation_message("conv_a", "user", "hello there")
    clean_db.add_conversation_message("conv_a", "assistant", "hi")
    clean_db.add_conversation_message("conv_b", "user", "second chat")

    ids = clean_db.get_conversation_ids()
    assert "conv_a" in ids and "conv_b" in ids

    previews = clean_db.get_conversation_previews()
    by_id = {p["id"]: p for p in previews}
    assert by_id["conv_a"]["title"].startswith("hello there")
    assert by_id["conv_a"]["lastMessage"] == "hi"
    assert by_id["conv_b"]["title"].startswith("second chat")
