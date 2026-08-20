"""
Regression tests for voice-pipeline graceful degradation and wiring fixes:

1. VoiceService routes transcripts through the *current* message router
   (read from the module at call time), not an import-time stale None.
2. SpeechToTextService.start() returns cleanly when faster-whisper is absent.
3. VoiceActivityDetector construction is safe when PyTorch is absent.
"""

from unittest.mock import AsyncMock, patch

from backend.voice.service import VoiceService
from backend.voice.stt import SpeechToTextService
from backend.voice.vad import VoiceActivityDetector
import backend.message_router as message_router_module


def test_stt_start_graceful_when_whisper_absent(monkeypatch):
    monkeypatch.setattr("backend.voice.stt.WhisperModel", None)
    stt = SpeechToTextService(model_size="tiny")
    # Must not raise (previously raised TypeError: 'NoneType' object is not callable).
    stt.start()
    assert stt.is_running is False


def test_vad_construction_safe_when_torch_absent(monkeypatch):
    monkeypatch.setattr("backend.voice.vad.torch", None)
    # Previously raised AttributeError: 'NoneType' has no attribute 'hub'.
    vad = VoiceActivityDetector(threshold=0.5)
    assert vad.model is None


def test_voice_service_uses_current_message_router():
    """_handle_transcript must read the router from the module at call time."""
    service = VoiceService()
    service.current_conversation_id = "conv-1"

    mock_router = AsyncMock()
    # Simulate what initialize_message_router() does at startup.
    message_router_module.message_router = mock_router

    try:
        import asyncio
        asyncio.run(service._handle_transcript("open firefox", is_final=True))
    finally:
        message_router_module.message_router = None

    # The transcript must be routed into the cognitive runtime via the router.
    assert mock_router.handle_message.called
    call_args, _call_kwargs = mock_router.handle_message.call_args
    # handle_message(websocket=None, message={...})
    assert call_args[0] is None
    message = call_args[1]
    assert message["type"] == "user_message"
    assert message["content"] == "open firefox"
    assert message["conversation_id"] == "conv-1"
