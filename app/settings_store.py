"""Shared backend settings store (cross-platform).

Persists a small settings dict (wake word, voice, speed, theme, server URL, …)
to data/settings.json so the web, desktop, and Android clients share one source
of truth instead of each keeping their own localStorage/QSettings/DataStore.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from app.config import settings
from app.utils.logger import app_logger

_SETTINGS_PATH = settings.DATA_DIR / "settings.json"

_DEFAULTS: Dict[str, Any] = {
    # Voice
    "wake_word": "hey_arena",
    "voice": "en_US-lessac-medium",
    "voice_speed": 1.0,
    "voice_enabled": True,
    "language": "en_US",
    "noise_suppression": True,
    "vad_sensitivity": 50,      # 0-100 (0 = least sensitive)
    "response_delay": 500,      # ms before the assistant starts speaking
    # Appearance
    "theme": "dark",
    "font_size": "medium",
    "high_contrast": False,
    "large_text": False,
    "reduced_motion": False,
    # Connection / models
    "server_url": "http://localhost:8000",
    "api_key": "",
    "fast_model": "",
    "main_model": "",
    "lm_studio_url": "",
}


def get_settings() -> Dict[str, Any]:
    """Return the merged settings dict (defaults + persisted)."""
    if _SETTINGS_PATH.exists():
        try:
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**_DEFAULTS, **data}
        except Exception as e:  # noqa: BLE001
            app_logger.warning(f"Could not read settings file: {e}")
    return dict(_DEFAULTS)


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a partial patch into the settings and persist it."""
    current = get_settings()
    for key, value in patch.items():
        if value is not None:
            current[key] = value
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        app_logger.error(f"Could not persist settings: {e}")
    return current
