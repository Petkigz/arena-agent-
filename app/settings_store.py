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
    # Hardware profile (owner statement 2026-09-13 — this was always
    # meant to live in system settings and had been dropped/forgotten;
    # model-lane sizing, readiness, and planning read it). Editable via
    # POST /settings {"hardware": {...}}; partial patches merge.
    "hardware": {
        "cpu": "Intel Core i9-14900K",
        "gpu_model": "AMD Radeon RX 580",
        "vram_gb": 8,
        "ram_gb": 48,
        "ram_type": "DDR5",
        "planned_gpu": "16 GB VRAM card (owner-planned upgrade, 2026-09)",
        "notes": (
            "Polaris: ROCm unsupported; Vulkan is the GPU path on "
            "Windows. Main-lane model files should fit fully in VRAM "
            "(<= ~6 GB at 8 GB VRAM); revisit on the 16 GB card."
        ),
        "updated_at": "2026-09-13T00:00:00+00:00",
    },
}


def get_hardware() -> Dict[str, Any]:
    """The recorded owner hardware profile (never None, fail-open)."""
    try:
        hw = get_settings().get("hardware")
        return dict(hw) if isinstance(hw, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


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
        if value is None:
            continue
        # The hardware profile merges field-by-field: patching one value
        # (e.g. vram_gb after the owner's planned GPU swap) must not wipe
        # the recorded siblings.
        if key == "hardware" and isinstance(value, dict):
            merged = dict(current.get("hardware") or {})
            merged.update({k: v for k, v in value.items() if v is not None})
            from datetime import datetime, timezone
            merged["updated_at"] = datetime.now(timezone.utc).isoformat()
            current[key] = merged
        else:
            current[key] = value
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        app_logger.error(f"Could not persist settings: {e}")
    return current
