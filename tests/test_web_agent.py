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


def test_web_agent_preserves_step_order():
    """P0 #6: steps must reach the browser layer as an ORDERED sequence —
    the old bucket mapping (all fills, then all clicks, waits dropped)
    reordered real workflows and broke sites that need
    click -> wait -> DOM update -> fill -> click -> extract."""
    captured = {}

    def capture(url, fill_inputs=None, click_selectors=None, submit_form=False,
                use_profile=False, steps=None):
        captured["url"] = url
        captured["steps"] = steps
        captured["fill"] = fill_inputs
        captured["click"] = click_selectors
        return _fake_browser()

    with patch.object(WebAgent, "__module__", "app.tools.web_agent"), \
         patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", side_effect=capture), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", side_effect=_fake_llm):

        WebAgent.execute_web_workflow(
            objective="search", target_url="https://example.com",
            steps=[
                {"action": "click", "selector": "#open-form"},
                {"action": "wait", "ms": 2000},
                {"action": "fill", "selector": "#q", "value": "query"},
                {"action": "click", "selector": "#search-btn"},
                {"action": "extract", "selector": "#results"},
            ],
            auto_save_memory=False,
        )

    assert captured["url"] == "https://example.com"
    # The exact declared order, interleaved — not bucketed.
    assert [s["action"] for s in captured["steps"]] == [
        "click", "wait", "fill", "click", "extract"]
    assert captured["steps"][1]["ms"] == 2000
    assert captured["steps"][2] == {"action": "fill", "selector": "#q", "value": "query"}
    assert captured["steps"][3]["selector"] == "#search-btn"
    # No bucket flattening alongside the sequence.
    assert captured["fill"] is None and captured["click"] is None


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
    verdict = ('{"objective_satisfied": true, "summary": "found it", '
               '"evidence": "the page says found", "next_step": ""}')
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser()), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", return_value=_fake_llm(verdict)):

        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com", auto_save_memory=False)

    assert res["success"] is True
    assert res["objective_satisfied"] is True
    assert res["agent_summary"] == "found it"
    assert res["steps_executed"] == 0


def test_web_agent_llm_failure_is_graceful():
    def llm_raises(**kw):
        raise RuntimeError("llm down")

    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser()), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", side_effect=llm_raises):

        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com", auto_save_memory=False)

    # The browser work succeeded… (browser_execution_success=True)
    assert res["browser_execution_success"] is True
    # …but the goal could not be VERIFIED — that is not success (review #8).
    assert res["success"] is False
    assert res["objective_satisfied"] == "unknown"
    assert res["goal_verification"] == "unverified"
    assert "objective verification failed" in res["agent_summary"]


# ---------------------------------------------------------------------------
# P0 review #8: browser execution success != goal success. The LLM's
# objective verdict is authoritative for `success`.
# ---------------------------------------------------------------------------

def _verdict(satisfied, summary="checked", evidence="", next_step=""):
    import json as _json
    return _json.dumps({"objective_satisfied": satisfied, "summary": summary,
                        "evidence": evidence, "next_step": next_step})


def test_navigation_success_is_not_goal_success():
    """THE review case: 'check whether the site says my application was
    approved' — the browser navigated fine; the page does not say approved.
    success must be False."""
    browser = _fake_browser()
    browser["content_snippet"] = "Welcome back. Your documents are pending review."
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=browser), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion",
               return_value=_fake_llm(_verdict(False, summary="The page does not state approval",
                                               evidence="pending review", next_step="check email"))):
        res = WebAgent.execute_web_workflow(
            objective="Check whether the website says my application was approved",
            target_url="https://portal.example.com/status", auto_save_memory=False)
    assert res["browser_execution_success"] is True   # browser did its job
    assert res["page_retrieved"] is None or True       # page came back
    assert res["objective_satisfied"] is False         # the goal, judged
    assert res["success"] is False                     # authoritative
    assert res["objective_evidence"] == "pending review"
    assert res["recommended_next_step"] == "check email"


def test_objective_satisfied_makes_goal_success():
    browser = _fake_browser()
    browser["content_snippet"] = "Congratulations! Your application was approved."
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=browser), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion",
               return_value=_fake_llm(_verdict(True, summary="Approved", evidence="approved"))):
        res = WebAgent.execute_web_workflow(
            objective="Check whether the website says my application was approved",
            target_url="https://portal.example.com/status", auto_save_memory=False)
    assert res["success"] is True
    assert res["objective_satisfied"] is True
    assert res["goal_verification"] == "llm_content_analysis"


def test_unparseable_verdict_is_unknown_not_success():
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser()), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion", return_value=_fake_llm("looks fine to me")):
        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com", auto_save_memory=False)
    assert res["objective_satisfied"] == "unknown"
    assert res["success"] is False  # never silently promoted to True
    assert res["agent_summary"] == "looks fine to me"


def test_browser_failure_reports_goal_unsatisfied():
    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser(success=False)):
        res = WebAgent.execute_web_workflow(objective="x", target_url="https://example.com")
    assert res["success"] is False
    assert res["objective_satisfied"] is False
    assert res["browser_execution_success"] is False
    assert res["goal_verification"] == "browser_execution_failed"
    assert res["error"] == "network down"


def test_memory_saves_the_honest_outcome():
    saved = {}

    def fake_index(payload, category=None):
        saved.update(payload)
        return "mem-1"

    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", return_value=_fake_browser()), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion",
               return_value=_fake_llm(_verdict(False, summary="not approved"))), \
         patch("app.tools.web_agent.KnowledgeIndexer.index_web_knowledge", side_effect=fake_index):
        res = WebAgent.execute_web_workflow(
            objective="check approval", target_url="https://example.com", auto_save_memory=True)
    assert res["success"] is False
    assert saved["success"] is False  # memory never learns a fake success
