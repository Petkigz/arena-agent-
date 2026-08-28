"""General OS control: one planner for every action, every platform.

Plus the Firefox-search payload fix: 'can you open firefox and search
ordinary' must extract JUST 'ordinary' as the query, not the whole sentence.
"""
from unittest.mock import patch

from app.cognition.tool_matcher import match_control_tool
from app.cognition.os_control_planner import _is_os_control_request, OSActionPlan


# ── Firefox search payload fix ─────────────────────────────────────────────

def test_search_extracts_query_not_whole_sentence():
    match = match_control_tool("can you open firefox and search ordinary")
    assert match is not None
    assert match.action_type == "web_search"
    assert match.payload.get("query") == "ordinary"
    assert match.payload.get("query") != "can you open firefox and search ordinary"


def test_search_variants_extract_clean_queries():
    for text, expected in [
        ("search the web for python tutorials", "python tutorials"),
        ("google best restaurants in kampala", None),  # 'google' may match differently
        ("can you search for the weather today", "the weather today"),
        ("find files named report.pdf", None),  # find files routes differently
    ]:
        match = match_control_tool(text)
        if match and match.action_type == "web_search":
            query = match.payload.get("query", "")
            if expected:
                assert expected in query.lower(), f"{text} -> {query!r} should contain {expected!r}"
            assert "can you" not in query.lower(), f"query should not contain the instruction: {query!r}"
            assert "open firefox" not in query.lower(), f"query should not contain the browser instruction: {query!r}"


# ── General OS control routing ─────────────────────────────────────────────

def test_os_control_requests_are_detected():
    assert _is_os_control_request("change my desktop wallpaper")
    assert _is_os_control_request("set my volume to 50")
    assert _is_os_control_request("turn on dark mode")
    assert _is_os_control_request("change my desktop icon size to medium")
    assert _is_os_control_request("adjust brightness to 80%")
    assert _is_os_control_request("enable night light")
    assert _is_os_control_request("change screen resolution to 1920x1080")
    assert _is_os_control_request("set the screensaver timeout to 5 minutes")


def test_non_os_requests_are_not_detected():
    assert not _is_os_control_request("what is the capital of France")
    assert not _is_os_control_request("do you have wisdom")
    assert not _is_os_control_request("can you talk")
    assert not _is_os_control_request("read my email")
    assert not _is_os_control_request("write a poem about dogs")


def test_unmatched_os_requests_route_to_planner_not_chat():
    """'change desktop icon size' has NO specific tool — must route to the
    general OS planner, not fall through to a chat reply."""
    match = match_control_tool("can you change my desktop icon size to medium")
    assert match is not None
    assert match.action_type == "os_control_plan"
    assert "os_settings" in match.matched_terms


def test_specific_tools_beat_the_general_planner():
    """When a specific tool matches confidently (wallpaper), it wins over
    the general OS planner."""
    match = match_control_tool("can you change my desktop wallpaper to C:/pics/w.jpg")
    assert match is not None
    assert match.action_type == "set_wallpaper"  # specific tool, not os_control_plan


# ── Planner output safety ──────────────────────────────────────────────────

def test_dangerous_commands_are_refused():
    """The planner must refuse obviously destructive shell commands."""
    from app.cognition.os_control_planner import DANGEROUS_PATTERNS
    assert DANGEROUS_PATTERNS.search("format c:")
    assert DANGEROUS_PATTERNS.search("rm -rf /")
    assert DANGEROUS_PATTERNS.search("shutdown /s /t 0")
    assert not DANGEROUS_PATTERNS.search("Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name WallPaper -Value 'C:/img.jpg'")
    assert not DANGEROUS_PATTERNS.search("gsettings set org.gnome.desktop.background picture-uri 'file:///img.jpg'")


def test_os_plan_is_structured_not_freeform_shell():
    plan = OSActionPlan(
        plan_id="test_1", user_request="set dark mode",
        command="Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name AppsUseLightTheme -Value 0",
        shell="powershell", description="Set dark mode",
        verify_command="(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize').AppsUseLightTheme",
        risk_level="reversible", platform="Windows")
    d = plan.to_dict()
    assert d["shell"] == "powershell"
    assert d["risk_level"] == "reversible"
    assert d["verify_command"]  # always has a verification plan
