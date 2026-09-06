"""
Tests for the phone-audio → backend STT routing (browser-free voice ingest).

The Android app streams raw int16 PCM over WebSocket binary frames. These tests
verify byte→float32 conversion, energy-based utterance detection, and that a
detected utterance is transcribed + routed to the cognitive runtime (or degrades
gracefully when STT is unavailable).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import numpy as np

from backend.voice.remote_audio import RemoteAudioBuffer
from backend.voice.service import VoiceService


def _int16_pcm(samples: np.ndarray) -> bytes:
    """float samples in [-1,1] → int16 little-endian PCM bytes (as Android sends)."""
    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def _speech_frame(duration_ms: int = 100, rate: int = 16000, amp: float = 0.5, freq: int = 440) -> bytes:
    n = int(rate * duration_ms / 1000)
    t = np.arange(n) / rate
    return _int16_pcm(amp * np.sin(2 * np.pi * freq * t))


def _silence_frame(duration_ms: int = 100, rate: int = 16000) -> bytes:
    n = int(rate * duration_ms / 1000)
    return _int16_pcm(np.zeros(n))


def test_bytes_to_float32_conversion():
    buf = RemoteAudioBuffer()
    arr = buf._bytes_to_float32(_int16_pcm(np.array([0.0, 0.5, -0.5], dtype=np.float32)))
    assert arr.dtype == np.float32
    assert abs(arr[1] - 0.5) < 0.01
    assert abs(arr[2] + 0.5) < 0.01


def test_utterance_detected_after_speech_then_silence():
    buf = RemoteAudioBuffer()
    utterances = []
    buf.on_utterance = utterances.append

    # 500ms speech, then 800ms silence (> 700ms max_silence_ms).
    for _ in range(5):
        buf.ingest(_speech_frame(100))
    for _ in range(8):
        buf.ingest(_silence_frame(100))

    assert len(utterances) == 1
    assert len(utterances[0]) > 0


def test_short_utterance_ignored():
    buf = RemoteAudioBuffer()
    utterances = []
    buf.on_utterance = utterances.append

    # Only 100ms speech (below min_utterance_ms=250) then long silence.
    buf.ingest(_speech_frame(100))
    for _ in range(8):
        buf.ingest(_silence_frame(100))

    assert len(utterances) == 0


def test_leading_silence_ignored():
    buf = RemoteAudioBuffer()
    utterances = []
    buf.on_utterance = utterances.append

    # Leading silence (not speaking) is dropped, then real speech.
    for _ in range(5):
        buf.ingest(_silence_frame(100))
    for _ in range(5):
        buf.ingest(_speech_frame(100))
    for _ in range(8):
        buf.ingest(_silence_frame(100))

    assert len(utterances) == 1


def test_reset_clears_buffer():
    buf = RemoteAudioBuffer()
    utterances = []
    buf.on_utterance = utterances.append

    buf.ingest(_speech_frame(100))
    buf.reset()
    for _ in range(8):
        buf.ingest(_silence_frame(100))

    assert len(utterances) == 0


def test_voice_service_ingest_delegates_to_buffer():
    service = VoiceService()
    with patch.object(service.remote_audio, "ingest") as mock_ingest:
        service.ingest_remote_audio(b"abc")
    mock_ingest.assert_called_once_with(b"abc")


def test_transcribe_routes_transcript_to_cognitive_runtime():
    service = VoiceService()
    service.current_conversation_id = "android-voice"

    fake_stt = AsyncMock()
    fake_stt.transcribe_async.return_value = {"text": "open firefox", "language": "en", "segments": []}

    # Route through the same path a PC transcript uses (_handle_transcript),
    # which broadcasts + sends to the message router.
    with patch.object(service, "_get_remote_stt", return_value=fake_stt), \
         patch.object(service, "_handle_transcript", new_callable=AsyncMock) as mock_handle:

        asyncio.run(service._transcribe_remote_utterance(np.zeros(1600, dtype=np.float32)))

        mock_handle.assert_awaited_once()
        args, kwargs = mock_handle.call_args
        assert args[0] == "open firefox"
        assert kwargs.get("is_final") is True


def test_transcribe_reports_when_stt_unavailable():
    service = VoiceService()
    service.current_conversation_id = "android-voice"

    with patch.object(service, "_get_remote_stt", return_value=None), \
         patch.object(service, "_handle_transcript", new_callable=AsyncMock) as mock_handle, \
         patch("backend.voice.service.ws_manager") as mock_ws:
        mock_ws.broadcast_to_conversation = AsyncMock()

        # Must not raise or route anywhere, but must expose the component failure.
        asyncio.run(service._transcribe_remote_utterance(np.zeros(1600, dtype=np.float32)))
        mock_handle.assert_not_awaited()
        payloads = [call.args[1] for call in mock_ws.broadcast_to_conversation.await_args_list]
        errors = [payload for payload in payloads if payload.get("type") == "voice_status"]
        assert errors and errors[0]["component"] == "remote_stt"


def test_transcribe_skips_empty_text():
    service = VoiceService()
    service.current_conversation_id = "android-voice"

    fake_stt = AsyncMock()
    fake_stt.transcribe_async.return_value = {"text": "", "language": None, "segments": []}

    with patch.object(service, "_get_remote_stt", return_value=fake_stt), \
         patch.object(service, "_handle_transcript", new_callable=AsyncMock) as mock_handle:

        asyncio.run(service._transcribe_remote_utterance(np.zeros(1600, dtype=np.float32)))
        mock_handle.assert_not_awaited()
