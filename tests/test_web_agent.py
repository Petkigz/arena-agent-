"""
WebAgent multi-step workflow tests (no real browser — mocks the automation layer).

Verifies: step validation, step→param mapping, LLM synthesis, graceful failure,
and that submit_form is passed through (so the Level-3 policy gate still fires).
"""

from unittest.mock import patch

from app.tools.web_agent import WebAgent


def _fake_browser(success=True, **kw):
    if not success:
        return {"success": False, "error": "network down"}
    return {
        "success": True,
        "url": "https://example.com",
        "title": "Example",
        "content_snippet": "hello world",
        "screenshot_path": "",
        "image_url": "",
        "text_length": 11,
    }


def _fake_llm(text="summary"):
    return {"choices": [{"message": {"content": text}}], "model": "fast"}


def test_web_agent_rejects_invalid_step():
    res = WebAgent.execute_web_workflow(
        objective="x", target_url="https://example.com",
        steps=[{"action": "hack", "selector": "#q"}],
    )
    assert res["success"] is False
    assert "invalid action" in res["error"]


def test_web_agent_maps_steps_to_browser_params():
    captured = {}

    def capture(url, fill_inputs=None, click_selectors=None, submit_form=False):
        captured["url"] = url
        captured["fill"] = fill_inputs
        captured["click"] = click_selectors
        captured["submit"] = submit_form
        return _fake_browser()

    with patch.object(WebAgent, "__module__", "app.tools.web_agent"), \
         patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", side_effect=capture), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", side_effect=_fake_llm):

        WebAgent.execute_web_workflow(
            objective="search", target_url="https://example.com",
            steps=[
                {"action": "fill", "selector": "#q", "value": "query"},
                {"action": "click", "selector": "button"},
                {"action": "submit"},
            ],
            auto_save_memory=False,
        )

    assert captured["url"] == "https://example.com"
    assert captured["fill"] == {"#q": "query"}
    assert captured["click"] == ["button"]
    assert captured["submit"] is True


def test_web_agent_navigate_step_overrides_url():
    captured = {}

    def capture(url, **kw):
        captured["url"] = url
        return _fake_browser()

    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", side_effect=capture), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", side_effect=_fake_llm):

        WebAgent.execute_web_workflow(
            objective="x", target_url="https://ignored.com",
            steps=[{"action": "navigate", "url": "example.org"}],
            auto_save_memory=False,
        )

    assert captured["url"] == "https://example.org"


def test_web_agent_returns_browser_failure():
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser(success=False)):
        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com")
    assert res["success"] is False
    assert res["error"] == "network down"


def test_web_agent_synthesizes_summary():
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser()), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", return_value=_fake_llm("found it")):

        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com", auto_save_memory=False)

    assert res["success"] is True
    assert res["agent_summary"] == "found it"
    assert res["steps_executed"] == 0


def test_web_agent_llm_failure_is_graceful():
    def llm_raises(**kw):
        raise RuntimeError("llm down")

    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser()), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", side_effect=llm_raises):

        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com", auto_save_memory=False)

    assert res["success"] is True  # the browser work succeeded
    assert "summarization failed" in res["agent_summary"]
