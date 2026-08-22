"""Tests for the shared settings store (app/settings_store.py)."""

import json

from app.settings_store import _DEFAULTS, get_settings, update_settings


def _clear_settings_file(monkeypatch, tmp_path):
    """Point the store at a temp file so tests don't touch real data/settings.json."""
    from app import settings_store

    monkeypatch.setattr(settings_store, "_SETTINGS_PATH", tmp_path / "settings.json")


def test_defaults_cover_voice_appearance_and_connection():
    # Everything the user can change from the UI should have a default.
    for key in (
        "wake_word", "voice", "voice_speed", "voice_enabled", "language",
        "noise_suppression", "vad_sensitivity", "response_delay",
        "theme", "font_size", "high_contrast", "large_text", "reduced_motion",
        "server_url", "api_key", "fast_model", "main_model", "lm_studio_url",
    ):
        assert key in _DEFAULTS, f"missing default for {key}"


def test_get_settings_returns_defaults_when_no_file(monkeypatch, tmp_path):
    _clear_settings_file(monkeypatch, tmp_path)
    s = get_settings()
    assert s["wake_word"] == "hey_arena"
    assert s["voice_speed"] == 1.0
    assert s["theme"] == "dark"


def test_update_settings_merges_and_persists(monkeypatch, tmp_path):
    _clear_settings_file(monkeypatch, tmp_path)
    updated = update_settings({"wake_word": "hi android", "voice": "en_GB-alan-medium"})
    assert updated["wake_word"] == "hi android"
    assert updated["voice"] == "en_GB-alan-medium"
    assert updated["theme"] == "dark"  # untouched default survives

    # Persisted to disk.
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data["wake_word"] == "hi android"
    assert data["voice_speed"] == 1.0


def test_update_settings_ignores_none_values(monkeypatch, tmp_path):
    _clear_settings_file(monkeypatch, tmp_path)
    update_settings({"voice_speed": None, "theme": "light"})
    s = get_settings()
    assert s["voice_speed"] == 1.0  # None ignored
    assert s["theme"] == "light"
