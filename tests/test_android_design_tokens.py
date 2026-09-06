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
UI = REPO / "android/app/src/main/java/com/arena/voice/ui"
THEME_KT = UI / "theme" / "Theme.kt"
COLORS_KT = UI / "theme" / "Colors.kt"
MOTION_KT = UI / "theme" / "Motion.kt"
SPACING_KT = UI / "theme" / "Spacing.kt"
SHAPES_KT = UI / "theme" / "Shapes.kt"
ELEVATION_KT = UI / "theme" / "Elevation.kt"
PRESENCE_KT = UI / "components" / "BeaniePresence.kt"
TOP_BAR_KT = UI / "components" / "BeanieTopBar.kt"
COMPOSER_KT = UI / "components" / "BeanieComposer.kt"
MESSAGE_KT = UI / "components" / "BeanieMessage.kt"
TOOL_KT = UI / "components" / "ToolActivity.kt"
WORKING_CONTEXT_KT = UI / "components" / "WorkingContext.kt"
DRAWER_KT = UI / "components" / "ConversationDrawer.kt"
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
    assert match, f"{scheme_name} not found in Colors.kt"
    values: dict[str, str] = {}
    for role, hex_value in re.findall(r"(\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{8})\)", match.group(1)):
        values[role] = f"#{hex_value[2:]}"
    return values


def test_android_theme_matches_canonical_tokens():
    source = COLORS_KT.read_text(encoding="utf-8")
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
                f"Colors.kt {scheme_name}.{role} = {values.get(role)} "
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
    source = PRESENCE_KT.read_text(encoding="utf-8")
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


def test_android_chat_is_composition_only():
    """21j review: ChatScreen wires state; visuals live in ui/components."""
    source = CHAT_KT.read_text(encoding="utf-8")
    assert "Color(0x" not in source
    for piece in (
        "BeanieTopBar(", "BeanieEmptyState(", "BeanieMessage(",
        "VoiceStatusIndicator(", "WorkingContextAffordance(", "BeanieComposer(",
        "ConversationDrawer(",
    ):
        assert piece in source, f"ChatScreen lost the {piece} composition"
    # The screen must NOT define visual pieces itself anymore.
    assert "private fun MessageBubble" not in source
    assert "OutlinedTextField" not in source
    assert "Divider(" not in source


def test_android_presence_surfaces_read_one_state_machine():
    """21j review, problem 4: orb, voice pill and composer mic all read the
    SAME PresenceStatus — not several independent mechanisms."""
    presence = PRESENCE_KT.read_text(encoding="utf-8")
    indicator = (UI / "components" / "VoiceStatusIndicator.kt").read_text(encoding="utf-8")
    assert "status.color" in indicator  # pill colors come from the state machine
    composer = COMPOSER_KT.read_text(encoding="utf-8")
    assert "voiceStatus == PresenceStatus.LISTENING" in composer  # mic reacts
    message = MESSAGE_KT.read_text(encoding="utf-8")
    assert "voiceStatus == PresenceStatus.SPEAKING" in message  # streaming orb follows TTS


# --------------------------------------------------------------------------
# Android phase 2 (round-21g): working-context + drawer-grouped navigation
# --------------------------------------------------------------------------


def test_android_working_context_in_viewmodel():
    """The card composes from the contract endpoints and clears on completion."""
    source = (REPO / "android/app/src/main/java/com/arena/voice/ui/chat/ChatViewModel.kt").read_text(encoding="utf-8")
    assert "data class WorkingContext(" in source
    assert "val workingContext: StateFlow<WorkingContext?>" in source
    # Same contract endpoints the web/desktop context panels use.
    for call in ("getBackendProjectsRaw()", "getAutonomousGoals()", "memories()"):
        assert call in source, f"working-context fetch lost {call}"
    # Lifecycle: fetched on send, cleared on stream done and on error.
    assert "fetchWorkingContext()" in source
    assert source.count("_workingContext.value = null") >= 2


def test_android_working_context_card_rendered():
    """One quiet line above the dock; the detail belongs to the sheet (21j)."""
    source = WORKING_CONTEXT_KT.read_text(encoding="utf-8")
    assert "WorkingContextAffordance(" in source
    assert '"Working on"' in source          # single-line affordance
    assert "joinTogether" not in source or "joinToString" in source
    # Detail sheet labels follow the 21j review's expanded layout.
    assert '"PROJECT"' in source
    assert '"OBJECTIVE"' in source
    assert '"RELEVANT MEMORY"' in source
    # Partial context renders: rows are individually optional.
    assert "context.project?.let" in source
    assert "context.objective?.let" in source
    chat = CHAT_KT.read_text(encoding="utf-8")
    assert "viewModel.workingContext.collectAsStateWithLifecycle()" in chat


def test_android_navigation_is_conversation_first():
    """Bottom bar carries the conversation core; workspace opens from the drawer."""
    scaffold = SCAFFOLD_KT.read_text(encoding="utf-8")
    assert "listOf(AppTab.BEANIE, AppTab.CHAT).forEach { tab ->" in scaffold
    assert "AppTab.entries.forEach" not in scaffold  # the 7-tab bar is gone
    # Drawer entries navigate.
    assert "onNavigate = { route ->" in scaffold

    drawer = DRAWER_KT.read_text(encoding="utf-8")
    # Grouped drawer (mirrors the desktop sidebar sections).
    assert '"RECENT"' in drawer
    assert '"WORKSPACE"' in drawer
    assert "currentConversationId" in drawer  # the current conversation is visibly selected
    for label in ("Pansophy", "Files", "Images", "Projects"):
        assert f'"{label}" to "' in drawer, f"drawer lost the {label} entry"


def test_android_motion_tokens_match_canonical():
    """NavHost transitions are paced by the shared motion tokens."""
    tokens = _tokens()
    source = MOTION_KT.read_text(encoding="utf-8")
    fast = re.search(r"const val FAST_MS = (\d+)", source)
    base = re.search(r"const val BASE_MS = (\d+)", source)
    assert fast and int(fast.group(1)) == tokens["motion"]["fast_ms"], "FAST_MS drifted from tokens.motion.fast_ms"
    assert base and int(base.group(1)) == tokens["motion"]["base_ms"], "BASE_MS drifted from tokens.motion.base_ms"
    # And the NavHost actually uses them.
    scaffold = SCAFFOLD_KT.read_text(encoding="utf-8")
    assert scaffold.count("MotionTokens.FAST_MS") >= 4  # enter/exit/popEnter/popExit


def test_android_tool_activity_is_semantic():
    """Review idea: tool activity as semantic cards (never raw diagnostics).

    The old rendering was plain "• label (status)" text bullets.
    """
    vm_source = (REPO / "android/app/src/main/java/com/arena/voice/ui/chat/ChatViewModel.kt").read_text(encoding="utf-8")
    assert "data class ToolActivity(" in vm_source
    assert "actionSteps: List<ToolActivity>" in vm_source
    # Updates replace by label (no string-prefix matching hack).
    assert "it.label == label" in vm_source

    tool = TOOL_KT.read_text(encoding="utf-8")
    assert "ToolActivityTimeline" in tool
    assert "Surface(" not in tool  # 21j: timeline rows, never a card nested in the bubble
    assert "Icons.Default.CheckCircle" in tool  # complete
    assert "Icons.Default.Refresh" in tool      # in_progress (spinning)
    assert "Icons.Default.Error" in tool        # error
    # The timeline renders below the bubble (web parity), not inside it.
    message = MESSAGE_KT.read_text(encoding="utf-8")
    assert "ToolActivityTimeline(msg.actionSteps)" in message
    assert message.index("ToolActivityTimeline(msg.actionSteps)") > message.index("Surface(")


def test_android_context_sheet():
    """Tapping the affordance opens the detail sheet (component-owned state)."""
    source = WORKING_CONTEXT_KT.read_text(encoding="utf-8")
    assert "ModalBottomSheet" in source
    assert "ContextSheetRow" in source
    assert '"Working context"' in source
    assert "clickable { showSheet = true }" in source  # the line IS the entry point


def test_android_voice_is_one_continuous_interaction():
    """Review idea: the streaming orb follows the LIVE voice state (speaking
    during TTS) instead of a fixed 'thinking' placeholder."""
    message = MESSAGE_KT.read_text(encoding="utf-8")
    assert "voiceStatus == PresenceStatus.SPEAKING" in message
    chat = CHAT_KT.read_text(encoding="utf-8")
    assert "BeanieMessage(msg, voiceStatus)" in chat


# --------------------------------------------------------------------------
# 21j review: component layer, integrated composer, no hard dividers
# --------------------------------------------------------------------------


def test_android_component_layer_exists():
    """The review's structure: ui/components + ui/theme, screens = composition."""
    for rel in (
        "BeanieTopBar.kt", "BeanieComposer.kt", "BeanieMessage.kt",
        "BeanieEmptyState.kt", "BeaniePresence.kt", "ToolActivity.kt",
        "WorkingContext.kt", "ConversationDrawer.kt",
    ):
        path = UI / "components" / rel
        assert path.exists(), f"missing component {rel}"
    for rel in ("Colors.kt", "Typography.kt", "Shapes.kt", "Spacing.kt", "Elevation.kt", "Motion.kt"):
        path = UI / "theme" / rel
        assert path.exists(), f"missing theme primitive {rel}"
    # The old locations are gone (theme split out of ui/).
    assert not (UI / "Theme.kt").exists()
    assert not (UI / "Typography.kt").exists()


def test_android_composer_is_one_integrated_surface():
    """21j problem 2: a ComposerDock, not four Material controls in a row."""
    source = COMPOSER_KT.read_text(encoding="utf-8")
    assert "OutlinedTextField" not in source  # no Material form chrome
    assert "BasicTextField" in source         # chrome-less input
    assert "decorationBox" in source          # placeholder is part of the surface
    assert "BorderStroke" in source           # the container owns the border…
    assert "onFocusChanged" in source         # …including the focus state
    assert "shadowElevation" in source        # …and elevation
    # The one accent control: send is alive only with text.
    assert "canSend" in source


def test_android_conversation_surfaces_have_no_hard_dividers():
    """21j problem 3: spacing / surface contrast / subtle borders — no Dividers."""
    for path in (CHAT_KT, DRAWER_KT, TOP_BAR_KT):
        source = path.read_text(encoding="utf-8")
        assert "Divider(" not in source, f"{path.name} reintroduced a hard divider"
    # Grouping in the drawer comes from section labels.
    drawer = DRAWER_KT.read_text(encoding="utf-8")
    assert "DrawerSectionLabel" in drawer


def test_android_theme_primitives_match_tokens():
    """Spacing / radius / elevation / motion derive from design/tokens.json."""
    tokens = _tokens()
    spacing = SPACING_KT.read_text(encoding="utf-8")
    for name, px in zip(("xs", "sm", "md", "lg", "xl", "xxl"), tokens["spacing"]["scale_px"]):
        assert re.search(rf"val {name} = {px}\.dp", spacing), f"Spacing.{name} != {px}px"
    for name, px in (("fieldX", 12), ("fieldY", 8), ("bubbleX", 16), ("bubbleY", 10)):
        assert re.search(rf"val {name} = {px}\.dp", spacing), f"Spacing.{name} != {px}px"

    radius = tokens["radius"]
    shapes = SHAPES_KT.read_text(encoding="utf-8")
    for name, key in (("sm", "sm_px"), ("md", "md_px"), ("lg", "lg_px"), ("xl", "xl_px"), ("xxl", "xxl_px"), ("full", "full_px")):
        assert re.search(rf"val {name} = {radius[key]}\.dp", shapes), f"ArenaRadius.{name} != {radius[key]}px"

    elevation = ELEVATION_KT.read_text(encoding="utf-8")
    assert re.search(r"val level1 = 1\.dp", elevation)
    assert re.search(r"val level4 = 12\.dp", elevation)

    motion = MOTION_KT.read_text(encoding="utf-8")
    assert re.search(rf"const val FAST_MS = {tokens['motion']['fast_ms']}", motion)
    assert re.search(rf"const val BASE_MS = {tokens['motion']['base_ms']}", motion)


def test_android_no_duplicate_imports_in_chat_layer():
    """21j code-quality catch: duplicate imports mean patched-together files."""
    for path in sorted((UI / "components").glob("*.kt")) + [CHAT_KT, SCAFFOLD_KT]:
        source = path.read_text(encoding="utf-8")
        imports = re.findall(r"^import (.+)$", source, flags=re.MULTILINE)
        dupes = {i for i in imports if imports.count(i) > 1}
        assert not dupes, f"{path.name} has duplicate imports: {dupes}"


def test_android_icons_are_in_the_classic_set():
    """Every material icon import must be one verified to exist in
    material-icons-extended's classic Material Icons set (the Compose icons
    mirror the classic set, NOT Material Symbols — 'Brain' broke the first
    real Gradle build). New icons must be verified before extending this list.
    """
    verified = {
        # core set
        "Add", "CheckCircle", "Error", "KeyboardArrowRight", "Menu", "MoreVert",
        "Person", "Refresh", "Send", "Settings",
        # classic extended set (present in 1.5.x)
        "AttachFile", "Chat", "Folder", "Image", "Mic", "MicOff", "Psychology",
    }
    icons_dir = REPO / "android/app/src/main/java/com/arena/voice"
    for path in sorted(icons_dir.glob("**/*.kt")):
        for icon in re.findall(r"import androidx\.compose\.material\.icons\.filled\.(\w+)", path.read_text(encoding="utf-8")):
            assert icon in verified, (
                f"{path.name}: icon '{icon}' is not on the verified classic-set "
                f"allowlist — confirm it exists in material-icons-extended 1.5.x "
                f"and add it to the test before using it"
            )


# --------------------------------------------------------------------------
# First real-device run (round-21n): connectivity + wake-word behaviour
# --------------------------------------------------------------------------


def test_android_allows_cleartext_to_the_lan_backend():
    """The first device run died on 'CLEARTEXT communication not permitted':
    Arena is a personal LAN assistant — plain WS to the owner's own machine is
    the deployment model, so the network security config must allow it."""
    nsc = (REPO / "android/app/src/main/res/xml/network_security_config.xml").read_text(encoding="utf-8")
    assert 'cleartextTrafficPermitted="true"' in nsc
    manifest = (REPO / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in manifest
    assert "android.permission.INTERNET" in manifest


def test_android_backend_url_is_configurable():
    """10.0.2.2 is the EMULATOR's host alias — a real phone needs the PC's LAN
    IP, so the server URL must be user-configurable (Settings screen)."""
    repo = (REPO / "android/app/src/main/java/com/arena/voice/util/SettingsRepository.kt").read_text(encoding="utf-8")
    assert 'const val DEFAULT_SERVER_URL = "ws://10.0.2.2:8000/ws"' in repo
    assert "KEY_SERVER_URL" in repo
    settings = (REPO / "android/app/src/main/java/com/arena/voice/ui/screens/SettingsScreen.kt").read_text(encoding="utf-8")
    assert '"Server URL (ws://…)"' in settings  # the field exists in the UI


def test_android_wake_word_does_not_restart_storm():
    """Error 7 (NO_MATCH) every ~6s was the NORMAL idle cadence logged at
    debug level with a flat 500ms rearm. Now: idle cycles are quiet, stacked
    errors back off exponentially, and an unhealthy recognizer is recreated."""
    source = (REPO / "android/app/src/main/java/com/arena/voice/service/WakeWordService.kt").read_text(encoding="utf-8")
    assert "ERROR_NO_MATCH" in source           # idle errors identified as such
    assert "consecutiveErrors = 0" in source    # streak resets on healthy sessions
    assert "restartDelayMs()" in source         # backoff replaces the flat delay
    assert "RESTART_DELAY_MS shl exp" in source # exponential, capped
    assert "Recognizer unhealthy — recreating" in source
    assert "createRecognizer()" in source       # creation split from starting


def test_android_ws_sends_the_api_key():
    """The device run's 'IP connection failed': with ARENA_API_KEY set (required
    to bind 0.0.0.0), the server closes keyless WS upgrades with 4003. The web
    authenticates via ?api_key=…; the Android WS client must match."""
    source = (REPO / "android/app/src/main/java/com/arena/voice/websocket/VoiceWebSocketClient.kt").read_text(encoding="utf-8")
    assert "settings.apiKey.first()" in source   # key read from settings
    assert 'currentServerUrl + sep + "api_key=" + Uri.encode(currentApiKey)' in source
    assert "currentApiKey = apiKey" in source


def test_android_wake_word_is_opt_in():
    """The device run: mic indicator + recognizer beeps from app launch because
    the wake-word foreground service started unconditionally. Now the setting
    is the single source of truth (default OFF) and drives the service."""
    repo = (REPO / "android/app/src/main/java/com/arena/voice/util/SettingsRepository.kt").read_text(encoding="utf-8")
    assert 'booleanPreferencesKey("wake_word_enabled")' in repo
    assert "prefs[KEY_WAKE_WORD] ?: false" in repo  # OPT-IN: default false

    main = MAIN_KT.read_text(encoding="utf-8")
    # Launch connects only — no unconditional mic service.
    start_services = main[main.index("private fun startServices()"):]
    start_services = start_services[: start_services.index("\n    }")]
    assert "startWakeWordService()" not in start_services
    # The setting collector drives the service + isListening.
    assert "settings.wakeWordEnabled.collect" in main
    assert "settings.setWakeWordEnabled(!isListening)" in main

    settings = (REPO / "android/app/src/main/java/com/arena/voice/ui/screens/SettingsScreen.kt").read_text(encoding="utf-8")
    assert '"Wake word listening"' in settings
    assert "onToggleWakeWord" in settings
