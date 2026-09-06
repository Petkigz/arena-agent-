"""Android design tokens: the third client consumes the same design system.

The Android app (android/, Kotlin + Jetpack Compose) is a full Arena client —
kept per the design review's salvage rule (networking/websocket/models kept,
presentation layer revived). These tests pin it to design/tokens.json exactly
the way desktop and web are pinned, so the three clients cannot drift:

- Theme.kt dark/light Material schemes must equal the canonical themes
  (role → token mapping documented in Theme.kt).
- The Compose PresenceStatus enum must equal the 11 Beanie states
  (color + pulse duration) from tokens.beanie.states.
- Screens must stay theme-driven (no hardcoded Color(0xFF…) outside the
  token-sourced enum), and the landing must follow the restrained design.

Parsed from Python so the guard runs in CI without an Android toolchain.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOKENS_PATH = REPO / "design" / "tokens.json"
THEME_KT = REPO / "android/app/src/main/java/com/arena/voice/ui/Theme.kt"
BEANIE_KT = REPO / "android/app/src/main/java/com/arena/voice/ui/screens/BeanieScreen.kt"
CHAT_KT = REPO / "android/app/src/main/java/com/arena/voice/ui/screens/ChatScreen.kt"
MAIN_KT = REPO / "android/app/src/main/java/com/arena/voice/MainActivity.kt"
SCAFFOLD_KT = REPO / "android/app/src/main/java/com/arena/voice/ui/AppScaffold.kt"

# Material 3 role → design token path (Theme.kt documents this mapping).
_ROLE_TO_TOKEN = {
    "primary": ("color", "accent", "primary"),
    "secondary": ("color", "accent", "success"),
    "tertiary": ("color", "accent", "warning"),
    "error": ("color", "accent", "error"),
    "background": ("background", "primary"),
    "surface": ("background", "secondary"),
    "surfaceVariant": ("background", "surface"),
    "onBackground": ("text", "primary"),
    "onSurface": ("text", "primary"),
    "onSurfaceVariant": ("text", "secondary"),
    "outline": ("text", "muted"),
}


def _tokens() -> dict:
    return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))


def _scheme_values(source: str, scheme_name: str) -> dict[str, str]:
    match = re.search(rf"val {scheme_name} = \w+ColorScheme\((.*?)\n\)", source, re.DOTALL)
    assert match, f"{scheme_name} not found in Theme.kt"
    values: dict[str, str] = {}
    for role, hex_value in re.findall(r"(\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{8})\)", match.group(1)):
        values[role] = f"#{hex_value[2:]}"
    return values


def test_android_theme_matches_canonical_tokens():
    source = THEME_KT.read_text(encoding="utf-8")
    tokens = _tokens()
    for scheme_name, theme in (("DarkColorScheme", "dark"), ("LightColorScheme", "light")):
        values = _scheme_values(source, scheme_name)
        canonical_theme = tokens["color"]["themes"][theme]
        for role, path in _ROLE_TO_TOKEN.items():
            # Accent paths are rooted at the token root; theme paths at the theme.
            expected = tokens if path[0] == "color" else canonical_theme
            for part in path:
                expected = expected[part]
            assert values.get(role) == expected.upper(), (
                f"Theme.kt {scheme_name}.{role} = {values.get(role)} "
                f"but canonical {theme} token is #{expected}"
            )


def test_android_dynamic_color_is_opt_in():
    """Arena's palette by default; Material You only when explicitly requested."""
    source = THEME_KT.read_text(encoding="utf-8")
    match = re.search(r"dynamicColor:\s*Boolean\s*=\s*(\w+)", source)
    assert match, "dynamicColor parameter not found in Theme.kt"
    assert match.group(1) == "false", "dynamicColor must default to false (Arena palette, not wallpaper)"


def test_android_presence_enum_matches_beanie_states():
    """The Compose PresenceStatus enum must equal the shared 11-state machine."""
    source = BEANIE_KT.read_text(encoding="utf-8")
    match = re.search(r"enum class PresenceStatus.*?\{(.*?)\n\}", source, re.DOTALL)
    assert match, "PresenceStatus enum not found"
    entries = dict(
        (name.lower(), (f"#{color[2:]}", int(duration)))
        for name, color, duration in re.findall(
            r"(\w+)\(Color\(0x([0-9A-Fa-f]{8})\),\s*(\d+)\)", match.group(1)
        )
    )
    states = _tokens()["beanie"]["states"]
    assert set(entries) == set(states), (
        f"Android presence states {sorted(entries)} != canonical {sorted(states)}"
    )
    for state, spec in states.items():
        color, duration = entries[state]
        assert color == spec["color"].upper(), f"presence {state}: {color} != {spec['color']}"
        assert duration == spec["duration_ms"], f"presence {state}: {duration}ms != {spec['duration_ms']}ms"


def test_android_screens_are_theme_driven():
    """No hardcoded hex colors outside the token-sourced presence enum."""
    screens_dir = REPO / "android/app/src/main/java/com/arena/voice/ui/screens"
    for path in sorted(screens_dir.glob("*.kt")):
        source = path.read_text(encoding="utf-8")
        if path.name == "BeanieScreen.kt":
            # Strip the enum block (the token-sourced presence palette) first.
            source = re.sub(r"enum class PresenceStatus.*?\n\}", "", source, flags=re.DOTALL)
        literals = re.findall(r"Color\(0x[0-9A-Fa-f]{8}\)", source)
        assert not literals, f"{path.name} reintroduced hardcoded colors: {literals}"


def test_android_landing_is_restrained():
    """Review section 2, mirrored from the desktop landing (round-21d)."""
    source = BEANIE_KT.read_text(encoding="utf-8")
    assert "Ask Beanie anything…" in source
    assert "What are we working on today?" in source
    assert "Good " in source  # time-based greeting
    assert "TextButton" in source  # subtle suggestion chips
    assert "OutlinedButton" not in source  # the old 56dp tiles are gone
    assert "Talk to Beanie" not in source  # giant talk button removed (mic is in the composer)

    # Resting status message matches the desktop landing question.
    main = MAIN_KT.read_text(encoding="utf-8")
    assert '"What are we working on today?"' in main

    # The landing composer routes to the conversation (primary surface).
    scaffold = SCAFFOLD_KT.read_text(encoding="utf-8")
    assert "onLandingSubmit" in scaffold
    main = MAIN_KT.read_text(encoding="utf-8")
    assert "handleLandingSubmit" in main


def test_android_voice_chip_toggles_voice():
    """The 'Talk to me' chip must toggle voice, not map to an empty prompt."""
    main = MAIN_KT.read_text(encoding="utf-8")
    assert '"talk" -> null' not in main
    assert re.search(r'action == "talk"', main)


def test_android_chat_is_theme_driven_and_conforms():
    """Chat follows the shared visual language: token radius, theme-driven bubbles."""
    source = CHAT_KT.read_text(encoding="utf-8")
    assert "Color(0x" not in source
    assert "RoundedCornerShape(16.dp)" in source  # bubble + composer radius = token xxl
    # Presence-driven voice pill (not hand-copied hexes).
    assert "PresenceStatus.LISTENING.color" in source
    assert "PresenceStatus.THINKING.color" in source
    assert "PresenceStatus.SPEAKING.color" in source
