import pytest
from app.tools.desktop_control import DesktopControl
from app.tools.browser_automation import BrowserAutomation
from app.tools.web_agent import WebAgent

def test_desktop_control_approved_apps():
    apps = DesktopControl.list_approved_apps()
    assert "vscode" in apps
    assert "chrome" in apps
    assert "calculator" in apps

def test_browser_automation_fallback():
    res = BrowserAutomation.navigate_and_extract("https://example.com")
    if res["success"]:
        assert "Example Domain" in res["title"] or "example.com" in res["url"]
    else:
        assert res.get("error")
        assert "initialized successfully" not in str(res).lower()

def test_web_agent_workflow_degrades_honestly():
    res = WebAgent.execute_web_workflow("Test web search and analysis", "https://example.com")
    assert isinstance(res, dict) and "success" in res
    if res["success"]:
        assert "agent_summary" in res
    else:
        assert res.get("error") or res.get("agent_summary")
