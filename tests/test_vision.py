import pytest
from pathlib import Path
import tempfile
from app.tools.screen_capture import ScreenCaptureTool
from app.tools.ocr_reader import OCRReaderTool
from app.tools.vision_analyzer import VisionAnalyzerTool

def test_screen_capture_tool():
    res = ScreenCaptureTool.capture_screen("test_capture.png")
    assert res["success"] is True
    assert Path(res["file_path"]).exists()

def test_screen_capture_delta():
    res1 = ScreenCaptureTool.capture_screen_delta()
    assert res1["success"] is True
    assert "screen_changed" in res1

def test_ocr_reader_tool_missing_file():
    res = OCRReaderTool.extract_text_from_image("missing_image.png")
    assert res["success"] is False
    assert "not found" in res["error"]

def test_vision_analyzer_simulation():
    # Capture screen first
    cap = ScreenCaptureTool.capture_screen("test_vision_input.png")
    assert cap["success"] is True

    # Run vision analysis
    analysis = VisionAnalyzerTool.analyze_screen_image(cap["file_path"], prompt_focus="check window")
    assert analysis["success"] is True
    assert "image_name" in analysis
