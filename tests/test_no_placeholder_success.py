"""Regression guards: unavailable perception features must never fabricate success."""

import asyncio
import base64
import io
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from backend.api import screenshot_routes, speaker_routes, wakeword_routes
from app.perception.speech_to_text import LocalSpeechToText


def _png_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), color=(255, 255, 255)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_wakeword_training_reports_unavailable_and_creates_no_model(tmp_path):
    wakeword_routes.wakeword_models.clear()
    samples = [
        wakeword_routes.WakeWordSample(
            id=f"sample-{index}",
            audio=base64.b64encode(b"real-audio-bytes").decode("ascii"),
            timestamp="2026-08-23T00:00:00Z",
            duration=1.5,
            sample_rate=16000,
            channels=1,
        )
        for index in range(5)
    ]
    request = wakeword_routes.WakeWordTrainingRequest(
        wake_word="Hey Beanie", samples=samples
    )

    with patch.object(wakeword_routes, "WAKEWORD_DIR", tmp_path):
        result = asyncio.run(wakeword_routes.train_wake_word(request))

    assert result.success is False
    assert result.available is False
    assert result.accuracy is None
    assert result.model_id is None
    assert wakeword_routes.wakeword_models == {}
    assert list(tmp_path.iterdir()) == []


def test_legacy_placeholder_wakeword_model_cannot_activate(tmp_path):
    model_path = tmp_path / "legacy.onnx"
    model_path.write_bytes(b"PLACEHOLDER_MODEL")
    model = wakeword_routes.WakeWordModel(
        id="legacy",
        name="Legacy fake",
        wake_word="fake",
        model_path=str(model_path),
        created_at="2026-08-23T00:00:00Z",
        sample_count=5,
    )
    wakeword_routes.wakeword_models[model.id] = model
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(wakeword_routes.activate_wake_word_model(model.id))
        assert exc.value.status_code == 409
        assert model.is_active is False
    finally:
        wakeword_routes.wakeword_models.clear()


def test_missing_voice_reference_is_unknown_not_verified(tmp_path):
    with patch("app.perception.speech_to_text.settings.DATA_DIR", tmp_path):
        result = LocalSpeechToText.verify_speaker_voice(str(tmp_path / "input.wav"))

    assert result["verified"] is False
    assert result["available"] is False
    assert result["confidence"] == 0.0


def test_speaker_enrollment_is_501_without_embedding_engine():
    speaker_routes.enrolled_speakers.clear()
    request = speaker_routes.EnrollmentRequest(
        name="Owner",
        samples=[base64.b64encode(b"wav").decode("ascii")] * 3,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(speaker_routes.enroll_speaker(request))

    assert exc.value.status_code == 501
    assert speaker_routes.enrolled_speakers == {}


def test_speaker_identification_never_returns_first_record_as_fake_match():
    speaker_routes.enrolled_speakers["metadata-only"] = speaker_routes.Speaker(
        id="metadata-only",
        name="Owner",
        enrolled_at="2026-08-23T00:00:00Z",
        sample_count=3,
        embedding_path=None,
    )
    upload = UploadFile(filename="sample.wav", file=io.BytesIO(b"audio bytes"))
    try:
        result = asyncio.run(speaker_routes.identify_speaker(upload))
    finally:
        speaker_routes.enrolled_speakers.clear()

    assert result.success is False
    assert result.available is False
    assert result.speaker_id is None
    assert result.confidence is None


def test_screenshot_analysis_calls_real_components_and_reports_results():
    screenshot_routes.screenshot_store.clear()
    screenshot_routes.screenshot_store["shot-1"] = {"image": _png_base64()}
    ocr = Mock(return_value={"success": True, "extracted_text": "Settings"})
    vision = Mock(return_value={
        "success": True,
        "ai_analysis": "A settings window is visible",
        "detections": [{"label": "window", "confidence": 0.9}],
        "groundings_created": ["window"],
        "engine": "test_vlm",
    })
    fake_ocr_module = SimpleNamespace(
        OCRReaderTool=SimpleNamespace(extract_text_from_image=ocr)
    )
    fake_vision_module = SimpleNamespace(
        VisionAnalyzerTool=SimpleNamespace(analyze_screen_image=vision)
    )

    with patch.dict(sys.modules, {
        "app.tools.ocr_reader": fake_ocr_module,
        "app.tools.vision_analyzer": fake_vision_module,
    }):
        result = asyncio.run(screenshot_routes.analyze_screenshot(
            screenshot_routes.ScreenshotAnalysisRequest(
                screenshot_id="shot-1", analysis_type="both", prompt_focus="settings"
            )
        ))

    assert result.success is True
    assert result.analysis["complete"] is True
    assert result.analysis["components"]["ocr"]["text"] == "Settings"
    assert result.analysis["components"]["vision"]["engine"] == "test_vlm"
    assert "Analysis of screenshot" not in str(result.analysis)
    ocr.assert_called_once()
    vision.assert_called_once()


def test_screenshot_partial_failure_is_not_reported_as_complete_success():
    screenshot_routes.screenshot_store.clear()
    screenshot_routes.screenshot_store["shot-2"] = {"image": _png_base64()}
    fake_ocr_module = SimpleNamespace(
        OCRReaderTool=SimpleNamespace(
            extract_text_from_image=Mock(return_value={"success": False, "error": "Tesseract missing"})
        )
    )
    fake_vision_module = SimpleNamespace(
        VisionAnalyzerTool=SimpleNamespace(
            analyze_screen_image=Mock(return_value={"success": True, "ai_analysis": "Real vision output"})
        )
    )

    with patch.dict(sys.modules, {
        "app.tools.ocr_reader": fake_ocr_module,
        "app.tools.vision_analyzer": fake_vision_module,
    }):
        result = asyncio.run(screenshot_routes.analyze_screenshot(
            screenshot_routes.ScreenshotAnalysisRequest(
                screenshot_id="shot-2", analysis_type="both"
            )
        ))

    assert result.success is False
    assert result.analysis["complete"] is False
    assert result.analysis["components"]["vision"]["success"] is True
    assert "Tesseract missing" in result.error


def test_invalid_screenshot_bytes_fail_without_analysis_claim():
    screenshot_routes.screenshot_store.clear()
    screenshot_routes.screenshot_store["bad"] = {"image": base64.b64encode(b"not an image").decode("ascii")}

    result = asyncio.run(screenshot_routes.analyze_screenshot(
        screenshot_routes.ScreenshotAnalysisRequest(screenshot_id="bad")
    ))

    assert result.success is False
    assert result.analysis is None
