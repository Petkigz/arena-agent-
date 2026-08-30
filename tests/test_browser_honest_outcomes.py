"""P0 bottleneck #8: the HTTP fallback must not report browser AUTOMATION
as successful. 'Open this website and click the login button' is NOT
satisfied by an HTTP GET — the outcome is now structurally honest:
request_success / browser_available / page_retrieved /
interaction_executed / environment_verified / execution_success."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.tools.browser_automation import BrowserAutomation


class FakePage:
    def __init__(self, fail_on=frozenset()):
        self.fail_on = fail_on

    def set_viewport_size(self, size): pass
    def goto(self, url, **kw): pass
    def fill(self, sel, val):
        if "fill" in self.fail_on: raise RuntimeError("not found")
    def click(self, sel):
        if "click" in self.fail_on: raise RuntimeError("not found")
    def wait_for_timeout(self, ms): pass
    def query_selector(self, sel): return None if sel in self.fail_on else object()
    def inner_text(self, sel): return "page text"
    def screenshot(self, path=None): pass
    def title(self): return "Title"
    def is_visible(self, sel): return sel not in self.fail_on
    keyboard = SimpleNamespace(press=lambda k: None)


class FakeBrowser:
    def __init__(self, page): self._page = page
    def new_page(self): return self._page
    def close(self): pass


class _FakeSync:
    def __init__(self, launch_error=None):
        self._err = launch_error
    def __enter__(self):
        if self._err: raise self._err
        return SimpleNamespace(chromium=object())
    def __exit__(self, *a): return False


class _FakeResp:
    status_code = 200
    text = "<html><head><title>T</title></head><body>hello</body></html>"


class _FakeHTTPClient:
    def __init__(self, *a, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, url): return _FakeResp()
    def close(self): pass


def _run(url="https://example.com", page=None, launch_error=None, http_ok=True, **kw):
    fake_pw = SimpleNamespace(sync_playwright=lambda: _FakeSync(launch_error))
    fake_httpx = SimpleNamespace(Client=lambda *a, **k: _FakeHTTPClient() if http_ok else (_ for _ in ()).throw(RuntimeError("net down")))
    fake_bs4 = SimpleNamespace(BeautifulSoup=lambda html, parser: _BS4(html))
    grounding = SimpleNamespace(
        observe_tab=lambda **kw2: SimpleNamespace(to_dict=lambda: {"tab": 1}))
    with patch.object(BrowserAutomation, "SCREENSHOTS_DIR", Path("/tmp/arena_test_shots")), \
         patch.object(BrowserAutomation, "GROUNDING", grounding), \
         patch.object(BrowserAutomation, "_launch", classmethod(lambda cls, ch, **k2: FakeBrowser(page or FakePage()))), \
         patch.dict(sys.modules, {"playwright.sync_api": fake_pw, "httpx": fake_httpx, "bs4": fake_bs4}):
        return BrowserAutomation.navigate_and_extract(url, **kw)


class _BS4:
    def __init__(self, html): self.text = html
    def get_text(self, separator="\n", strip=True): return "hello"
    title = SimpleNamespace(string="T")


def test_playwright_read_only_success():
    res = _run()
    assert res["success"] is True
    assert res["browser_available"] is True
    assert res["page_retrieved"] is True
    assert res["interaction_executed"] is None     # nothing requested
    assert res["environment_verified"] is True
    assert res["execution_success"] is True


def test_playwright_interaction_success():
    res = _run(steps=[{"action": "fill", "selector": "#q", "value": "x"},
                      {"action": "click", "selector": "#go"}])
    assert res["success"] is True
    assert res["interaction_executed"] is True
    assert res["execution_success"] is True


def test_playwright_partial_interaction_failure_is_honest():
    res = _run(page=FakePage(fail_on={"fill"}),
               steps=[{"action": "fill", "selector": "#gone", "value": "x"},
                      {"action": "extract", "selector": "#out"}])
    assert res["request_success"] is True
    assert res["browser_available"] is True
    assert res["page_retrieved"] is True
    assert res["interaction_executed"] is False
    assert res["execution_success"] is False
    assert res["success"] is False


def test_http_fallback_read_only_is_legitimate():
    """No interaction requested: fetching the page via HTTP IS the task."""
    res = _run(launch_error=RuntimeError("chromium missing"))
    assert res["success"] is True
    assert res["browser_available"] is False
    assert res["page_retrieved"] is True
    assert res["interaction_executed"] is False
    assert res["environment_verified"] is False
    assert res["execution_success"] is True
    assert res["fallback_mode"] == "http"


def test_http_fallback_interaction_request_is_not_success():
    """'Open this site and click the login button': an HTTP GET cannot
    click. The user's exact honesty matrix."""
    res = _run(launch_error=RuntimeError("chromium missing"),
               steps=[{"action": "click", "selector": "#login"}])
    assert res["success"] is False
    assert res["request_success"] is True
    assert res["browser_available"] is False
    assert res["page_retrieved"] is True
    assert res["interaction_executed"] is False
    assert res["environment_verified"] is False
    assert res["execution_success"] is False
    assert "could not execute" in res["error"]


def test_both_fail_all_fields_false():
    res = _run(launch_error=RuntimeError("chromium missing"), http_ok=False)
    assert res["success"] is False
    for field in ("request_success", "browser_available", "page_retrieved",
                  "interaction_executed", "environment_verified", "execution_success"):
        assert res[field] is False
