"""Tests for the desktop app's GUI-free Phase 3 pieces: settings + voice tokens."""

import json

import pytest

from desktop.settings import DEFAULTS, DesktopSettings
from desktop.voice_client import DesktopAudioPlayer, DesktopVoiceClient, accumulate_tokens


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch):
    """Force the in-memory fallback: on the owner's machine PySide6 is
    installed, so DesktopSettings reads the REAL persisted app settings
    (their theme is 'system', not the DEFAULTS 'dark') and the defaults
    assertions read the machine instead of the code (owner run
    2026-09-02)."""
    monkeypatch.setattr(DesktopSettings, "_has_qt",
                        staticmethod(lambda: False))


# ── accumulate_tokens (pure helper) ─────────────────────────────────────────
def test_accumulate_tokens_folds_stream():
    parts = []
    assert accumulate_tokens({"type": "message_token", "token": "Hel", "done": False}, parts) is None
    assert accumulate_tokens({"type": "message_token", "token": "lo", "done": False}, parts) is None
    assert accumulate_tokens({"type": "message_token", "token": "!", "done": True}, parts) == "Hello!"
    assert parts == []  # cleared after completion


def test_accumulate_tokens_ignores_non_token_events():
    parts = []
    assert accumulate_tokens({"type": "voice_state", "state": "idle"}, parts) is None
    assert parts == []


def test_accumulate_tokens_handles_missing_token():
    parts = []
    assert accumulate_tokens({"type": "message_token", "done": True}, parts) == ""
    assert parts == []


# ── voice_state routing (new) ───────────────────────────────────────────────
def test_handle_text_routes_voice_state():
    c = DesktopVoiceClient(ws_url="ws://unused", conversation_id="conv-1")
    seen = []
    c.on_voice_state = seen.append
    c._handle_text(json.dumps({"type": "voice_state", "state": "speaking"}))
    c._handle_text(json.dumps({"type": "voice_state", "state": "idle"}))
    assert seen == ["speaking", "idle"]


def test_handle_text_ignores_unknown_and_missing_state():
    c = DesktopVoiceClient(ws_url="ws://unused", conversation_id="conv-1")
    seen = []
    c.on_voice_state = seen.append
    c._handle_text(json.dumps({"type": "voice_transcript", "text": "hi", "is_final": True}))
    c._handle_text(json.dumps({"type": "voice_state"}))  # missing state
    assert seen == [""]  # missing state → empty string, still routed


# ── audio routing (new) ─────────────────────────────────────────────────────
def test_handle_audio_frames_via_on_audio():
    c = DesktopVoiceClient(ws_url="ws://unused", conversation_id="conv-1")
    seen = []
    c.on_audio = seen.append

    # Simulate the _recv_loop's binary branch without a live socket.
    frame = b"\x00\x01\x02\x03"
    if c.on_audio:
        c.on_audio(bytes(frame))
    assert seen == [b"\x00\x01\x02\x03"]


# ── DesktopAudioPlayer (GUI-free; degrades without PyAudio) ─────────────────
def test_audio_player_degrades_without_pyaudio(monkeypatch):
    import desktop.voice_client as vc
    monkeypatch.setattr(vc, "PYAUDIO_AVAILABLE", False)
    player = DesktopAudioPlayer()
    assert player.available is False
    # start() is a no-op when PyAudio is absent; push() is a no-op when stopped.
    player.start()
    assert player.playing is False
    player.push(b"\x00\x00\x01\x00")
    player.stop()  # no-op when not running; must not raise
    assert player.playing is False


def test_audio_player_push_requires_running(monkeypatch):
    import desktop.voice_client as vc
    monkeypatch.setattr(vc, "PYAUDIO_AVAILABLE", False)
    player = DesktopAudioPlayer()
    # push() while stopped is a no-op and must not raise.
    player.push(b"\x00\x00")
    assert player.playing is False


# ── DesktopSettings (in-memory fallback when Qt is absent) ──────────────────
def test_settings_defaults():
    s = DesktopSettings()
    assert s.get("server_url") == DEFAULTS["server_url"]
    assert s.get("wake_word") == "hey_arena"


def test_settings_rejects_unknown_key():
    s = DesktopSettings()
    try:
        s.get("nope")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_settings_all_returns_every_default():
    s = DesktopSettings()
    assert s.all() == DEFAULTS
