"""
Protocol-alignment tests for the Android app ↔ backend voice flow.

The Android app sends `wake_word_detected` (previously unhandled → logged as
"Unknown message type"). These tests pin that the message now routes through the
voice service and transitions the conversation to LISTENING.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from backend.message_router import MessageRouter
from backend.voice.service import VoiceService


def test_message_router_handles_wake_word_detected():
    router = MessageRouter(runtime=None)  # type: ignore
    router.voice_service = AsyncMock()
    router.voice_service.notify_wake_word = AsyncMock()

    msg = {"type": "wake_word_detected", "conversation_id": "android-voice"}
    asyncio.run(router._handle_wake_word_detected(None, msg))

    router.voice_service.notify_wake_word.assert_awaited_once_with("android-voice")


def test_message_router_ignores_wake_word_without_conversation():
    router = MessageRouter(runtime=None)  # type: ignore
    router.voice_service = AsyncMock()
    router.voice_service.notify_wake_word = AsyncMock()

    asyncio.run(router._handle_wake_word_detected(None, {"type": "wake_word_detected"}))

    router.voice_service.notify_wake_word.assert_not_awaited()


def test_voice_service_notify_wake_word_broadcasts_listening():
    service = VoiceService()

    with patch.object(service, "current_conversation_id", None), \
         patch("backend.voice.service.ws_manager.broadcast_to_conversation", new_callable=AsyncMock) as mock_bcast:

        asyncio.run(service.notify_wake_word("android-voice"))

        mock_bcast.assert_awaited_once()
        args, _ = mock_bcast.call_args
        assert args[0] == "android-voice"
        assert args[1]["type"] == "voice_state"
        assert args[1]["state"] == "listening"
