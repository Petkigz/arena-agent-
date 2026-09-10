"""Phase 0 — safe deterministic baseline + startup readiness (owner plan
2026-09-10).

Pinned here:
  * the readiness probe reads the NATIVE load state (a pinned-but-not-
    loaded model must be reported at startup, not discovered via a 400
    at the first message);
  * the snapshot is honest when the provider is down (no crash, no
    invented models);
  * background-job defaults are the Phase 0 safe ones (parked rechecks
    OFF, autonomy OFF) until the typed event ledger lands;
  * the server actually wires the startup block, the endpoint, and the
    headless auto-open guard.
"""

import json

import pytest

from app.config import Settings
from app.utils.readiness import (
    collect_readiness,
    format_readiness,
    probe_provider,
)


class _FakeResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestProviderProbe:
    def test_native_state_is_authoritative(self, monkeypatch):
        # The 14B-over-9B incident: the OpenAI-compatible listing includes
        # DOWNLOADED-but-not-loaded models; only the native state field
        # tells the truth.
        def fake_urlopen(url, timeout=None):
            if url.endswith("/api/v0/models"):
                return _FakeResp({"data": [
                    {"id": "qwen2.5-9b-instruct-live", "state": "loaded"},
                    {"id": "qwen/qwen3-14b", "state": "not-loaded"},
                ]})
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        out = probe_provider("http://localhost:1234/v1")
        assert out["reachable"] is True
        assert out["loaded_models"] == ["qwen2.5-9b-instruct-live"]

    def test_unreachable_provider_is_honest(self, monkeypatch):
        def fake_urlopen(url, timeout=None):
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        out = probe_provider("http://localhost:1234/v1")
        assert out["reachable"] is False
        assert out["loaded_models"] is None


class TestReadinessSnapshot:
    @pytest.fixture
    def snapshot(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.MAIN_MODEL", "qwen2.5-9b-instruct")
        monkeypatch.setattr("app.config.settings.FAST_MODEL", "auto")
        monkeypatch.setattr("app.config.settings.CODE_MODEL", "auto")
        return collect_readiness(probe_provider_fn=lambda base: {
            "reachable": True,
            "endpoint": "native",
            "loaded_models": ["qwen2.5-3b-instruct"],
        })

    def test_pinned_but_unloaded_model_is_called_out(self, snapshot):
        main = snapshot["models"]["main"]
        assert main["configured"] == "qwen2.5-9b-instruct"
        assert main["resolution"].startswith("NOT loaded")

    def test_auto_lanes_are_described_not_guessed(self, snapshot):
        assert "best loaded" in snapshot["models"]["fast"]["resolution"]

    def test_background_jobs_report_their_flags(self, snapshot, monkeypatch):
        monkeypatch.setattr("app.config.settings.ARENA_PARKED_RECHECK", "1")
        snap = collect_readiness(probe_provider_fn=lambda base: {
            "reachable": False, "loaded_models": None})
        assert snap["background_jobs"]["parked_goal_recheck"] == "enabled"
        assert snapshot["background_jobs"]["autonomy_mode"]

    def test_opencv_and_browser_sections_are_always_present(self, snapshot):
        assert "cascade" in snapshot["opencv"]
        assert "available" in snapshot["browser"]

    def test_format_is_owner_readable(self, snapshot):
        text = format_readiness(snapshot)
        assert "STARTUP READINESS" in text
        assert "qwen2.5-9b-instruct" in text
        assert "NOT loaded" in text


class TestPhase0Defaults:
    def test_safe_defaults(self, monkeypatch):
        # Phase 0: no autonomous replays or cycles unless explicitly on.
        for var in ("ARENA_PARKED_RECHECK", "LPA_ARENA_PARKED_RECHECK",
                    "AUTONOMY_MODE", "LPA_AUTONOMY_MODE"):
            monkeypatch.delenv(var, raising=False)
        s = Settings(_env_file=None)
        assert s.ARENA_PARKED_RECHECK == "0"
        assert s.AUTONOMY_MODE == "off"

    def test_owner_can_still_enable_explicitly(self, monkeypatch):
        monkeypatch.setenv("ARENA_PARKED_RECHECK", "1")
        monkeypatch.setenv("AUTONOMY_MODE", "supervised")
        monkeypatch.delenv("LPA_ARENA_PARKED_RECHECK", raising=False)
        monkeypatch.delenv("LPA_AUTONOMY_MODE", raising=False)
        s = Settings(_env_file=None)
        assert s.ARENA_PARKED_RECHECK == "1"
        assert s.AUTONOMY_MODE == "supervised"


def test_server_wires_readiness_and_headless_guard():
    import inspect

    import app.server as server_module

    src = inspect.getsource(server_module)
    assert '"/readiness"' in src
    assert "collect_readiness" in src
    assert "_headless_environment" in src
    assert "ARENA_READINESS" in src
