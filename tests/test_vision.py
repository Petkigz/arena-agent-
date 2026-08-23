import pytest
from pathlib import Path
import tempfile
from app.tools.screen_capture import ScreenCaptureTool
from app.tools.ocr_reader import OCRReaderTool
from app.tools.vision_analyzer import VisionAnalyzerTool
from app.tools.knowledge_indexer import KnowledgeIndexer

def test_screen_capture_tool():
    res = ScreenCaptureTool.capture_screen("test_capture.png")
    if res["success"]:
        assert Path(res["file_path"]).exists()
    else:
        assert res.get("available") is False
        assert res["file_path"] == ""

def test_screen_capture_delta():
    res1 = ScreenCaptureTool.capture_screen_delta()
    if res1["success"]:
        assert "screen_changed" in res1
    else:
        assert res1.get("available") is False

def test_ocr_reader_tool_missing_file():
    res = OCRReaderTool.extract_text_from_image("missing_image.png")
    assert res["success"] is False
    assert "not found" in res["error"]

def test_vision_analyzer_simulation():
    # Capture screen first
    cap = ScreenCaptureTool.capture_screen("test_vision_input.png")
    if not cap["success"]:
        pytest.skip("Physical display capture unavailable")

    # Run vision analysis
    analysis = VisionAnalyzerTool.analyze_screen_image(cap["file_path"], prompt_focus="check window")
    assert analysis["success"] is True
    assert "image_name" in analysis


def test_analyze_image_skips_delta_check(monkeypatch, tmp_path):
    """/vision/analyze analyzes an explicit image and must NOT apply the
    screen-delta dedup (regression: B1 — it was skipping analysis of uploaded
    images whenever the live screen was unchanged)."""
    # Fake image file on disk.
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    calls = {"delta": 0, "ocr": 0}

    def fake_delta():
        calls["delta"] += 1
        raise AssertionError("capture_screen_delta must not run for explicit image analysis")

    monkeypatch.setattr(ScreenCaptureTool, "capture_screen_delta", fake_delta)

    def fake_ocr(path):
        calls["ocr"] += 1
        return {"success": True, "extracted_text": "hello from image"}

    monkeypatch.setattr(OCRReaderTool, "extract_text_from_image", fake_ocr)

    class _FakeLLM:
        def generate_chat_completion(self, messages, complexity, max_tokens):
            return {"choices": [{"message": {"content": "an image analysis"}}]}

    monkeypatch.setattr("app.tools.vision_analyzer.llm_client", _FakeLLM())
    monkeypatch.setattr(KnowledgeIndexer, "index_doc_knowledge",
                        lambda *a, **k: 1)

    res = VisionAnalyzerTool.analyze_screen_image(
        str(img), prompt_focus="errors", auto_save_memory=False, skip_delta_check=True,
    )
    assert res["success"] is True
    assert res["ai_analysis"] == "an image analysis"
    assert calls["ocr"] == 1
    assert calls["delta"] == 0


def test_screen_observation_still_uses_delta_check(monkeypatch, tmp_path):
    """The screen-observation path (skip_delta_check=False) still dedupes."""
    img = tmp_path / "screen.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_delta():
        return {"screen_changed": False, "success": True}

    monkeypatch.setattr(ScreenCaptureTool, "capture_screen_delta", fake_delta)

    res = VisionAnalyzerTool.analyze_screen_image(str(img), skip_delta_check=False)
    assert res["success"] is True
    assert res.get("screen_changed") is False
    assert "unchanged" in res.get("ai_analysis", "")
