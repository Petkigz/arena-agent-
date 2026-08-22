"""Tests for the shared Piper TTS integration (app/perception/piper_voice.py)."""

from pathlib import Path

import numpy as np

from app.perception import piper_voice as pv


class TestDescribeModel:
    def test_standard_voice_name(self):
        info = pv._describe_model(Path("en_US-lessac-medium.onnx"))
        assert info is not None
        assert info["id"] == "en_US-lessac-medium"
        assert info["language"] == "en"
        assert info["region"] == "US"
        assert info["quality"] == "medium"
        assert info["path"].endswith("en_US-lessac-medium.onnx")
        assert "has_config" in info

    def test_swahili_voice_name(self):
        info = pv._describe_model(Path("sw_KE-lanfrica-medium.onnx"))
        assert info is not None
        assert info["language"] == "sw"
        assert info["region"] == "KE"
        assert info["quality"] == "medium"

    def test_non_onnx_rejected(self):
        assert pv._describe_model(Path("notes.txt")) is None


class TestResample:
    def test_identity_when_rates_equal(self):
        audio = np.linspace(0, 1, 100, dtype=np.float32)
        out = pv.resample(audio, 16000, 16000)
        assert out is audio  # same object returned

    def test_downsample_length(self):
        src, dst = 22050, 16000
        n = 22050  # 1 second
        audio = np.random.randn(n).astype(np.float32)
        out = pv.resample(audio, src, dst)
        assert out.dtype == np.float32
        assert abs(len(out) - dst) <= 2  # ~1 second at 16k

    def test_empty_safe(self):
        out = pv.resample(np.array([], dtype=np.float32), 22050, 16000)
        assert out.size == 0


class TestFindModels:
    def test_recursive_discovery(self, tmp_path, monkeypatch):
        # Nested model in its own subfolder (a common download layout).
        nested = tmp_path / "en_US-lessac-medium"
        nested.mkdir()
        (nested / "en_US-lessac-medium.onnx").write_bytes(b"dummy")
        (nested / "en_US-lessac-medium.onnx.json").write_text("{}")

        monkeypatch.setattr(pv, "_candidate_dirs", lambda: [tmp_path])
        monkeypatch.setattr(pv, "_models_cache", None)

        models = pv.find_piper_models()
        assert len(models) == 1
        assert models[0]["id"] == "en_US-lessac-medium"
        assert models[0]["has_config"] is True


class TestResolveVoiceId:
    def test_unknown_voice_falls_back_to_default(self, monkeypatch):
        def fake_find(voice_id):
            if voice_id == pv.DEFAULT_VOICE_ID:
                return {"id": pv.DEFAULT_VOICE_ID, "path": "/x.onnx"}
            return None

        monkeypatch.setattr(pv, "find_model_for_voice", fake_find)
        assert pv.resolve_voice_id("does-not-exist") == pv.DEFAULT_VOICE_ID

    def test_valid_voice_returned_as_is(self, monkeypatch):
        monkeypatch.setattr(
            pv,
            "find_model_for_voice",
            lambda v: {"id": v, "path": f"/{v}.onnx"} if v == "sw_KE-lanfrica-medium" else None,
        )
        assert pv.resolve_voice_id("sw_KE-lanfrica-medium") == "sw_KE-lanfrica-medium"


class TestCandidateDirs:
    def test_includes_override_dir(self, monkeypatch):
        monkeypatch.setenv("ARENA_PIPER_MODEL_DIR", "/tmp/voices")
        dirs = pv._candidate_dirs()
        assert any(str(d).endswith("voices") for d in dirs)
