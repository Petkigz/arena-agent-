"""
Regression guard: the live WebSocket chat path must route through CognitiveRuntime,
not a raw LLM call. (Phase 1 — one authoritative cognitive path.)
"""

import asyncio
from unittest.mock import MagicMock, patch

from backend.message_router import MessageRouter


def test_chat_routes_through_cognitive_runtime():
    """The chat response path must invoke CognitiveRuntime.process_cognitive_cycle."""
    runtime = MagicMock()
    runtime.process_cognitive_cycle.return_value = {
        "success": True,
        "assistant_reply": "hello from the runtime",
        "session_id": "sess_test",
        "goal_lifecycle_state": "achieved",
    }
    router = MessageRouter(runtime=runtime)

    with patch("backend.message_router.llm_client", create=True) as mock_llm:
        reply = asyncio.run(router._call_cognitive_runtime("hello"))

    assert reply == "hello from the runtime"
    runtime.process_cognitive_cycle.assert_called_once()
    # The whole point of the guard: the raw LLM client must not be called here.
    mock_llm.generate_chat_completion.assert_not_called()


def test_chat_cognitive_runtime_falls_back_gracefully():
    """If the runtime raises, the router returns a safe message instead of crashing."""
    runtime = MagicMock()
    runtime.process_cognitive_cycle.side_effect = RuntimeError("boom")
    router = MessageRouter(runtime=runtime)

    reply = asyncio.run(router._call_cognitive_runtime("hello"))

    assert "Error: boom" in reply
    runtime.process_cognitive_cycle.assert_called_once()


def test_chat_cognitive_runtime_handles_missing_reply():
    """If the cycle succeeds but returns no reply, surface the lifecycle state."""
    runtime = MagicMock()
    runtime.process_cognitive_cycle.return_value = {
        "success": True,
        "assistant_reply": "",
        "goal_lifecycle_state": "deferred",
    }
    router = MessageRouter(runtime=runtime)

    reply = asyncio.run(router._call_cognitive_runtime("hello"))

    assert "deferred" in reply
