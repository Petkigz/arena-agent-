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
    assert res["success"] is True
    assert "Example Domain" in res["title"] or "example.com" in res["url"]

def test_web_agent_workflow_simulation():
    res = WebAgent.execute_web_workflow("Test web search and analysis", "https://example.com")
    assert res["success"] is True
    assert "agent_summary" in res
