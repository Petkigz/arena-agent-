"""P0 bottleneck #6: browser workflows execute as a true SEQUENCE.
click -> wait -> DOM update -> fill -> click -> extract must reach the
page in exactly that order — never bucketed into all-fills-then-all-clicks."""
from unittest.mock import patch

from app.tools.browser_automation import BrowserAutomation


class FakeKeyboard:
    def __init__(self, ops):
        self._ops = ops

    def press(self, key):
        self._ops.append(("press", key))


class FakePage:
    def __init__(self, fail_on=None):
        self.ops = []
        self.fail_on = fail_on or set()
        self.keyboard = FakeKeyboard(self.ops)

    def goto(self, url, **kw):
        self.ops.append(("navigate", url))

    def fill(self, selector, value):
        if "fill" in self.fail_on:
            raise RuntimeError(f"element {selector} not found")
        self.ops.append(("fill", selector, value))

    def click(self, selector):
        if "click" in self.fail_on:
            raise RuntimeError(f"element {selector} not found")
        self.ops.append(("click", selector))

    def wait_for_timeout(self, ms):
        self.ops.append(("wait", ms))

    def query_selector(self, selector):
        return object() if selector not in self.fail_on else None

    def inner_text(self, selector):
        self.ops.append(("extract", selector))
        return f"text@{selector}"


def test_steps_execute_in_declared_order():
    """The exact interleaving that bucketing destroyed:
    navigate / click A / wait / fill B / click C / extract."""
    page = FakePage()
    BrowserAutomation._run_sequential_steps(page, [
        {"action": "navigate", "url": "https://example.com/login"},
        {"action": "click", "selector": "#open-login"},
        {"action": "wait", "ms": 2000},
        {"action": "fill", "selector": "#email", "value": "a@b.c"},
        {"action": "click", "selector": "#next"},
        {"action": "extract", "selector": "#dashboard"},
    ])
    ops = page.ops
    assert ops[0] == ("navigate", "https://example.com/login")
    assert ops[1] == ("click", "#open-login")
    assert ("wait", 500) in ops          # implicit post-click settle
    assert ("wait", 2000) in ops         # the explicit wait
    # The fill must happen AFTER the click+#wait, not before all clicks.
    assert ops.index(("click", "#open-login")) < ops.index(("wait", 2000)) \
        < ops.index(("fill", "#email", "a@b.c")) < ops.index(("click", "#next")) \
        < ops.index(("extract", "#dashboard"))


def test_extracts_accumulate_per_selector():
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "extract", "selector": "#price"},
        {"action": "click", "selector": "#next"},
        {"action": "extract", "selector": "#price2"},
    ])
    assert res["extracts"]["#price"] == "text@#price"
    assert res["extracts"]["#price2"] == "text@#price2"


def test_wait_is_capped():
    page = FakePage()
    BrowserAutomation._run_sequential_steps(page, [{"action": "wait", "ms": 999999}])
    assert page.ops == [("wait", BrowserAutomation._WAIT_CAP_MS)]


def test_failed_required_step_aborts_by_default():
    """THE review #6 case: login fails -> 'click dashboard' and 'delete
    record' must NEVER run. Default fail_policy is abort."""
    page = FakePage(fail_on={"fill"})
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#login-email", "value": "a@b.c"},
        {"action": "click", "selector": "#dashboard"},
        {"action": "click", "selector": "#delete-record"},
    ])
    assert res["aborted"] is True
    assert res["aborted_at"] == 0
    assert res["steps_executed"] == 1  # only the failed step ran
    # The later steps were NOT attempted — ops proves it.
    assert ("click", "#dashboard") not in page.ops
    assert ("click", "#delete-record") not in page.ops
    assert res["step_log"][0]["ok"] is False
    assert res["step_log"][0]["aborted_workflow"] is True


def test_continue_policy_is_explicit_opt_in():
    """The old continue-on-failure semantics survive as an explicit
    fail_policy='continue' for best-effort scraping."""
    page = FakePage(fail_on={"fill"})
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#gone", "value": "x"},
        {"action": "click", "selector": "#next"},
        {"action": "extract", "selector": "#out"},
    ], fail_policy="continue")
    assert res["aborted"] is False
    assert res["fail_policy"] == "continue"
    # The failed step is reported honestly…
    assert res["step_log"][0]["ok"] is False and "RuntimeError" in res["step_log"][0]["error"]
    # …and the rest of the sequence still ran.
    assert ("click", "#next") in page.ops
    assert ("extract", "#out") in page.ops
    assert res["step_log"][1]["ok"] is True


def test_optional_step_failure_never_aborts():
    page = FakePage(fail_on={"fill"})
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#cookie-banner", "value": "x", "optional": True},
        {"action": "click", "selector": "#next"},
        {"action": "extract", "selector": "#out"},
    ])  # default policy: abort
    assert res["aborted"] is False
    assert res["step_log"][0]["skipped_as_optional"] is True
    assert ("click", "#next") in page.ops
    assert ("extract", "#out") in page.ops


def test_recover_policy_retries_once_then_continues():
    class FlakyPage(FakePage):
        """Fails the FIRST fill, succeeds on retry."""
        def __init__(self):
            super().__init__()
            self.failed_once = False

        def fill(self, selector, value):
            if not self.failed_once:
                self.failed_once = True
                raise RuntimeError("transient element detach")
            self.ops.append(("fill", selector, value))

    page = FlakyPage()
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#email", "value": "a@b.c"},
        {"action": "click", "selector": "#next"},
    ], fail_policy="recover")
    assert res["aborted"] is False
    assert res["step_log"][0]["recovered"] is True
    assert res["step_log"][0]["attempt"] == 2
    assert res["step_log"][0]["ok"] is True
    assert ("click", "#next") in page.ops


def test_recover_policy_aborts_when_retry_also_fails():
    page = FakePage(fail_on={"fill"})
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#email", "value": "a@b.c"},
        {"action": "click", "selector": "#next"},
    ], fail_policy="recover")
    assert res["aborted"] is True
    assert res["aborted_at"] == 0
    assert res["step_log"][0]["recovered"] is False
    assert ("click", "#next") not in page.ops


def test_unknown_policy_falls_back_to_abort():
    page = FakePage(fail_on={"fill"})
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#gone", "value": "x"},
        {"action": "click", "selector": "#next"},
    ], fail_policy="yolo")
    assert res["fail_policy"] == "abort"
    assert res["aborted"] is True
    assert ("click", "#next") not in page.ops


def test_unsupported_action_is_a_failure_under_abort():
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "teleport", "selector": "#q"},
        {"action": "click", "selector": "#next"},
    ])
    assert res["aborted"] is True
    assert "unsupported action" in res["step_log"][0]["error"]
    assert ("click", "#next") not in page.ops


def test_submit_step_hits_the_level3_policy_gate():
    """A submit step is policy-checked BEFORE any browser launches."""
    with patch("app.tools.browser_automation.PolicyEvaluator.evaluate_action",
               return_value=(False, "submit requires owner approval", 3)):
        res = BrowserAutomation.navigate_and_extract(
            "https://example.com",
            steps=[{"action": "fill", "selector": "#q", "value": "x"},
                   {"action": "submit", "selector": "form"}],
        )
    assert res["success"] is False
    assert "Policy Blocked" in res["error"]
    assert res["authority_level"] == 3


def test_bucket_params_still_work_legacy_path():
    """fill_inputs/click_selectors remain supported (API backward compat);
    the fake-page check runs the real sequential path via steps."""
    page = FakePage()
    BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#a", "value": "1"},
        {"action": "fill", "selector": "#b", "value": "2"},
    ])
    assert page.ops == [("fill", "#a", "1"), ("fill", "#b", "2")]


def test_wait_ms_becomes_a_real_page_wait():
    """P0 bottleneck #7 (regression pin): 'wait 5000' must mean a
    five-second page wait. The old WebAgent parsed wait_ms into a local
    variable that never reached the browser layer — waits were silently
    dropped (only the fixed 1s post-click sleep existed)."""
    page = FakePage()
    BrowserAutomation._run_sequential_steps(page, [
        {"action": "click", "selector": "#load-more"},
        {"action": "wait", "ms": 5000},
        {"action": "extract", "selector": "#results"},
    ])
    # Exactly five seconds, executed between the click and the extract.
    assert ("wait", 5000) in page.ops
    i_click = page.ops.index(("click", "#load-more"))
    i_wait = page.ops.index(("wait", 5000))
    i_extract = page.ops.index(("extract", "#results"))
    assert i_click < i_wait < i_extract


def test_web_agent_passes_wait_ms_through():
    """WebAgent must forward the parsed ms to the browser layer inside the
    ordered steps (the old code computed wait_ms and dropped it)."""
    from unittest.mock import patch
    from app.tools.web_agent import WebAgent

    captured = {}

    def capture(url, **kw):
        captured.update(kw)
        return {"success": True, "url": url, "title": "t", "content_snippet": "x",
                "screenshot_path": "", "image_url": "", "text_length": 1,
                "step_log": [], "extracts": {}}

    with patch("app.tools.web_agent.BrowserAutomation.navigate_and_extract", side_effect=capture), \
         patch("app.tools.web_agent.llm_client.generate_chat_completion",
               return_value={"choices": [{"message": {"content": "ok"}}], "model": "m"}):
        WebAgent.execute_web_workflow(
            objective="timing", target_url="https://example.com",
            steps=[{"action": "wait", "ms": 5000}],
            auto_save_memory=False)

    assert captured["steps"] == [{"action": "wait", "ms": 5000}]


# ---------------------------------------------------------------------------
# P0 review #7: the 40-step ceiling is a runaway guard, NOT a silent crop.
# ---------------------------------------------------------------------------

def _many_steps(n, action="wait"):
    return [{"action": action, "ms": 1} for _ in range(n)]


def test_truncation_at_default_limit_is_reported_not_silent():
    """45 steps requested, default limit: 40 run, and the result SAYS so."""
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(page, _many_steps(45))
    assert res["workflow_truncated"] is True
    assert res["truncation_intentional"] is False
    assert res["steps_requested"] == 45
    assert res["steps_planned"] == 40
    assert res["steps_executed"] == 40
    assert len(res["step_log"]) == 40
    assert res["aborted"] is False  # every step that ran, succeeded


def test_explicit_step_limit_makes_truncation_intentional():
    """A caller-chosen ceiling is deliberate best-effort execution."""
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(page, _many_steps(10), step_limit=3)
    assert res["workflow_truncated"] is True
    assert res["truncation_intentional"] is True
    assert res["steps_requested"] == 10
    assert res["steps_executed"] == 3


def test_step_limit_can_raise_the_default_ceiling_up_to_the_hard_cap():
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(page, _many_steps(50), step_limit=60)
    assert res["workflow_truncated"] is False
    assert res["steps_executed"] == 50


def test_step_limit_never_exceeds_the_hard_cap():
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(
        page, _many_steps(300), step_limit=100000)
    assert res["step_limit"] == BrowserAutomation._SEQ_STEP_HARD_LIMIT
    assert res["steps_executed"] == BrowserAutomation._SEQ_STEP_HARD_LIMIT
    assert res["workflow_truncated"] is True
    assert res["steps_requested"] == 300


def test_short_workflow_reports_no_truncation():
    page = FakePage()
    res = BrowserAutomation._run_sequential_steps(page, _many_steps(5))
    assert res["workflow_truncated"] is False
    assert res["steps_requested"] == res["steps_executed"] == 5


def test_truncated_workflow_with_step_failure_reports_both():
    """Truncation and abort are independent, orthogonal facts."""
    page = FakePage(fail_on={"fill"})
    steps = [{"action": "fill", "selector": "#gone", "value": "x"}] + _many_steps(44, action="click")
    res = BrowserAutomation._run_sequential_steps(page, steps)  # default abort
    assert res["aborted"] is True
    assert res["aborted_at"] == 0
    assert res["steps_executed"] == 1
    assert res["workflow_truncated"] is True
    assert res["steps_requested"] == 45


def test_navigate_and_extract_fails_on_unintentional_truncation():
    """End-to-end: a 60-step workflow that stops at the default 40 must
    come back success=False — the agent must not believe it ran 60."""
    import sys
    import types
    from unittest.mock import MagicMock

    class RichPage(FakePage):
        def set_viewport_size(self, size):
            pass

        def goto(self, url, **kw):
            self.ops.append(("navigate", url))

        def screenshot(self, path=None, **kw):
            pass

        def title(self):
            return "t"

    class FakeBrowser:
        def new_page(self):
            return page

        def close(self):
            pass

    page = RichPage()
    fake_sync = types.SimpleNamespace()
    fake_module = types.ModuleType("playwright")
    fake_api = types.ModuleType("playwright.sync_api")
    fake_api.sync_playwright = lambda: MagicMock(
        __enter__=lambda s: types.SimpleNamespace(chromium=object()),
        __exit__=lambda *a: False)
    fake_module.sync_api = fake_api
    sys.modules.setdefault("playwright", fake_module)
    sys.modules.setdefault("playwright.sync_api", fake_api)

    with patch.object(BrowserAutomation, "_launch", return_value=FakeBrowser()), \
         patch.object(BrowserAutomation.GROUNDING, "observe_tab",
                      return_value=MagicMock(to_dict=lambda: {})):
        res = BrowserAutomation.navigate_and_extract(
            "https://example.com", steps=_many_steps(60, action="click"))
    assert res["workflow_truncated"] is True
    assert res["steps_requested"] == 60
    assert res["steps_executed"] == 40
    assert res["success"] is False  # unintentional truncation fails honestly

    # The same workflow with an EXPLICIT limit is intentional best-effort.
    with patch.object(BrowserAutomation, "_launch", return_value=FakeBrowser()), \
         patch.object(BrowserAutomation.GROUNDING, "observe_tab",
                      return_value=MagicMock(to_dict=lambda: {})):
        res2 = BrowserAutomation.navigate_and_extract(
            "https://example.com", steps=_many_steps(60, action="click"),
            step_limit=60)
    assert res2["workflow_truncated"] is False
    assert res2["steps_executed"] == 60
    assert res2["success"] is True
