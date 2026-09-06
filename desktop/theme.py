"""Theme — the desktop client's palette and Beanie presence states.

Colors and presence states come from the shared design system
(design/tokens.json) via desktop.design_tokens — the SAME file the web client
(frontend/src/design/tokens.ts) imports — so the two clients cannot drift
apart. The embedded fallbacks below exist only so a packaged/frozen desktop
binary still starts if the JSON cannot be located; tests/test_design_tokens.py
pins the fallbacks to the canonical values so even that path cannot rot.

Canonical values (round-21, owner directive): the WEB client is the visual
reference. Two historical desktop drifts are intentionally corrected here:
dark TEXT_SECONDARY/TEXT_MUTED were one shade lighter than the web palette,
and the light theme carried an accent override the web does not have.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)

# Last-resort fallbacks for when design/tokens.json is unavailable (packaged
# binary). MUST equal the canonical tokens — enforced by tests.
_FALLBACK_THEME_COLORS = {
    "dark": {
        "BG_PRIMARY": "#0F172A",
        "BG_SECONDARY": "#1E293B",
        "BG_SURFACE": "#334155",
        "TEXT_PRIMARY": "#F1F5F9",
        "TEXT_SECONDARY": "#94A3B8",
        "TEXT_MUTED": "#64748B",
        "ACCENT": "#3B82F6",
    },
    "light": {
        "BG_PRIMARY": "#F8FAFC",
        "BG_SECONDARY": "#E2E8F0",
        "BG_SURFACE": "#CBD5E1",
        "TEXT_PRIMARY": "#1E293B",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#64748B",
        "ACCENT": "#3B82F6",
    },
}
_FALLBACK_PRESENCE_COLORS = {
    "idle": "#3B82F6",
    "working": "#F59E0B",
    "listening": "#10B981",
    "speaking": "#8B5CF6",
    "offline": "#334155",
    "thinking": "#F59E0B",
    "acting": "#38BDF8",
    "observing": "#38BDF8",
    "success": "#10B981",
    "error": "#EF4444",
    "sleeping": "#334155",
}
_FALLBACK_PRESENCE_DURATIONS = {
    "idle": 3400,
    "working": 1600,
    "listening": 1200,
    "speaking": 1050,
    "offline": 0,
    "thinking": 1600,
    "acting": 2000,
    "observing": 2000,
    "success": 2000,
    "error": 400,
    "sleeping": 5000,
}

try:
    from desktop.design_tokens import PRESENCE_COLORS, PRESENCE_DURATIONS, THEME_COLORS

    _TOKENS_LOADED = True
except Exception:  # pragma: no cover - packaged binary without design/tokens.json
    logger.warning(
        "design/tokens.json unavailable; using embedded fallback palette "
        "(should only happen in packaged builds — run from the repo to pick up the shared design system)"
    )
    THEME_COLORS = _FALLBACK_THEME_COLORS
    PRESENCE_COLORS = _FALLBACK_PRESENCE_COLORS
    PRESENCE_DURATIONS = _FALLBACK_PRESENCE_DURATIONS
    _TOKENS_LOADED = False

BG_PRIMARY = THEME_COLORS["dark"]["BG_PRIMARY"]
BG_SECONDARY = THEME_COLORS["dark"]["BG_SECONDARY"]
BG_SURFACE = THEME_COLORS["dark"]["BG_SURFACE"]
TEXT_PRIMARY = THEME_COLORS["dark"]["TEXT_PRIMARY"]
TEXT_SECONDARY = THEME_COLORS["dark"]["TEXT_SECONDARY"]
TEXT_MUTED = THEME_COLORS["dark"]["TEXT_MUTED"]
ACCENT = THEME_COLORS["dark"]["ACCENT"]


def _is_system_dark() -> bool:
    """Best-effort detection of OS dark mode (Qt 6.5+ has colorScheme, else palette)."""
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                scheme = hints.colorScheme()
                if int(scheme) == 1:
                    return True
                if int(scheme) == 0:
                    return False
            pal = app.palette()
            bg = pal.color(pal.ColorRole.Window)
            return bg.lightness() < 128
    except Exception:
        pass
    return True


def apply_theme(name: str) -> str:
    """Switch the active palette (returns the normalized name).

    Supports 'dark', 'light', 'system' (follows OS). Returns 'dark'/'light'/'system'
    so callers can persist the user's choice while still rendering the resolved palette.
    """
    raw = (name or "dark").strip().lower()
    if raw in ("system", "auto"):
        resolved = "dark" if _is_system_dark() else "light"
        for key, value in THEME_COLORS[resolved].items():
            globals()[key] = value
        return "system"
    normalized = raw if raw in THEME_COLORS else "dark"
    for key, value in THEME_COLORS[normalized].items():
        globals()[key] = value
    return normalized


def _resolved_theme_name(name: str) -> str:
    """Return the concrete 'dark'/'light' that a stored name resolves to."""
    n = (name or "dark").strip().lower()
    if n in ("system", "auto"):
        return "dark" if _is_system_dark() else "light"
    return n if n in THEME_COLORS else "dark"


def _lighten(hex_color: str, factor: float = 0.6) -> QColor:
    c = QColor(hex_color)
    return QColor(
        int(c.red() + (255 - c.red()) * factor),
        int(c.green() + (255 - c.green()) * factor),
        int(c.blue() + (255 - c.blue()) * factor),
    )
