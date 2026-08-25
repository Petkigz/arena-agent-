"""Persistent browser profile: owner logins survive across headless runs.

open_session opens a visible persistent-profile browser (owner logs in once,
close_session persists it); later flows with use_profile=True launch the
persistent context instead of an ephemeral one. The profile lock refuses
concurrent writers honestly.
"""
import sys
from types import SimpleNamespace
from unittest.mock import patch

from app.tools.browser_automation import BrowserAutomation


class FakePage:
    url = "https://example.test/logged-in"

    def goto(self, *a, **k): pass
    def title(self): return "Example"
    def set_input_files(self, *a, **k): pass
    def click(self, *a, **k): pass
    def wait_for_selector(self, *a, **k): pass
    def is_visible(self, s): return s != ".done"
    def query_selector(self, s): return None


class FakeContext:
    """Records launch_persistent_context usage."""
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.persistent_calls = []
        self.ephemeral_calls = 0
        self._ctx = FakeContext()

    def launch(self, **kwargs):
        self.ephemeral_calls += 1
        return SimpleNamespace(new_page=lambda: FakePage(), close=lambda: None)

    def launch_persistent_context(self, user_data_dir, **kwargs):
        self.persistent_calls.append((user_data_dir, kwargs))
        return self._ctx


class FakePlaywrightHandle:
    """Mimics real sync_playwright(): usable as a context manager AND via .start()."""

    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_playwright(monkeypatch, chromium):
    handle = FakePlaywrightHandle(chromium)
    monkeypatch.setitem(sys.modules, "playwright.sync_api",
                        SimpleNamespace(sync_playwright=lambda: handle))
    return handle


def reset_session_state():
    BrowserAutomation._session_browser = None
    BrowserAutomation._playwright_handle = None
    BrowserAutomation._session_tab = None


def test_open_session_uses_persistent_profile_and_close_persists(tmp_path, monkeypatch):
    from app.cognition.browser_grounding import BrowserGroundingStore
    monkeypatch.setattr(BrowserAutomation, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "g.db"))
    reset_session_state()
    chromium = FakeChromium()
    fake_playwright(monkeypatch, chromium)

    opened = BrowserAutomation.open_session("https://example.test")
    assert opened["success"] is True
    assert chromium.persistent_calls and chromium.persistent_calls[0][0] == str(tmp_path / "profile")
    assert chromium.persistent_calls[0][1].get("headless") is False
    assert (tmp_path / "profile" / "arena.lock").exists()  # advisory lock held

    closed = BrowserAutomation.close_session()
    assert closed["success"] is True
    assert chromium._ctx.closed is True
    assert not (tmp_path / "profile" / "arena.lock").exists()  # lock released


def test_second_session_is_refused_until_closed(tmp_path, monkeypatch):
    from app.cognition.browser_grounding import BrowserGroundingStore
    monkeypatch.setattr(BrowserAutomation, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "g.db"))
    reset_session_state()
    chromium = FakeChromium()
    fake_playwright(monkeypatch, chromium)

    assert BrowserAutomation.open_session("https://example.test")["success"] is True
    second = BrowserAutomation.open_session("https://example.test")
    assert second["success"] is False and second["refused"] is True
    BrowserAutomation.close_session()
    assert BrowserAutomation.open_session("https://example.test")["success"] is True
    BrowserAutomation.close_session()


def test_stale_lock_file_refuses_launch_without_corrupting(tmp_path, monkeypatch):
    from app.cognition.browser_grounding import BrowserGroundingStore
    profile = tmp_path / "profile"
    profile.mkdir(parents=True)
    (profile / "arena.lock").write_text("left by a crashed session")
    monkeypatch.setattr(BrowserAutomation, "PROFILE_DIR", profile)
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "g.db"))
    reset_session_state()
    chromium = FakeChromium()
    fake_playwright(monkeypatch, chromium)
    refused = BrowserAutomation.open_session("https://example.test")
    assert refused["success"] is False and refused["refused"] is True
    assert chromium.persistent_calls == []  # never launched over a locked profile


def test_use_profile_flows_launch_persistent_and_ephemeral_default(tmp_path, monkeypatch):
    from app.cognition.browser_grounding import BrowserGroundingStore
    monkeypatch.setattr(BrowserAutomation, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "g.db"))
    reset_session_state()
    chromium = FakeChromium()
    handle = fake_playwright(monkeypatch, chromium)
    source = tmp_path / "f.txt"
    source.write_text("payload")

    # Ephemeral default: plain launch.
    BrowserAutomation.upload_file(
        "https://example.test", "input[type=file]", str(source), "#submit", ".done"
    )
    assert chromium.ephemeral_calls == 1 and chromium.persistent_calls == []

    # use_profile=True: persistent context with the profile dir.
    BrowserAutomation.upload_file(
        "https://example.test", "input[type=file]", str(source), "#submit", ".done",
        use_profile=True,
    )
    assert len(chromium.persistent_calls) == 1
    assert chromium.persistent_calls[0][0] == str(tmp_path / "profile")
    # The lock is released when the flow closes the browser.
    assert not (tmp_path / "profile" / "arena.lock").exists()
