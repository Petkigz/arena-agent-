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
FRONTEND_DIR = REPO / "frontend"
INDEX_CSS = FRONTEND_DIR / "src" / "index.css"
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
            "BG_PANEL": spec["background"]["panel"],
            "BG_ELEVATED": spec["background"]["elevated"],
            "BORDER_SUBTLE": spec["border"]["subtle"],
            "BORDER_ACTIVE": spec["border"]["active"],
            "GLOW_PRIMARY": spec["glow"]["primary"],
            "GLOW_SECONDARY": spec["glow"]["secondary"],
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
        for part in ("primary", "secondary", "surface", "panel", "elevated"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["background"][part]), (theme, part)
        assert 0 < spec["background"]["panel_alpha"] <= 1, (theme, "panel_alpha")
        for part in ("primary", "secondary", "muted"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["text"][part]), (theme, part)
        for part in ("subtle", "active"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["border"][part]), (theme, part)
        for part in ("primary", "secondary"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["glow"][part]), (theme, part)
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", spec["accent"]), theme
    for part in ("primary", "secondary", "success", "warning", "error"):
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", tokens["color"]["accent"][part]), part
    for group, keys in (
        ("knowledge_node_types", ("concept", "entity", "memory", "conversation", "file", "other")),
        ("memory_types", ("episodic", "semantic", "procedural", "conversation", "empty")),
    ):
        palette = tokens["color"][group]
        for key in keys:
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", palette[key]), (group, key)
    for name in ("sm_px", "md_px", "lg_px", "xl_px", "xxl_px", "full_px"):
        assert isinstance(tokens["radius"][name], int) and tokens["radius"][name] >= 0, name
    radius_tokens = {k: v for k, v in tokens["radius"].items() if k.endswith("_px")}
    assert radius_tokens == {"sm_px": 4, "md_px": 6, "lg_px": 8, "xl_px": 12, "xxl_px": 16, "full_px": 9999}
    assert tokens["spacing"]["unit_px"] == 4
    for name in ("caption", "body", "subtitle", "title", "display"):
        assert isinstance(tokens["typography"]["scale_px"][name], int), name
    for name in ("regular", "semibold", "bold"):
        assert tokens["typography"]["weights"][name] in (400, 500, 600, 700, 800), name
    for name in ("sm", "DEFAULT", "md", "lg", "xl", "2xl", "inner"):
        assert isinstance(tokens["shadow"][name], str) and tokens["shadow"][name], name
    assert isinstance(tokens["motion"]["base_ms"], int) and tokens["motion"]["base_ms"] > 0
    assert isinstance(tokens["focus"]["ring_width_px"], int) and tokens["focus"]["ring_width_px"] > 0
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
        for part in ("primary", "secondary", "surface", "elevated"):
            assert variables[f"--color-background-{part}"] == spec["background"][part], (theme, part)
        # The panel is the translucency: the token hex composed with its alpha.
        panel_hex, alpha = spec["background"]["panel"], spec["background"]["panel_alpha"]
        expected_panel = "rgba({}, {}, {}, {})".format(
            int(panel_hex[1:3], 16), int(panel_hex[3:5], 16), int(panel_hex[5:7], 16), alpha
        )
        assert variables["--color-background-panel"] == expected_panel, (theme, "panel")
        for part in ("subtle", "active"):
            assert variables[f"--color-border-{part}"] == spec["border"][part], (theme, part)
        for part in ("primary", "secondary"):
            assert variables[f"--color-glow-{part}"] == spec["glow"][part], (theme, part)
        for part in ("primary", "secondary", "muted"):
            assert variables[f"--color-text-{part}"] == spec["text"][part], (theme, part)


def test_glow_and_panel_vocabulary_reaches_the_web_app():
    """Atmosphere (21q): glow/panel/border tokens must be consumed, not just declared."""
    tailwind = TAILWIND_CONFIG.read_text(encoding="utf-8")
    assert "tokens.color.themes.dark.glow" in tailwind, "boxShadow glow no longer derived from tokens"
    assert "panel: 'var(--color-background-panel)'" in tailwind, "translucent panel color dropped from tailwind"
    assert "subtle: 'var(--color-border-subtle)'" in tailwind, "border.subtle dropped from tailwind"

    composer = (FRONTEND_DIR / "src" / "components" / "chat" / "ChatInput.tsx").read_text(encoding="utf-8")
    assert "focus:shadow-glow" in composer, "composer focus glow removed"
    assert "border-border-subtle" in composer, "composer subtle border removed"

    context = (FRONTEND_DIR / "src" / "components" / "layout" / "ContextPanel.tsx").read_text(encoding="utf-8")
    assert "bg-background-panel" in context, "context rail translucency removed"
    assert "border-border-subtle" in context, "context rail subtle border removed"


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


# --------------------------------------------------------------------------
# Fine-tune layer (round-21c): desktop QSS must stay on the canonical scales
# --------------------------------------------------------------------------

_RADIUS_RE = re.compile(r"border-radius:\s*(\d+)px")
_FONT_RE = re.compile(r"font-size:\s*(\d+)px")


def _desktop_sources():
    return list((REPO / "desktop").rglob("*.py"))


def test_desktop_qss_radius_on_token_scale():
    """Every border-radius in desktop QSS must be a canonical radius token value."""
    tokens = _tokens()
    allowed = {tokens["radius"][name] for name in ("sm_px", "md_px", "lg_px", "xl_px", "xxl_px", "full_px")}
    for path in _desktop_sources():
        for match in _RADIUS_RE.finditer(path.read_text(encoding="utf-8")):
            value = int(match.group(1))
            assert value in allowed, f"{path.name}: border-radius {value}px is off the token scale {sorted(allowed)}"


def test_desktop_qss_font_sizes_on_token_scale():
    """Every font-size in desktop QSS must be a canonical type-scale step."""
    tokens = _tokens()
    allowed = set(tokens["typography"]["scale_px"].values())
    for path in _desktop_sources():
        for match in _FONT_RE.finditer(path.read_text(encoding="utf-8")):
            value = int(match.group(1))
            assert value in allowed, f"{path.name}: font-size {value}px is off the type scale {sorted(allowed)}"


def test_desktop_styles_have_professional_states():
    """QSS helpers must cover hover/pressed/focus/disabled like the web baseline."""
    styles_source = (REPO / "desktop" / "styles.py").read_text(encoding="utf-8")
    for state in (":hover", ":pressed", ":focus", ":disabled"):
        assert state in styles_source, f"styles.py lost the {state} state"
    # Values come from tokens, not literals.
    assert "RADIUS" in styles_source and "SPACING" in styles_source and "FOCUS_RING_WIDTH_PX" in styles_source
    assert "border-radius: 10px" not in styles_source  # old off-scale button radius


def test_desktop_bubbles_match_web_composer_baseline():
    """Message bubbles use the web bubble geometry (rounded-2xl, px-4 py-2.5)."""
    bubble_source = (REPO / "desktop" / "pages" / "message_bubble.py").read_text(encoding="utf-8")
    assert "border-radius: 16px" in bubble_source
    assert "padding: 10px 16px" in bubble_source
    assert "border-radius: 14px" not in bubble_source  # old off-scale radius

    chat_source = (REPO / "desktop" / "pages" / "chat.py").read_text(encoding="utf-8")
    assert "_composer_style()" in chat_source  # composer mirrors web rounded-2xl
    assert "border-radius: 9999px" in chat_source  # voice banner is a true pill


def test_context_panel_is_progressive():
    """The context panel must be collapsible (progressive, not permanent)."""
    context_source = (REPO / "desktop" / "widgets" / "context.py").read_text(encoding="utf-8")
    assert "def set_collapsed" in context_source
    assert "def toggle_collapsed" in context_source
    app_source = (REPO / "desktop" / "app.py").read_text(encoding="utf-8")
    assert 'context_collapsed' in app_source  # choice persisted
    settings_source = (REPO / "desktop" / "settings.py").read_text(encoding="utf-8")
    assert '"context_collapsed": True' in settings_source  # registered default (bool-normalized, progressive)


def test_web_shadow_scale_consumes_tokens():
    config_source = TAILWIND_CONFIG.read_text(encoding="utf-8")
    assert "tokens.shadow" in config_source
    # The hardcoded shadow literals must not return.
    assert "0 25px 50px -12px rgba(0, 0, 0, 0.25)" not in config_source


# --------------------------------------------------------------------------
# Shell hierarchy (round-21d, review sections 2/3/5/7)
# --------------------------------------------------------------------------


def test_beanie_landing_source_is_restrained():
    """Review section 2: no giant quick-action tiles; greeting + composer + subtle chips."""
    source = (REPO / "desktop" / "pages" / "beanie.py").read_text(encoding="utf-8")
    assert "setMinimumHeight(56)" not in source  # the old tile height
    assert "_talk_btn" not in source  # giant talk button removed (mic is in the composer)
    assert "Ask Beanie anything" in source  # landing composer placeholder
    assert "Good " in source  # time-based greeting
    assert "What are we working on today?" in source  # resting message
    assert "_chip_style" in source  # subtle suggestions


def test_sidebar_source_groups_navigation():
    """Review section 5: grouped sections with an owner area; flat nav items."""
    source = (REPO / "desktop" / "widgets" / "sidebar.py").read_text(encoding="utf-8")
    for section in ("Conversations", "Workspace", "Tools", "Owner", "System"):
        assert f'("{section}",' in source, f"sidebar lost the {section} section"
    assert "Owner Control" in source and "owner_control" in source
    assert "_nav_style" in source and "background: transparent" in source


def test_landing_composer_wired_and_context_progressive_by_default():
    """Landing submits route to the conversation; context hidden unless wanted."""
    app_source = (REPO / "desktop" / "app.py").read_text(encoding="utf-8")
    assert "_landing_submit" in app_source
    assert "on_submit=self._landing_submit" in app_source
    assert '"context_collapsed": True' in (REPO / "desktop" / "settings.py").read_text(encoding="utf-8")

    chat_source = (REPO / "desktop" / "pages" / "chat.py").read_text(encoding="utf-8")
    assert 'QPushButton("➤")' in chat_source  # icon send button, not text


# --------------------------------------------------------------------------
# Polish layer (round-21h): motion + theme-aware details, token-driven
# --------------------------------------------------------------------------


def test_desktop_scrollbars_are_theme_aware():
    """No raw OS scrollbars over the Arena palette (parity with web index.css)."""
    styles_source = (REPO / "desktop" / "styles.py").read_text(encoding="utf-8")
    assert "def _app_style" in styles_source
    assert "QScrollBar::handle:vertical" in styles_source
    assert "QScrollBar::handle:vertical:hover" in styles_source  # web: thumb:hover muted
    for value in ("BG_SECONDARY", "BG_SURFACE", "TEXT_MUTED"):  # theme-fresh, not literals
        assert value in styles_source.split("def _app_style")[1]

    app_source = (REPO / "desktop" / "app.py").read_text(encoding="utf-8")
    assert app_source.count("setStyleSheet(_app_style())") >= 2  # startup + theme refresh


def test_desktop_sidebar_items_have_hover_state():
    sidebar_source = (REPO / "desktop" / "widgets" / "sidebar.py").read_text(encoding="utf-8")
    assert sidebar_source.count("QListWidget::item:hover") == 2  # construct + refresh_theme


def test_web_animations_derive_from_motion_tokens():
    config_source = TAILWIND_CONFIG.read_text(encoding="utf-8")
    assert "tokens.motion" in config_source
    # The hardcoded durations must not return.
    for literal in ("'pulse 2s", "'pulse 1s", "fadeIn 0.3s"):
        assert literal not in config_source


def test_web_page_transitions_use_motion_tokens():
    """The live framer-motion page transitions read the shared tokens."""
    for rel in (
        "frontend/src/app/routes/DesktopLayout.tsx",
        "frontend/src/app/routes/MobileLayout.tsx",
        "frontend/src/components/animations/PageTransition.tsx",
    ):
        source = (REPO / rel).read_text(encoding="utf-8")
        assert "MOTION.base_ms / 1000" in source, f"{rel} lost the token-driven duration"
        assert "duration: 0.25" not in source


# --------------------------------------------------------------------------
# 21l review: one product, three shells — the Context rail (agent's mind)
# --------------------------------------------------------------------------


def test_desktop_live_context_rail():
    """Desktop = command center: Mission / Working on / Memory / Tools."""
    source = (REPO / "desktop" / "widgets" / "context.py").read_text(encoding="utf-8")
    for section in ("MISSION", "WORKING ON", "MEMORY", "TOOLS"):
        assert section in source, f"Live Context rail lost the {section} section"
    # The rail consumes the same context dict as the inline card…
    assert "def set_context(self, context: dict)" in source
    # …and the streamed tool events (update-by-label, like web/Android).
    assert "def set_tool_activity" in source
    assert "in_progress" in source and "complete" in source
    assert "def set_status" in source  # structured connection state, not a text dump

    app = (REPO / "desktop" / "app.py").read_text(encoding="utf-8")
    assert "self.context.set_context(context or {})" in app  # rail fed from working context
    assert "_handle_action_step" in app                      # action_step → rail
    assert "self.context.clear_tools()" in app               # fresh send → fresh timeline


def test_desktop_client_parses_action_steps():
    """The desktop chat client handles the action_step WS events the web renders."""
    source = (REPO / "desktop" / "chat_client.py").read_text(encoding="utf-8")
    assert 't == "action_step"' in source
    assert "on_action_step" in source


def test_web_context_panel_is_the_agents_mind():
    """Web ContextPanel: Mission / Working on / Memory / Tools — not a metrics
    sidebar (Statistics / Knowledge Graph / Current Chat removed)."""
    source = (REPO / "frontend" / "src" / "components" / "layout" / "ContextPanel.tsx").read_text(encoding="utf-8")
    for section in ("Mission", "Working on", "Memory", "Tools"):
        assert section in source, f"ContextPanel lost the {section} section"
    # Dashboard noise is gone…
    assert "Statistics" not in source
    assert "Knowledge Graph" not in source
    assert "Current Chat" not in source
    # …tool activity reuses the semantic ActionSteps renderer…
    assert "ActionSteps" in source
    test = (REPO / "frontend" / "src" / "test" / "components" / "ContextPanel.test.tsx").read_text(encoding="utf-8")
    assert "agent-mind sections" in test


def test_context_vocabulary_is_shared_across_all_three_shells():
    """One product, three shells: the same context concept on web (reference),
    desktop (command center) and Android (quiet, progressive)."""
    web = (REPO / "frontend" / "src" / "components" / "layout" / "ContextPanel.tsx").read_text(encoding="utf-8")
    desktop = (REPO / "desktop" / "widgets" / "context.py").read_text(encoding="utf-8")
    android = (REPO / "android" / "app" / "src" / "main" / "java" / "com" / "arena" / "voice" / "ui" / "components" / "WorkingContext.kt").read_text(encoding="utf-8")
    # Mission / goal
    assert ("Mission" in web) and ("MISSION" in desktop) and ("objective" in android)
    # Working on / project
    assert ("Working on" in web) and ("WORKING ON" in desktop) and ("project" in android)
    # Memory
    assert ("Memory" in web) and ("MEMORY" in desktop) and ("memories" in android)
    # Tools / activity
    assert ("Tools" in web) and ("TOOLS" in desktop)
    assert "ToolActivityTimeline" in (REPO / "android" / "app" / "src" / "main" / "java" / "com" / "arena" / "voice" / "ui" / "components" / "ToolActivity.kt").read_text(encoding="utf-8")
