"""Owner-managed inference profile: measured recommendations, live apply, probe honesty."""
import json
from unittest.mock import patch

import httpx
import pytest

import app.config as config_module
from app.cognition.inference_profile import (
    InferenceProfile,
    InferenceProfileStore,
    apply_profile,
    probe_provider,
)


@pytest.fixture(autouse=True)
def restore_settings():
    """apply_profile mutates global settings; restore them around every test."""
    saved = (
        config_module.settings.MAIN_MODEL,
        config_module.settings.FAST_MODEL,
        config_module.settings.LM_STUDIO_URL,
    )
    yield
    (
        config_module.settings.MAIN_MODEL,
        config_module.settings.FAST_MODEL,
        config_module.settings.LM_STUDIO_URL,
    ) = saved


def tier(level=1, ram=48.0, context=8192):
    return {"tier_level": level, "total_ram_gb": ram, "max_context_budget_tokens": context}


def test_recommendation_derives_from_measured_tier(tmp_path):
    with patch("app.cognition.inference_profile._hardware_tier", return_value=tier(1, 48.0, 8192)):
        high = InferenceProfile.recommended()
    with patch("app.cognition.inference_profile._hardware_tier", return_value=tier(2, 24.0, 4096)):
        mid = InferenceProfile.recommended()
    with patch("app.cognition.inference_profile._hardware_tier", return_value=tier(3, 8.0, 2048)):
        low = InferenceProfile.recommended()
    assert high.main_model == "qwen2.5-14b-instruct" and high.context_window_tokens == 8192
    assert mid.main_model == "qwen2.5-9b-instruct" and mid.context_window_tokens == 4096
    assert low.main_model == "qwen2.5-3b-instruct" and low.context_window_tokens == 2048


def test_first_load_initializes_from_measured_recommendation(tmp_path):
    with patch("app.cognition.inference_profile._hardware_tier", return_value=tier(1, 48.0, 8192)):
        store = InferenceProfileStore(tmp_path / "ip.json")
        assert store.get().main_model == "qwen2.5-14b-instruct"
        assert store.get().revision == 0  # untouched recommendation


def test_update_persists_validates_and_bumps_revision(tmp_path):
    store = InferenceProfileStore(tmp_path / "ip.json")
    updated = store.update({"main_model": "qwen2.5-14b-instruct", "context_window_tokens": 8192})
    assert updated.revision == 1 and updated.context_window_tokens == 8192
    raw = json.loads((tmp_path / "ip.json").read_text())
    assert raw["main_model"] == "qwen2.5-14b-instruct"
    reloaded = InferenceProfileStore(tmp_path / "ip.json")
    assert reloaded.get().main_model == "qwen2.5-14b-instruct" and reloaded.get().revision == 1


def test_invalid_updates_are_rejected(tmp_path):
    store = InferenceProfileStore(tmp_path / "ip.json")
    for bad in (
        {"nonsense": 1},
        {"main_model": "   "},
        {"provider_url": "not-a-url"},
        {"context_window_tokens": 100},       # below minimum
        {"context_window_tokens": 999999},    # above maximum
        {"context_window_tokens": "lots"},
    ):
        with pytest.raises(ValueError):
            store.update(bad)
    assert store.get().revision == 0  # nothing applied


def test_malformed_file_fails_safe_to_measured_recommendation(tmp_path):
    path = tmp_path / "ip.json"
    path.write_text("{ broken json")
    with patch("app.cognition.inference_profile._hardware_tier", return_value=tier(2, 24.0, 4096)):
        store = InferenceProfileStore(path)
    assert store.get().main_model == "qwen2.5-9b-instruct"


def test_context_above_measured_budget_is_flagged_not_blocked(tmp_path):
    with patch("app.cognition.inference_profile._hardware_tier", return_value=tier(1, 48.0, 8192)):
        store = InferenceProfileStore(tmp_path / "ip.json")
    owner_choice = store.update({"context_window_tokens": 16384})
    divergence = store.divergence(owner_choice)
    assert divergence["exceeds_measured_budget"] is True
    assert divergence["recommendation_match"] is False  # observation, not falsification


def test_apply_profile_is_the_single_write_path(tmp_path):
    from app.llm import llm_client

    store = InferenceProfileStore(tmp_path / "ip.json")
    profile = store.update({"main_model": "qwen2.5-14b-instruct", "provider_url": "http://localhost:1234/v1"})
    applied = apply_profile(profile)
    assert applied["applied"] is True
    assert config_module.settings.MAIN_MODEL == "qwen2.5-14b-instruct"
    assert llm_client.base_url == "http://localhost:1234/v1"


def test_probe_offline_reports_unknown_not_failure_of_capability():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    profile = InferenceProfile(main_model="m", fast_model="f", provider_url="http://localhost:9/v1")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    evidence = probe_provider(profile, client=client, timeout=1.0)
    assert evidence["provider_online"] is False
    assert evidence["main_model_loaded"] is None  # unknown, not False-with-certainty
    assert evidence["completion_probe"] is None
    assert "offline" in evidence["error"] or "unreachable" in evidence["error"]
    client.close()


def test_probe_online_measures_loaded_models_and_latency():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen2.5-14b-instruct"}]})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": " ready"}}],
                "usage": {"completion_tokens": 2},
            },
        )

    profile = InferenceProfile(main_model="qwen2.5-14b-instruct", fast_model="qwen2.5-3b-instruct", provider_url="http://localhost:1234/v1")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    evidence = probe_provider(profile, client=client)
    assert evidence["provider_online"] is True
    assert evidence["main_model_loaded"] is True
    assert evidence["fast_model_loaded"] is False
    assert evidence["completion_probe"]["verified"] is True
    assert isinstance(evidence["latency_ms"], float) and evidence["latency_ms"] >= 0
    client.close()


def test_owner_inference_profile_endpoints(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.cognition.inference_profile as ip

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    monkeypatch.setattr(ip, "inference_profile_store", ip.InferenceProfileStore(tmp_path / "ip.json"))
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    current = client.get("/owner-control/inference-profile", headers=headers)
    assert current.status_code == 200
    body = current.json()
    assert body["profile"]["revision"] == 0
    assert "divergence" in body

    updated = client.put(
        "/owner-control/inference-profile",
        headers=headers,
        json={"main_model": "qwen2.5-14b-instruct", "context_window_tokens": 8192},
    )
    assert updated.json()["success"] is True
    assert updated.json()["profile"]["revision"] == 1
    assert updated.json()["applied"]["main_model"] == "qwen2.5-14b-instruct"

    bad = client.put(
        "/owner-control/inference-profile",
        headers=headers,
        json={"provider_url": "ftp://nope"},
    )
    assert bad.json()["success"] is False

    probe = client.post("/owner-control/inference-profile/probe", headers=headers)
    evidence = probe.json()["evidence"]
    assert probe.status_code == 200 and evidence["provider_online"] is False


def test_legacy_models_config_writes_through_profile_store(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.cognition.inference_profile as ip

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    store = ip.InferenceProfileStore(tmp_path / "ip.json")
    monkeypatch.setattr(ip, "inference_profile_store", store)
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    response = client.post(
        "/models/config",
        headers=headers,
        json={"main_model": "qwen2.5-14b-instruct", "lm_studio_url": "http://localhost:1234/v1"},
    )
    body = response.json()
    assert body["success"] is True and body["configured_main_model"] == "qwen2.5-14b-instruct"
    assert store.get().main_model == "qwen2.5-14b-instruct"  # single persisted source of truth
    assert store.get().revision == 1


def test_benchmark_reports_offline_honestly(monkeypatch, tmp_path):
    from scripts.benchmark_lm_studio import run as benchmark_run

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    profile = InferenceProfile(main_model="m", fast_model="f", provider_url="http://localhost:9/v1")
    monkeypatch.chdir(tmp_path)
    with patch("app.cognition.inference_profile.inference_profile_store") as store:
        store.get.return_value = profile
        with patch("app.cognition.inference_profile.probe_provider", return_value=probe_provider(profile, client=httpx.Client(transport=httpx.MockTransport(handler)), completion_probe=False)):
            report = benchmark_run()
    assert report["success"] is False
    assert report["provider_online"] is False
    assert "provider offline" in report["error"]


def test_benchmark_measures_models_online(monkeypatch, tmp_path):
    from scripts.benchmark_lm_studio import run as benchmark_run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "answer text"}}],
                "usage": {"completion_tokens": 10},
            },
        )

    profile = InferenceProfile(main_model="model-a", fast_model="model-b", provider_url="http://localhost:1234/v1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.cognition.inference_profile.inference_profile_store.get", lambda: profile
    )
    with patch(
        "scripts.benchmark_lm_studio.probe_provider",
        return_value=probe_provider(
            profile, client=httpx.Client(transport=httpx.MockTransport(handler)), completion_probe=False
        ),
    ):
        report = benchmark_run(["model-a", "model-b"], client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(handler)))
    assert report["success"] is True
    assert report["provider_online"] is True
    by_model = {r["model"]: r for r in report["results"]}
    assert by_model["model-a"]["completed_samples"] == report["prompts_per_model"]
    assert by_model["model-a"]["usage_reported"] is True
    assert by_model["model-a"]["completion_tokens_per_second_mean"] > 0
    assert "ram_after" in report


def test_probe_uses_configured_models_only_and_reports_served_model(tmp_path):
    """Live-hardware regression: models[0] picked a reasoning model (50.8s,
    empty visible channel). The probe must target configured models only and
    flag when the provider loosely resolves to a different model."""
    import httpx
    from app.cognition.inference_profile import InferenceProfile, probe_provider

    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [
                    {"id": "qwen/qwen3-14b"},          # listed FIRST on purpose
                    {"id": "qwen2.5-3b-instruct"},     # the configured fast model
                ]})
            body = json.loads(request.content)
            # Server loosely resolves every request to its first model.
            return httpx.Response(200, json={
                "model": "qwen/qwen3-14b",
                "choices": [{"message": {"content": "ready"}}],
                "usage": {"completion_tokens": 1},
            })

    profile = InferenceProfile(main_model="qwen2.5-14b-instruct",
                               fast_model="qwen2.5-3b-instruct",
                               provider_url="http://127.0.0.1:1234/v1")
    evidence = probe_provider(profile, client=httpx.Client(transport=FakeTransport()), timeout=5.0)
    probe = evidence["completion_probe"]
    assert probe["model"] == "qwen2.5-3b-instruct"      # configured fast, NOT models[0]
    assert probe["served_model"] == "qwen/qwen3-14b"    # what actually answered
    assert probe["resolved_differently"] is True
    assert probe["verified"] is False                   # evidence about the wrong model


def test_probe_refuses_when_no_configured_model_loaded(tmp_path):
    import httpx
    from app.cognition.inference_profile import InferenceProfile, probe_provider

    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(200, json={"data": [{"id": "something-else"}]})

    profile = InferenceProfile(main_model="qwen2.5-14b-instruct",
                               fast_model="qwen2.5-3b-instruct",
                               provider_url="http://127.0.0.1:1234/v1")
    evidence = probe_provider(profile, client=httpx.Client(transport=FakeTransport()), timeout=5.0)
    assert evidence["completion_probe"]["success"] is False
    assert "refusing to probe an arbitrary" in evidence["completion_probe"]["reason"]


def test_benchmark_flags_loose_model_resolution(tmp_path):
    """A 'benchmark of X' served by model Y is not a benchmark of X."""
    import importlib.util
    import sys
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "benchmark_lm_studio",
        Path(__file__).resolve().parents[1] / "scripts" / "benchmark_lm_studio.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import httpx

    class ResolvingTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(200, json={
                "model": "qwen/qwen3-14b",
                "choices": [{"message": {"content": "answer " * 50}}],
                "usage": {"completion_tokens": 100},
            })

    client = httpx.Client(transport=ResolvingTransport())
    result = module.benchmark_model(client, "http://127.0.0.1:1234/v1", "qwen2.5-14b-instruct")
    assert result["requested_model_served"] is False
    assert result["success"] is False  # honest: samples are about the wrong model
    assert "NOT evidence about the requested model" in result["resolution_warning"]
