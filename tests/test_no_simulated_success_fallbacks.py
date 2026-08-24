"""Unavailable execution paths must never report simulated success."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.perception.text_to_speech import LocalTextToSpeech
from app.tools.browser_automation import BrowserAutomation
from app.tools.deep_os_controller import DeepOSController
from app.tools.media_studio import MediaStudioTool
from app.tools.screen_capture import ScreenCaptureTool
from app.tools.win32_ghost_operator import Win32GhostOperator


class _BrokenPyAutoGUI:
    @staticmethod
    def click(*args, **kwargs):
        raise RuntimeError("no display")

    @staticmethod
    def doubleClick(*args, **kwargs):
        raise RuntimeError("no display")

    @staticmethod
    def write(*args, **kwargs):
        raise RuntimeError("no display")

    @staticmethod
    def hotkey(*args, **kwargs):
        raise RuntimeError("no display")


def test_deep_os_unavailable_is_failure_not_simulation():
    with patch.dict(sys.modules, {"pyautogui": _BrokenPyAutoGUI}):
        click = DeepOSController.mouse_click(10, 20)
        typing = DeepOSController.type_text("hello")
        hotkey = DeepOSController.press_hotkey(["ctrl", "s"])

    for result in (click, typing, hotkey):
        assert result["success"] is False
        assert result["refused"] is True
        assert result["guard_reason"] == "missing_grounding"
        assert result["attempted"] is False
        assert "simulated" not in str(result).lower()
        # Ungrounded calls are refused before the display stack is touched, so
        # the grounded unavailable path is covered separately in
        # tests/test_raw_input_guard.py::test_unavailable_display_reports_failure_not_simulation.


def test_screen_capture_failure_creates_no_fake_screenshot(tmp_path):
    fake_mss = SimpleNamespace(MSS=lambda: (_ for _ in ()).throw(RuntimeError("no display")))
    with (
        patch.object(ScreenCaptureTool, "SCREENSHOTS_DIR", tmp_path),
        patch("app.tools.screen_capture.MSS_AVAILABLE", True),
        patch("app.tools.screen_capture.mss", fake_mss),
    ):
        result = ScreenCaptureTool.capture_screen("screen.png")

    assert result["success"] is False
    assert result["available"] is False
    assert result["file_path"] == ""
    assert not (tmp_path / "screen.png").exists()


def test_win32_operator_does_not_invent_windows_off_platform():
    with patch("app.tools.win32_ghost_operator.platform.system", return_value="Linux"):
        windows = Win32GhostOperator.list_open_windows()
        result = Win32GhostOperator.send_background_window_message("Chrome", "click")

    assert windows == []
    assert result["success"] is False
    assert result["available"] is False
    assert "hwnd" not in result


def test_browser_double_failure_does_not_claim_navigation(tmp_path):
    class _PlaywrightContext:
        def __enter__(self):
            raise RuntimeError("browser unavailable")

        def __exit__(self, *args):
            return False

    fake_playwright = SimpleNamespace(sync_playwright=lambda: _PlaywrightContext())
    fake_httpx = SimpleNamespace(
        Client=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network unavailable"))
    )
    fake_bs4 = SimpleNamespace(BeautifulSoup=object)

    with (
        patch.object(BrowserAutomation, "SCREENSHOTS_DIR", tmp_path),
        patch.dict(sys.modules, {
            "playwright.sync_api": fake_playwright,
            "httpx": fake_httpx,
            "bs4": fake_bs4,
        }),
    ):
        result = BrowserAutomation.navigate_and_extract("https://example.com")

    assert result["success"] is False
    assert result["available"] is False
    assert result["content_snippet"] == ""
    assert "initialized successfully" not in str(result).lower()


def test_invalid_svg_output_does_not_create_generic_placeholder(tmp_path):
    with (
        patch.object(MediaStudioTool, "MEDIA_DIR", tmp_path),
        patch(
            "app.tools.media_studio.llm_client.generate_chat_completion",
            return_value={"id": "chat-simulated", "choices": [{"message": {"content": "[Simulated Response - offline]"}}]},
        ),
    ):
        result = MediaStudioTool.generate_svg_graphic("specific logo", "logo.svg")

    assert result["success"] is False
    assert result["file_path"] == ""
    assert not (tmp_path / "logo.svg").exists()


def test_removed_fabrication_markers_do_not_return_to_production_python():
    root = Path(__file__).resolve().parents[1]
    production = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for base in (root / "app", root / "backend")
        for path in base.rglob("*.py")
    )
    forbidden = [
        "click_simulated",
        "typed_text_simulated",
        "hotkey_simulated",
        "Simulated Background Window",
        "Browser automation session initialized successfully.",
        "SYSTEM DESKTOP SCREENSHOT - SIMULATED DISPLAY",
        "Speaker verification fallback passed",
    ]
    assert [marker for marker in forbidden if marker in production] == []


def test_tts_failure_does_not_create_tone_and_call_it_speech(tmp_path):
    fake_pyttsx3 = SimpleNamespace(init=lambda: (_ for _ in ()).throw(RuntimeError("no voice driver")))
    with (
        patch.object(LocalTextToSpeech, "AUDIO_DIR", tmp_path),
        patch("app.perception.text_to_speech.PIPER_AVAILABLE", False),
        patch.dict(sys.modules, {"pyttsx3": fake_pyttsx3}),
    ):
        result = LocalTextToSpeech.synthesize_speech("hello", filename="speech.wav")

    assert result["success"] is False
    assert result["available"] is False
    assert result["audio_url"] == ""
    assert not (tmp_path / "speech.wav").exists()
