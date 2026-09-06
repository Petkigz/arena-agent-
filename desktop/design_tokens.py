"""Design tokens — programmatic access to design/tokens.json.

The single source of truth for the Arena design system, shared by every
client (web, desktop, future mobile). The web client (frontend/) is the
canonical visual reference; this module lets the desktop client consume the
SAME file instead of hand-copying hex values — the duplication that caused
the desktop/web palette drift.

This module deliberately imports NO Qt (and nothing else from the desktop
package) so it is usable from tests, build scripts and non-GUI tooling on
any platform, including headless CI.

A missing or malformed design/tokens.json is a hard error: fail loudly,
never silently fall back to stale constants (callers such as desktop.theme
own their own last-resort fallback, pinned to canonical values by tests).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = [
    "DesignTokenError",
    "TOKENS",
    "THEME_COLORS",
    "PRESENCE_COLORS",
    "PRESENCE_DURATIONS",
    "PRESENCE_LABELS",
    "FONT_FAMILY",
    "BASE_FONT_SIZE_PX",
    "load_tokens",
    "tokens_path",
]


class DesignTokenError(RuntimeError):
    """design/tokens.json is missing or does not match the expected schema."""


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

_BEANIE_STATES = (
    "idle",
    "working",
    "listening",
    "speaking",
    "offline",
    "thinking",
    "acting",
    "observing",
    "success",
    "error",
    "sleeping",
)

_THEME_KEYS = ("BG_PRIMARY", "BG_SECONDARY", "BG_SURFACE", "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED", "ACCENT")


def tokens_path() -> Path:
    """Absolute path to design/tokens.json (<repo>/design/tokens.json)."""
    # desktop/design_tokens.py -> <repo>/desktop/design_tokens.py
    return Path(__file__).resolve().parent.parent / "design" / "tokens.json"


def _require(mapping: Any, key: str, where: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        raise DesignTokenError(f"design tokens: missing '{key}' in {where}")
    return mapping[key]


def _hex(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _HEX_RE.match(value):
        raise DesignTokenError(f"design tokens: {where} must be a 6-digit hex color, got {value!r}")
    return value.upper()


def _validate(tokens: dict) -> None:
    color = _require(tokens, "color", "root")
    themes = _require(color, "themes", "color")
    for theme_name in ("dark", "light"):
        theme = _require(themes, theme_name, "color.themes")
        background = _require(theme, "background", f"color.themes.{theme_name}")
        text = _require(theme, "text", f"color.themes.{theme_name}")
        for part, source in (("primary", background), ("secondary", background), ("surface", background)):
            _hex(_require(source, part, f"color.themes.{theme_name}.background"), f"{theme_name}.background.{part}")
        for part in ("primary", "secondary", "muted"):
            _hex(_require(text, part, f"color.themes.{theme_name}.text"), f"{theme_name}.text.{part}")
        _hex(_require(theme, "accent", f"color.themes.{theme_name}"), f"{theme_name}.accent")
    accent = _require(color, "accent", "color")
    for part in ("primary", "success", "warning", "error"):
        _hex(_require(accent, part, "color.accent"), f"color.accent.{part}")

    beanie = _require(tokens, "beanie", "root")
    states = _require(beanie, "states", "beanie")
    if set(states) != set(_BEANIE_STATES):
        raise DesignTokenError(
            "design tokens: beanie.states must be exactly the 11 presence states "
            f"{sorted(_BEANIE_STATES)}, got {sorted(states)}"
        )
    for state in _BEANIE_STATES:
        spec = _require(states, state, "beanie.states")
        _hex(_require(spec, "color", f"beanie.states.{state}"), f"beanie.states.{state}.color")
        duration = _require(spec, "duration_ms", f"beanie.states.{state}")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            raise DesignTokenError(f"design tokens: beanie.states.{state}.duration_ms must be a non-negative int")
        label = _require(spec, "label", f"beanie.states.{state}")
        if not isinstance(label, str) or not label:
            raise DesignTokenError(f"design tokens: beanie.states.{state}.label must be a non-empty string")

    typography = _require(tokens, "typography", "root")
    size = _require(typography, "base_font_size_px", "typography")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise DesignTokenError("design tokens: typography.base_font_size_px must be a positive int")
    family = _require(typography, "font_family", "typography")
    if not isinstance(family, str) or not family:
        raise DesignTokenError("design tokens: typography.font_family must be a non-empty string")


def load_tokens(path: str | Path | None = None) -> dict:
    """Load and validate design/tokens.json. Raises DesignTokenError on any problem."""
    target = Path(path) if path is not None else tokens_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise DesignTokenError(f"design tokens: cannot read {target}: {exc}") from exc
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DesignTokenError(f"design tokens: invalid JSON in {target}: {exc}") from exc
    if not isinstance(tokens, dict):
        raise DesignTokenError(f"design tokens: root of {target} must be an object")
    _validate(tokens)
    return tokens


def theme_colors(tokens: dict) -> dict:
    """Map tokens to desktop.theme's THEME_COLORS shape ({dark/light: {BG_*, ..., ACCENT}})."""
    themes: dict = {"dark": {}, "light": {}}
    for theme_name in ("dark", "light"):
        theme = tokens["color"]["themes"][theme_name]
        themes[theme_name] = {
            "BG_PRIMARY": theme["background"]["primary"].upper(),
            "BG_SECONDARY": theme["background"]["secondary"].upper(),
            "BG_SURFACE": theme["background"]["surface"].upper(),
            "TEXT_PRIMARY": theme["text"]["primary"].upper(),
            "TEXT_SECONDARY": theme["text"]["secondary"].upper(),
            "TEXT_MUTED": theme["text"]["muted"].upper(),
            "ACCENT": theme["accent"].upper(),
        }
    return themes


def presence_colors(tokens: dict) -> dict:
    """Map tokens to desktop.theme's PRESENCE_COLORS shape ({state: '#HEX'})."""
    states = tokens["beanie"]["states"]
    return {state: spec["color"].upper() for state, spec in states.items()}


def presence_durations(tokens: dict) -> dict:
    """Map tokens to desktop.theme's PRESENCE_DURATIONS shape ({state: ms})."""
    states = tokens["beanie"]["states"]
    return {state: spec["duration_ms"] for state, spec in states.items()}


def presence_labels(tokens: dict) -> dict:
    """Human-readable state labels ({state: 'Working'}), e.g. for desktop tooltips."""
    states = tokens["beanie"]["states"]
    return {state: spec["label"] for state, spec in states.items()}


TOKENS: dict = load_tokens()
THEME_COLORS: dict = theme_colors(TOKENS)
PRESENCE_COLORS: dict = presence_colors(TOKENS)
PRESENCE_DURATIONS: dict = presence_durations(TOKENS)
PRESENCE_LABELS: dict = presence_labels(TOKENS)
FONT_FAMILY: str = TOKENS["typography"]["font_family"]
BASE_FONT_SIZE_PX: int = TOKENS["typography"]["base_font_size_px"]

# Static shape check: THEME_COLORS keys must stay compatible with theme.apply_theme,
# which does `for key, value in THEME_COLORS[name].items(): globals()[key] = value`.
assert all(sorted(theme) == sorted(_THEME_KEYS) for theme in THEME_COLORS.values()), (
    "desktop.design_tokens: THEME_COLORS keys drifted from theme.apply_theme expectations"
)
