"""DesktopControl.open_url launch honesty.

External sandbox audit (2026-09): the offline /chat fallback routed a
local-file goal to web_search, and the reply claimed "Opened default
browser and searched for ..." on a machine with NO browser at all. Root
cause: open_url called webbrowser.open(url) and DISCARDED its boolean
return — webbrowser.open returns False when no usable browser exists
(headless sandbox, stripped server) without raising, so the tool
self-reported {"success": True, "Successfully opened URL in browser"} on
every machine, no matter what actually happened. Fabricated success
flowed into executed_actions and the assistant reply.

webbrowser.open()'s return value IS the launch measurement. This test
pins the honest contract in both worlds.
"""

from unittest.mock import patch

from app.tools.desktop_control import DesktopControl


def test_open_url_reports_failure_when_no_browser_exists():
    """webbrowser.open returning False (no browser on the system) must be
    reported as FAILURE with a typed error — not fabricated success."""
    with patch("webbrowser.open", return_value=False) as mock_open:
        res = DesktopControl.open_url("https://example.com")
    mock_open.assert_called_once_with("https://example.com")
    assert res["success"] is False
    assert "error" in res and res["error"]
    assert "browser" in res["error"].lower()


def test_open_url_reports_success_when_browser_launches():
    """The success path is still the success path — the fix must not
    break real launches."""
    with patch("webbrowser.open", return_value=True):
        res = DesktopControl.open_url("https://example.com")
    assert res["success"] is True
    assert res["url"] == "https://example.com"


def test_open_url_typed_error_when_launch_raises():
    """An exception during launch is a typed failure, never a raise into
    the caller (the execution path depends on that)."""
    with patch("webbrowser.open", side_effect=OSError("display not found")):
        res = DesktopControl.open_url("https://example.com")
    assert res["success"] is False
    assert "display not found" in res["error"]


def test_web_search_handler_does_not_claim_a_browser_it_never_opened():
    """The consumer side (master_agent's web_search handler): when the
    browser never opens, the executed-action log must record the FAILURE,
    never 'Opened default browser and searched for ...'."""
    with patch("webbrowser.open", return_value=False):
        from types import SimpleNamespace
        from app.agents.master_agent import MasterAgentOrchestrator
        proposal = SimpleNamespace(
            action_type="web_search",
            payload={"query": "goal_verifier files", "action_type": "web_search"},
        )
        result = MasterAgentOrchestrator.execute_proposal(
            proposal,
            user_text="search for goal_verifier files",
        )
    executed = " ".join(str(a) for a in result.get("executed_actions", []))
    assert "Opened default browser" not in executed, \
        "a browser that never opened must not be claimed as opened"
    assert "Failed to open web browser" in executed
    assert result.get("success") is False
