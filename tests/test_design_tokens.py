"""Design-token single source of truth: web + desktop must consume design/tokens.json.

The web client is the canonical visual reference (owner directive, round-21).
These tests make drift structurally impossible rather than merely detectable:

- design/tokens.json is schema-validated (11 Beanie states, both themes).
- desktop reads the JSON via desktop.design_tokens (pure Python — no Qt).
- desktop.theme (PySide6) serves exactly those values, and its embedded
  fallback is pinned to canonical so even a packaged binary cannot rot.
- the web tailwind config + Beanie orb import the SAME JSON (no hardcoded
  presence hexes), and index.css CSS variables (the runtime theming
  mechanism) equal the canonical values.

This file intentionally parses the web sources from Python so the whole
design system is guarded by the Python suite even on machines without node.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOKENS_PATH = REPO / "design" / "tokens.json"
INDEX_CSS = REPO / "frontend" / "src" / "index.css"
TAILWIND_CONFIG = REPO / "frontend" / "tailwind.config.js"
ORB_TSX = REPO / "frontend" / "src" / "components" / "presence" / "ReactiveBeanieOrb.tsx"

EXPECTED_STATES = {
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
}


def _tokens() -> dict:
    return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))


def _canonical_theme_colors(tokens: dict) -> dict:
    """Canonical values in desktop.theme's THEME_COLORS shape."""
    out: dict = {"dark": {}, "light": {}}
    for theme in ("dark", "light"):
        spec = tokens["color"]["themes"][theme]
        out[theme] = {
            "BG_PRIMARY": spec["background"]["primary"],
            "BG_SECONDARY": spec["background"]["secondary"],
            "BG_SURFACE": spec["background"]["surface"],
            "TEXT_PRIMARY": spec["text"]["primary"],
            "TEXT_SECONDARY": spec["text"]["secondary"],
            "TEXT_MUTED": spec["text"]["muted"],
            "ACCENT": spec["accent"],
        }
    return out


def _canonical_presence(tokens: dict) -> tuple[dict, dict]:
    states = tokens["beanie"]["states"]
    colors = {state: spec["color"] for state, spec in states.items()}
    durations = {state: spec["duration_ms"] for state, spec in states.items()}
    return colors, durations


# --------------------------------------------------------------------------
# design/tokens.json itself
# --------------------------------------------------------------------------


def test_tokens_json_schema():
    tokens = _tokens()
    for theme in ("dark", "light"):
        spec = tokens["color"]["themes"][theme]
        for part in ("primary", "secondary", "surface"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["background"][part]), (theme, part)
        for part in ("primary", "secondary", "muted"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["text"][part]), (theme, part)
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["accent"]), theme
    for part in ("primary", "success", "warning", "error"):
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", tokens["color"]["accent"][part]), part
    for group, keys in (
        ("knowledge_node_types", ("concept", "entity", "memory", "conversation", "file", "other")),
        ("memory_types", ("episodic", "semantic", "procedural", "conversation", "empty")),
    ):
        palette = tokens["color"][group]
        for key in keys:
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", palette[key]), (group, key)
    assert tokens["typography"]["base_font_size_px"] > 0
    assert "Inter" in tokens["typography"]["font_family"]


def test_tokens_json_beanie_states_are_the_eleven_presence_states():
    states = _tokens()["beanie"]["states"]
    assert set(states) == EXPECTED_STATES
    for state, spec in states.items():
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["color"]), state
        assert isinstance(spec["duration_ms"], int) and spec["duration_ms"] >= 0, state
        assert isinstance(spec["label"], str) and spec["label"], state


# --------------------------------------------------------------------------
# Desktop side (pure-Python loader; Qt-guarded theme checks)
# --------------------------------------------------------------------------


def test_desktop_loader_serves_canonical_tokens():
    from desktop import design_tokens

    tokens = _tokens()
    assert design_tokens.TOKENS == tokens
    assert design_tokens.THEME_COLORS == _canonical_theme_colors(tokens)
    colors, durations = _canonical_presence(tokens)
    assert design_tokens.PRESENCE_COLORS == colors
    assert design_tokens.PRESENCE_DURATIONS == durations


def test_desktop_loader_rejects_bad_tokens(tmp_path):
    from desktop import design_tokens

    good = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))

    def _write(payload: dict) -> Path:
        path = tmp_path / "broken.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    # Missing state
    broken = json.loads(json.dumps(good))
    del broken["beanie"]["states"]["acting"]
    with pytest.raises(design_tokens.DesignTokenError, match="11 presence states"):
        design_tokens.load_tokens(_write(broken))

    # Bad hex
    broken = json.loads(json.dumps(good))
    broken["color"]["themes"]["dark"]["text"]["secondary"] = "slate-400"
    with pytest.raises(design_tokens.DesignTokenError, match="hex"):
        design_tokens.load_tokens(_write(broken))

    # Missing file
    with pytest.raises(design_tokens.DesignTokenError, match="cannot read"):
        design_tokens.load_tokens(tmp_path / "absent.json")


def _import_desktop_theme():
    """Import desktop.theme headless: use the real Qt when available, else stub QColor.

    Only QColor is touched at import time (palette logic itself is pure data),
    so a stub lets every environment verify the canonical values — the skip
    pattern used by widget tests would leave the palette unguarded on
    machines without a GL runtime.
    """
    import importlib
    import sys
    import types

    try:
        from PySide6.QtGui import QColor  # noqa: F401

        return importlib.import_module("desktop.theme"), False
    except Exception:
        pass

    saved = {k: sys.modules.get(k) for k in ("PySide6", "PySide6.QtGui", "desktop.theme")}
    pyside6 = types.ModuleType("PySide6")
    gui = types.ModuleType("PySide6.QtGui")

    class _QColor:  # minimal stand-in; palette tests never render
        def __init__(self, *args, **kwargs):
            self._args = args

    gui.QColor = _QColor
    pyside6.QtGui = gui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = gui
    sys.modules.pop("desktop.theme", None)
    try:
        return importlib.import_module("desktop.theme"), True
    finally:
        for key, module in saved.items():
            if module is not None:
                sys.modules[key] = module
            else:
                sys.modules.pop(key, None)


def test_desktop_theme_serves_canonical_tokens():
    theme, _stubbed = _import_desktop_theme()

    tokens = _tokens()
    assert theme.THEME_COLORS == _canonical_theme_colors(tokens)
    colors, durations = _canonical_presence(tokens)
    assert theme.PRESENCE_COLORS == colors
    assert theme.PRESENCE_DURATIONS == durations
    assert theme._TOKENS_LOADED is True
    # Dark module-level constants match the dark palette.
    assert theme.BG_PRIMARY == tokens["color"]["themes"]["dark"]["background"]["primary"]
    assert theme.TEXT_SECONDARY == tokens["color"]["themes"]["dark"]["text"]["secondary"]
    assert theme.TEXT_MUTED == tokens["color"]["themes"]["dark"]["text"]["muted"]
    assert theme.ACCENT == tokens["color"]["themes"]["dark"]["accent"]


def test_desktop_theme_fallback_pinned_to_canonical():
    """The embedded fallback (packaged-binary path) must equal canonical."""
    theme, _stubbed = _import_desktop_theme()

    tokens = _tokens()
    assert theme._FALLBACK_THEME_COLORS == _canonical_theme_colors(tokens)
    colors, durations = _canonical_presence(tokens)
    assert theme._FALLBACK_PRESENCE_COLORS == colors
    assert theme._FALLBACK_PRESENCE_DURATIONS == durations


def test_desktop_theme_modules_compile_without_qt():
    """Palette modules must stay syntactically valid where no Qt exists at all."""
    import ast

    for name in ("desktop/theme.py", "desktop/design_tokens.py"):
        source = (REPO / name).read_text(encoding="utf-8")
        ast.parse(source)


def test_apply_theme_rebinds_importer_modules():
    """Live theme switching must repaint importer modules, not just desktop.theme.

    Regression guard for the round-21 rendering bug: pages bind theme constants
    at import time (`from desktop.theme import BG_PRIMARY, ...`), so mutating
    desktop.theme's globals alone left every page painting the palette that was
    active at import. apply_theme now rebinds the importers' copies.
    """
    import sys
    import types

    theme, _stubbed = _import_desktop_theme()

    fake_page = types.ModuleType("desktop.fakepage")
    fake_page.BG_PRIMARY = theme.BG_PRIMARY  # simulate an import-time copy
    fake_page.TEXT_MUTED = theme.TEXT_MUTED
    fake_page.UNRELATED = "untouched"
    foreign = types.ModuleType("notarena")
    foreign.BG_PRIMARY = theme.BG_PRIMARY
    sys.modules["desktop.fakepage"] = fake_page
    sys.modules["notarena"] = foreign
    try:
        theme.apply_theme("light")
        light = theme.THEME_COLORS["light"]
        assert fake_page.BG_PRIMARY == light["BG_PRIMARY"]
        assert fake_page.TEXT_MUTED == light["TEXT_MUTED"]
        assert fake_page.UNRELATED == "untouched"  # unrelated attributes untouched
        assert foreign.BG_PRIMARY == theme.THEME_COLORS["dark"]["BG_PRIMARY"]  # non-desktop modules untouched

        theme.apply_theme("dark")
        assert fake_page.BG_PRIMARY == theme.THEME_COLORS["dark"]["BG_PRIMARY"]
    finally:
        sys.modules.pop("desktop.fakepage", None)
        sys.modules.pop("notarena", None)
        theme.apply_theme("dark")


def test_desktop_voice_banner_uses_presence_tokens():
    """The chat voice banner must not hand-copy Beanie presence hexes."""
    chat_source = (REPO / "desktop" / "pages" / "chat.py").read_text(encoding="utf-8")
    assert "PRESENCE_COLORS" in chat_source
    for hex_color in ("'#10B981'", "'#F59E0B'", "'#8B5CF6'", '"#10B981"', '"#F59E0B"', '"#8B5CF6"'):
        assert hex_color not in chat_source, f"hardcoded presence color {hex_color} returned to chat.py"


# --------------------------------------------------------------------------
# Web side (parsed from Python so node is not required to catch drift)
# --------------------------------------------------------------------------


def _css_variables(css: str, selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"selector {selector!r} not found in index.css"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1)))


def test_index_css_variables_equal_canonical():
    css = INDEX_CSS.read_text(encoding="utf-8")
    tokens = _tokens()
    for selector, theme in ((":root", "dark"), ("html.light", "light")):
        spec = tokens["color"]["themes"][theme]
        variables = _css_variables(css, selector)
        for part in ("primary", "secondary", "surface"):
            assert variables[f"--color-background-{part}"] == spec["background"][part], (theme, part)
        for part in ("primary", "secondary", "muted"):
            assert variables[f"--color-text-{part}"] == spec["text"][part], (theme, part)


def test_tailwind_config_consumes_tokens_json():
    source = TAILWIND_CONFIG.read_text(encoding="utf-8")
    # The config must import the shared token file...
    assert "design/tokens.json" in source
    # ...build the presence palette from the Beanie states (all 11, not a hand-picked 4)...
    assert "tokens.beanie.states" in source
    # ...and derive accent + legacy dark background from tokens too.
    assert "tokens.color.accent" in source
    assert "tokens.color.themes.dark.background" in source
    # No hardcoded presence hexes may remain.
    for hex_color in ("'#8B5CF6'", "'#38BDF8'", "'#EF4444'"):
        assert hex_color not in source, f"hardcoded presence color {hex_color} returned to tailwind.config.js"


def test_orb_component_consumes_tokens_json():
    source = ORB_TSX.read_text(encoding="utf-8")
    assert "design/tokens" in source, "ReactiveBeanieOrb must import the shared tokens"
    assert "BEANIE_STATES" in source
    # The hardcoded per-state COLORS map must not return.
    assert "const COLORS" not in source
    for state in ("thinking", "acting", "observing", "success", "error", "sleeping"):
        assert f"{state}: '#" not in source, f"hardcoded color for state {state!r} returned to the orb"


def test_web_and_desktop_presence_palettes_are_identical():
    """The one drift class this whole file exists to prevent: two presence palettes.

    The desktop loader reads the JSON in Python; the web orb reads it in TS.
    Both must serve exactly the same 11 colors.
    """
    from desktop import design_tokens

    orb_source = ORB_TSX.read_text(encoding="utf-8")
    assert "design/tokens" in orb_source  # web orb consumes the same file
    tokens = _tokens()
    colors, durations = _canonical_presence(tokens)
    assert design_tokens.PRESENCE_COLORS == colors
    assert design_tokens.PRESENCE_DURATIONS == durations
    assert set(design_tokens.PRESENCE_COLORS) == EXPECTED_STATES


def test_web_semantic_palettes_consumed_from_tokens():
    """Duplicated semantic color maps (node types, memory types, voice states) must import tokens.

    KnowledgeGraphView and NodeDetailPanel used to hand-copy the SAME node-type
    dict — two copies that could drift. LearningPatterns hand-copied memory-type
    colors; ListeningIndicator hand-copied voice-state colors.
    """
    checks = (
        (REPO / "frontend/src/components/knowledge/KnowledgeGraphView.tsx", "KNOWLEDGE_NODE_TYPE_COLORS"),
        (REPO / "frontend/src/components/knowledge/NodeDetailPanel.tsx", "KNOWLEDGE_NODE_TYPE_COLORS"),
        (REPO / "frontend/src/components/exploration/LearningPatterns.tsx", "MEMORY_TYPE_COLORS"),
        (REPO / "frontend/src/components/beanie/ListeningIndicator.tsx", "beanieColor"),
    )
    for path, marker in checks:
        source = path.read_text(encoding="utf-8")
        assert marker in source, f"{path.name} must use the shared design tokens ({marker})"
        assert "design/tokens" in source, f"{path.name} must import from design/tokens"

    # The hand-copied dicts must not return.
    graph_source = (REPO / "frontend/src/components/knowledge/KnowledgeGraphView.tsx").read_text(encoding="utf-8")
    detail_source = (REPO / "frontend/src/components/knowledge/NodeDetailPanel.tsx").read_text(encoding="utf-8")
    for source in (graph_source, detail_source):
        assert "concept: '#8B5CF6'" not in source
    learning_source = (REPO / "frontend/src/components/exploration/LearningPatterns.tsx").read_text(encoding="utf-8")
    assert "episodic: '#8B5CF6'" not in learning_source
