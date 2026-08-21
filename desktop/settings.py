"""Persistent desktop-app settings.

Wraps QSettings so the rest of the app doesn't depend on Qt directly, and so the
logic is unit-testable without a display. QSettings is created lazily — importing
this module is safe even where Qt GUI can't initialize.
"""

from __future__ import annotations

from typing import Any, Dict


DEFAULTS: Dict[str, Any] = {
    "server_url": "http://localhost:8000",
    "wake_word": "hey_arena",
    "voice_speed": 1.0,
    "minimize_to_tray": True,
    "notifications_enabled": True,
}


class DesktopSettings:
    """Key/value settings persisted via QSettings (or in-memory in tests)."""

    def __init__(self, org: str = "Arena", app: str = "Beanie"):
        self._org = org
        self._app = app
        self._qs = None  # lazily-created QSettings (needs QApplication in real runs)

    # ── internal QSettings accessor ─────────────────────────────────────────
    def _settings(self):
        if self._qs is None:
            from PySide6.QtCore import QSettings  # local import: safe in tests
            self._qs = QSettings(self._org, self._app)
        return self._qs

    # ── API ─────────────────────────────────────────────────────────────────
    def get(self, key: str) -> Any:
        if key not in DEFAULTS:
            raise KeyError(key)
        if self._qs is None and not self._has_qt():
            return DEFAULTS[key]
        try:
            return self._settings().value(key, DEFAULTS[key])
        except Exception:
            return DEFAULTS[key]

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        try:
            self._settings().setValue(key, value)
        except Exception:
            pass

    def all(self) -> Dict[str, Any]:
        return {k: self.get(k) for k in DEFAULTS}

    @staticmethod
    def _has_qt() -> bool:
        try:
            from PySide6.QtCore import QSettings  # noqa: F401
            return True
        except Exception:
            return False
