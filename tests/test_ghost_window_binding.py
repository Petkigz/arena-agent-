"""Background window messaging binds ONE window uniquely or refuses.

Audit item 16: ghost-send previously took the FIRST fuzzy title-substring
match — the silent-wrong-binding failure class. Binding now requires a unique
match (exact title preferred), lists candidates on ambiguity, and grounds the
window to its owning process where the platform allows.
"""
from app.tools.win32_ghost_operator import Win32GhostOperator

WINDOWS = [
    {"hwnd": 101, "title": "Monthly Report - Notepad"},
    {"hwnd": 102, "title": "Quarterly Report - Notepad"},
    {"hwnd": 103, "title": "Terminal"},
]


def test_exact_title_match_wins():
    binding = Win32GhostOperator.bind_window(WINDOWS, "terminal")
    assert binding["success"] is True and binding["window"]["hwnd"] == 103


def test_unique_substring_matches_and_no_match_is_honest():
    binding = Win32GhostOperator.bind_window(WINDOWS, "Quarterly")
    assert binding["success"] is True and binding["window"]["hwnd"] == 102
    none = Win32GhostOperator.bind_window(WINDOWS, "Spreadsheets")
    assert none["success"] is False and "No visible window" in none["error"]


def test_ambiguous_substring_refuses_with_candidates():
    binding = Win32GhostOperator.bind_window(WINDOWS, "Report")
    assert binding["success"] is False
    assert "Ambiguous" in binding["error"] and binding["candidates"]
    assert {c["hwnd"] for c in binding["candidates"]} == {101, 102}


def test_empty_query_is_refused():
    assert Win32GhostOperator.bind_window(WINDOWS, "   ")["success"] is False


def test_window_pid_is_honest_off_windows(monkeypatch):
    # On non-Windows (CI) the PID lookup reports None rather than inventing one.
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert Win32GhostOperator.window_pid(101) is None
