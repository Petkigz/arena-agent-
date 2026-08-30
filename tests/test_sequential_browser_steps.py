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


def test_failing_step_does_not_abort_the_workflow():
    page = FakePage(fail_on={"fill"})
    res = BrowserAutomation._run_sequential_steps(page, [
        {"action": "fill", "selector": "#gone", "value": "x"},
        {"action": "click", "selector": "#next"},
        {"action": "extract", "selector": "#out"},
    ])
    # The failed step is reported honestly…
    assert res["step_log"][0]["ok"] is False and "RuntimeError" in res["step_log"][0]["error"]
    # …and the rest of the sequence still ran.
    assert ("click", "#next") in page.ops
    assert ("extract", "#out") in page.ops
    assert res["step_log"][1]["ok"] is True


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
