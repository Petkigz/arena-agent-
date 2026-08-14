import pytest
from pathlib import Path
import tempfile
from app.perception.text_to_speech import LocalTextToSpeech
from app.perception.speech_to_text import LocalSpeechToText

def test_text_to_speech_synthesis():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "test_synthesis.wav"
        res = LocalTextToSpeech.synthesize_speech("Hello, testing local speech synthesis.", filename=test_file)
        assert res["success"] is True
        assert res["audio_url"] == f"/audio/{test_file}"
        assert Path(res["file_path"]).exists()

def test_speech_to_text_file_not_found():
    res = LocalSpeechToText.transcribe_file("non_existent_audio_file.wav")
    assert res["success"] is False
    assert "Audio file not found" in res["error"]
