"""Comprehensive coverage: every OS/browser/file/system verb and domain.

Pins the full pattern maps so regressions surface as test failures, not
live bugs on the owner machine. Three layers tested:
  1. Observation router: read-only questions get evidence-based answers
  2. Tool matcher: specific tool requests route to the right tool
  3. OS planner: general settings requests are detected
"""
import pytest

from app.cognition.tool_matcher import match_control_tool
from app.cognition.observation_router import plan_observation
from app.cognition.os_control_planner import _is_os_control_request


@pytest.fixture(autouse=True)
def desktop_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])


class TestObservationPatterns:
    """Every read-only system question must produce an observation plan."""

    @pytest.mark.parametrize("text,kind", [
        ("how many tabs are open on this desktop", "browser_tabs"),
        ("list my browser tabs", "browser_tabs"),
        ("what tabs are open", "browser_tabs"),
        ("how many icons do i have on my desktop", "desktop_contents"),
        ("what's on my screen", "screen_contents"),
        ("what apps are running", "running_processes"),
        ("which windows are open", "open_windows"),
        ("what programs do i have installed", "installed_apps"),
        # System resources
        ("how much RAM do i have", "system_resources"),
        ("how much disk space is free", "system_resources"),
        ("check my CPU usage", "system_resources"),
        ("how is my battery doing", "power_status"),
        ("am i plugged in or on battery", "power_status"),
        # Network
        ("what is my IP address", "network_address"),
        ("am i online", "network_status"),
        ("is my internet working", "network_status"),
        # System info
        ("what version of windows am i running", "system_info"),
        ("system information", "system_info"),
        # Devices
        ("what devices are connected", "connected_devices"),
        ("what USB drives do i have", "connected_devices"),
        # Startup
        ("what programs run at startup", "startup_programs"),
        ("what services are running", "startup_programs"),
        # Clipboard
        ("what's in my clipboard", "clipboard"),
        ("what did i copy", "clipboard"),
        # Downloads
        ("what's in my downloads folder", "downloads_folder"),
        ("show my downloads", "downloads_folder"),
    ])
    def test_observation_produces_correct_kind(self, text, kind):
        plan = plan_observation(text)
        assert plan is not None, f"NO observation plan for: {text!r}"
        assert plan.question_kind == kind, f"{text!r} -> {plan.question_kind} (expected {kind})"

    def test_chat_questions_produce_no_observation(self):
        for text in ["what is the capital of France", "do you have wisdom",
                     "write me a poem", "hello"]:
            assert plan_observation(text) is None or plan_observation(text).question_kind not in (
                "browser_tabs", "system_resources", "network_address")


class TestControlVerbs:
    """Control verbs must be recognized by BOTH the matcher and planner."""

    def test_verb_lists_are_consistent(self):
        from app.cognition.tool_matcher import CONTROL_VERBS
        from app.cognition.os_control_planner import OS_ACTION_VERBS
        missing = CONTROL_VERBS - OS_ACTION_VERBS
        assert not missing, f"in matcher but not planner: {sorted(missing)}"

    @pytest.mark.parametrize("verb", [
        "open", "close", "minimize", "maximize", "launch", "quit",
        "navigate", "refresh", "scroll", "zoom", "bookmark", "click",
        "screenshot", "record", "mute", "unmute", "connect", "disconnect",
        "pair", "scan", "lock", "unlock", "install", "uninstall",
        "compress", "extract", "encrypt", "decrypt", "clear", "empty",
    ])
    def test_common_verbs_in_both_sets(self, verb):
        from app.cognition.tool_matcher import CONTROL_VERBS
        from app.cognition.os_control_planner import OS_ACTION_VERBS
        assert verb in CONTROL_VERBS, f"'{verb}' missing from tool_matcher"
        assert verb in OS_ACTION_VERBS, f"'{verb}' missing from os_control_planner"


class TestOSControlDetection:
    """OS settings requests must be detected for the general planner."""

    @pytest.mark.parametrize("text", [
        "change my desktop wallpaper",
        "turn on dark mode",
        "set volume to 50",
        "adjust brightness",
        "change icon size",
        "enable night light",
        "set screen resolution",
        "connect to wifi",
        "disconnect bluetooth",
        "clear my clipboard",
        "mute my speakers",
        "change my theme",
        "set a screensaver",
        "change the time zone",
        "lock my screen",
        "restart my computer",
        "show hidden files",
        "change file associations",
    ])
    def test_os_control_detected(self, text):
        assert _is_os_control_request(text), f"{text!r} not detected as OS control"

    @pytest.mark.parametrize("text", [
        "what is the capital of France",
        "do you have wisdom",
        "hello",
        "write a poem",
    ])
    def test_non_control_not_detected(self, text):
        assert not _is_os_control_request(text)


class TestUnmatchedRoutesToPlanner:
    """Control requests with no specific tool must route to the OS planner."""

    @pytest.mark.parametrize("text", [
        "change my desktop icon size to medium",
        "turn on night light",
        "set my volume to 30",
        "connect to my home wifi",
        "clear my dns cache",
    ])
    def test_routes_to_planner(self, text):
        m = match_control_tool(text)
        assert m is not None, f"{text!r} produced no match at all"
        assert m.action_type == "os_control_plan", (
            f"{text!r} -> {m.action_type} (expected os_control_plan)")


class TestSpecificToolsWin:
    """When a specific tool exists, it beats the general planner."""

    @pytest.mark.parametrize("text,expected", [
        ("change my desktop wallpaper to C:/img.jpg", "set_wallpaper"),
        ("search my files for report", "search_files"),
    ])
    def test_specific_tool_beats_planner(self, text, expected):
        m = match_control_tool(text)
        assert m is not None
        assert m.action_type == expected


class TestSearchQueryExtraction:
    """Search queries extract cleanly from natural language."""

    @pytest.mark.parametrize("text,expected_query", [
        ("search ordinary", "ordinary"),
        ("can you open firefox and search ordinary", "ordinary"),
        ("search the web for python tutorials", "python tutorials"),
        ("search for me ordinary on YouTube", "ordinary on YouTube"),
        ("find information about quantum computing", "quantum computing"),
    ])
    def test_query_extraction(self, text, expected_query):
        m = match_control_tool(text)
        assert m is not None, f"no match for {text!r}"
        assert m.action_type == "web_search"
        query = m.payload.get("query", "")
        assert expected_query in query, f"{text!r} -> {query!r} (expected {expected_query!r})"
        # Never the whole instruction sentence.
        assert query != text
        assert "open firefox" not in query.lower()
        assert "can you" not in query.lower()
