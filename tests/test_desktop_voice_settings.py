"""Tests for the desktop app's GUI-free Phase 3 pieces: settings + voice tokens."""

from desktop.settings import DEFAULTS, DesktopSettings
from desktop.voice_client import accumulate_tokens


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
