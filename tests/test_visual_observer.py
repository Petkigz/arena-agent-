"""VisualObserver tests — the deterministic "understand the screen" step."""

from app.cognition.visual_observer import VisualObserver, VisualObservation


def test_observe_missing_file_degrades_cleanly():
    v = VisualObserver.observe_screenshot("/nonexistent/screen.png")
    assert isinstance(v, VisualObservation)
    assert v.has_content is False
    assert "not found" in v.error


def test_observe_captured_screenshot_produces_typed_observation():
    import pytest
    from app.tools.screen_capture import ScreenCaptureTool
    cap = ScreenCaptureTool.capture_screen("vis_test.png")
    if not cap["success"]:
        pytest.skip("Physical display capture unavailable")

    v = VisualObserver.observe_screenshot(cap["file_path"])
    assert isinstance(v, VisualObservation)
    # Tesseract may or may not be installed. Either way, a real captured image
    # produces a typed observation with timestamp and dimensions.
    assert v.image_name == "vis_test.png"
    assert v.timestamp
    # Width/height are read from the real image.
    assert v.width is not None
    assert v.height is not None


def test_to_dict_shape():
    v = VisualObserver.observe_screenshot("/nonexistent/x.png")
    d = v.to_dict()
    for key in ("timestamp", "file_path", "image_name", "has_content",
                "visible_text", "word_count", "width", "height", "error"):
        assert key in d


def test_visual_observation_has_content_flag_false_on_empty():
    v = VisualObservation(
        timestamp="2026-01-01T00:00:00+00:00",
        file_path="/x.png",
        image_name="x.png",
        has_content=False,
        visible_text="",
        word_count=0,
    )
    assert v.has_content is False
    assert v.visible_text == ""
