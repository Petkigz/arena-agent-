"""Theme — mirrors frontend index.css dark + light palettes.

Extracted from desktop/app.py monolith (P2 code-quality fix).
"""

from __future__ import annotations

from PySide6.QtGui import QColor

THEME_COLORS = {
    "dark": {
        "BG_PRIMARY": "#0F172A",
        "BG_SECONDARY": "#1E293B",
        "BG_SURFACE": "#334155",
        "TEXT_PRIMARY": "#F1F5F9",
        "TEXT_SECONDARY": "#CBD5E1",
        "TEXT_MUTED": "#94A3B8",
        "ACCENT": "#3B82F6",
    },
    "light": {
        "BG_PRIMARY": "#F8FAFC",
        "BG_SECONDARY": "#E2E8F0",
        "BG_SURFACE": "#CBD5E1",
        "TEXT_PRIMARY": "#1E293B",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#64748B",
        "ACCENT": "#2563EB",
    },
}

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


PRESENCE_COLORS = {
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
PRESENCE_DURATIONS = {
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


def _lighten(hex_color: str, factor: float = 0.6) -> QColor:
    c = QColor(hex_color)
    return QColor(
        int(c.red() + (255 - c.red()) * factor),
        int(c.green() + (255 - c.green()) * factor),
        int(c.blue() + (255 - c.blue()) * factor),
    )
