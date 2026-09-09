"""Owner live findings 2026-09-09 — the model lane must serve HER
loaded models, not fight them.

Live log evidence:
- MAIN_MODEL=qwen2.5-9b-instruct did not match her loaded 9B ("the
  model has other words on the title") and role scoring pulled the 14B
  into VRAM over it. A pinned id must be SATISFIED by a loaded id with
  extra title words — same model, silently, never a scored fallback.
- LM Studio answered a not-loaded fast model with "Please load the
  model ... first" — the retry regex missed that phrasing and the
  request fell straight to simulation while loaded models sat idle.
- The coding model must be LOADED ON DEMAND and EJECTED afterwards —
  the VRAM belongs to the chat models she keeps loaded.

Contracts pinned here:
- fuzzy satisfaction: unique token-subsequence match = same model;
  sizes never cross (9b pinned never 'matches' 14b loaded);
  ambiguity goes to the loud scored fallback;
- the 'please load the model ... first' 400 triggers the existing
  retry-once-with-a-loaded-fallback ladder;
- code lane: loads the pinned (or biggest downloaded) coder on demand,
  uses it, ejects it after a quiet window; never ejects a coder the
  owner loaded herself; every API gap degrades to the main lane
  honestly; ARENA kill switch CODE_MODEL_AUTOSWAP=0 stands down.
"""

from __future__ import annotations

import time

import httpx
import pytest

from app.config import settings
from app.llm import LocalLLMClient


@pytest.fixture(autouse=True)
def _real_llm_transport(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)


class _FakeNativeHTTP:
    """Stands in for httpx.Client: LM Studio native API (models with
    load state + load/unload), the legacy listing, and completions."""

    def __init__(self, native_models=None, legacy_models=None,
                 completions=None, native_available=True):
        # native_models: [{"id": str, "state": "loaded"|"not-loaded"}]
        self.native_models = list(native_models or [])
        self.legacy_models = list(legacy_models or [])
        self.completions = list(completions or [])
        self.native_available = native_available
        self.load_calls = []
        self.unload_calls = []
        self.completion_payloads = []
        self.is_closed = False

    # -- httpx.Client surface used by LocalLLMClient --
    def get(self, url, **kwargs):
        if url.endswith("/api/v0/models"):
            if not self.native_available:
                return _Resp(404, {})
            return _Resp(200, {"data": [dict(m) for m in self.native_models]})
        if url.endswith("/models"):
            return _Resp(200, {"data": [{"id": m} for m in self.legacy_models]})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, json=None, **kwargs):
        if url.endswith(("/api/v0/models/load", "/api/v0/models/unload")) \
                and not self.native_available:
            return _Resp(404, {"error": "no native API"})
        if url.endswith("/api/v0/models/load"):
            self.load_calls.append(dict(json or {}))
            for m in self.native_models:
                if m["id"] == (json or {}).get("identifier"):
                    m["state"] = "loaded"
            return _Resp(200, {"success": True})
        if url.endswith("/api/v0/models/unload"):
            self.unload_calls.append(dict(json or {}))
            for m in self.native_models:
                if m["id"] == (json or {}).get("identifier"):
                    m["state"] = "not-loaded"
            return _Resp(200, {"success": True})
        if url.endswith("/chat/completions"):
            self.completion_payloads.append(dict(json or {}))
            if not self.completions:
                return _Resp(200, _ok_completion((json or {}).get("model")))
            item = self.completions.pop(0)
            if isinstance(item, tuple):  # (status, text) -> error
                return _Resp(item[0], {"error": {"message": item[1]}},
                             text=item[1])
            return _Resp(200, _ok_completion((json or {}).get("model")))
        raise AssertionError(f"unexpected POST {url}")

    def close(self):
        self.is_closed = True


class _Resp:
    def __init__(self, status_code, json_data, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or str(json_data)
        self.ok = status_code < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code}'",
                request=httpx.Request("POST", "http://test/v1/chat/completions"),
                response=httpx.Response(self.status_code, text=self.text))

    def json(self):
        return self._json


def _ok_completion(model="any"):
    return {"id": "chat-1", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant",
                                                 "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"completion_tokens": 2}}


def _client(fake):
    c = LocalLLMClient(base_url="http://test/v1")
    c.client = fake
    return c


# ── fuzzy title satisfaction (her 9B with extra words) ─────────────────────
def test_pinned_model_satisfied_by_extra_words_in_title():
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen/qwen2.5-9b-instruct-uncensored", "state": "loaded"},
        {"id": "qwen/qwen3-14b", "state": "loaded"},
    ])
    model, info = _client(fake)._resolve_model("qwen2.5-9b-instruct")
    assert model == "qwen/qwen2.5-9b-instruct-uncensored"
    assert info is None, "same model under a drifted title is not a fallback"


def test_fuzzy_never_crosses_sizes():
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-14b-instruct", "state": "loaded"},
    ])
    model, info = _client(fake)._resolve_model("qwen2.5-9b-instruct")
    # 9b pinned must never be 'satisfied' by 14b loaded — the scored
    # fallback stays loud.
    assert model == "qwen2.5-14b-instruct"
    assert info is not None and info["requested"] == "qwen2.5-9b-instruct"


def test_fuzzy_ambiguity_goes_to_the_scored_fallback():
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-9b-instruct-1m", "state": "loaded"},
        {"id": "qwen2.5-9b-instruct-uncensored", "state": "loaded"},
    ])
    _, info = _client(fake)._resolve_model("qwen2.5-9b-instruct")
    assert info is not None, "two candidate matches: choose loudly, not silently"


def test_completion_uses_her_loaded_model_end_to_end(monkeypatch):
    monkeypatch.setattr(settings, "MAIN_MODEL", "qwen2.5-9b-instruct")
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-9b-instruct-1m", "state": "loaded"},
        {"id": "qwen/qwen3-14b", "state": "loaded"},
    ])
    c = _client(fake)
    res = c.generate_chat_completion(
        [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.completion_payloads[0]["model"] == "qwen2.5-9b-instruct-1m"
    assert res.get("model_fallback") is None


# ── the 'please load the model ... first' 400 ───────────────────────────────
def test_please_load_phrasing_triggers_retry_with_a_loaded_model(monkeypatch):
    monkeypatch.setattr(settings, "FAST_MODEL", "qwen2.5-3b-instruct")
    # No native API: the legacy listing claims the downloaded-but-
    # not-loaded 3b is available (her live setup), so the request goes
    # out and the provider answers with LM Studio's instruction-style
    # 400 — the phrasing the old regex missed.
    fake = _FakeNativeHTTP(
        native_available=False,
        legacy_models=["qwen2.5-3b-instruct", "qwen2.5-9b-instruct"],
        completions=[(400, 'Please load the model with key '
                           '"qwen2.5-3b-instruct" first.')],
    )
    c = _client(fake)
    res = c.generate_chat_completion(
        [{"role": "user", "content": "hi"}], complexity="fast")
    # Legacy listing claimed the 3b was 'loaded' (it is only downloaded);
    # the provider refused with LM Studio's instruction-style 400 — the
    # ladder must retry once with the loaded 9b, not simulate.
    assert res.get("simulated") is not True
    assert res.get("model_fallback", {}).get("used") == "qwen2.5-9b-instruct"
    assert fake.completion_payloads[-1]["model"] == "qwen2.5-9b-instruct"


# ── code lane: load on demand, eject afterwards ─────────────────────────────
def test_code_lane_loads_pinned_coder_on_demand_and_uses_it(monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "qwen2.5-coder-7b-instruct")
    monkeypatch.setattr(settings, "CODE_MODEL_AUTOSWAP", "1")
    monkeypatch.setattr(settings, "CODE_MODEL_EJECT_AFTER_S", 60)
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-9b-instruct", "state": "loaded"},
        {"id": "qwen2.5-coder-7b-instruct", "state": "not-loaded"},
    ])
    c = _client(fake)
    res = c.generate_chat_completion(
        [{"role": "user", "content": "write a function"}], complexity="code")
    assert fake.load_calls == [{"identifier": "qwen2.5-coder-7b-instruct",
                                "ttl": int(settings.CODE_MODEL_TTL_S)}]
    assert fake.completion_payloads[0]["model"] == "qwen2.5-coder-7b-instruct"
    assert res.get("simulated") is not True
    assert c._code_swapped_id == "qwen2.5-coder-7b-instruct"
    assert c._code_eject_timer is not None
    c._code_eject_timer.cancel()


def test_code_lane_ejects_after_the_quiet_window(monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL_EJECT_AFTER_S", 1)
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-coder-7b-instruct", "state": "loaded"},
    ])
    c = _client(fake)
    c._code_swapped_id = "qwen2.5-coder-7b-instruct"
    c._schedule_code_eject("qwen2.5-coder-7b-instruct")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not fake.unload_calls:
        time.sleep(0.05)
    assert fake.unload_calls == [{"identifier": "qwen2.5-coder-7b-instruct"}]
    assert c._code_swapped_id is None


def test_code_lane_never_ejects_a_coder_the_owner_loaded(monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "qwen2.5-coder-7b-instruct")
    monkeypatch.setattr(settings, "CODE_MODEL_AUTOSWAP", "1")
    monkeypatch.setattr(settings, "CODE_MODEL_EJECT_AFTER_S", 1)
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-coder-7b-instruct", "state": "loaded"},
    ])
    c = _client(fake)
    c.generate_chat_completion(
        [{"role": "user", "content": "code"}], complexity="code")
    assert fake.load_calls == []
    assert fake.completion_payloads[0]["model"] == "qwen2.5-coder-7b-instruct"
    time.sleep(1.6)
    assert fake.unload_calls == [], "her model, her VRAM, her call"
    assert c._code_eject_timer is None


def test_code_lane_auto_picks_the_biggest_downloaded_coder(monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "auto")
    monkeypatch.setattr(settings, "CODE_MODEL_AUTOSWAP", "1")
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-9b-instruct", "state": "loaded"},
        {"id": "qwen2.5-coder-7b-instruct", "state": "not-loaded"},
        {"id": "deepseek-coder-33b", "state": "not-loaded"},
    ])
    c = _client(fake)
    c._code_eject_timer and c._code_eject_timer.cancel()
    c.generate_chat_completion(
        [{"role": "user", "content": "code"}], complexity="code")
    assert fake.load_calls[0]["identifier"] == "deepseek-coder-33b"
    assert fake.completion_payloads[0]["model"] == "deepseek-coder-33b"
    c._code_eject_timer and c._code_eject_timer.cancel()


def test_code_lane_kill_switch_stands_down(monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "qwen2.5-coder-7b-instruct")
    monkeypatch.setattr(settings, "CODE_MODEL_AUTOSWAP", "0")
    monkeypatch.setattr(settings, "MAIN_MODEL", "qwen2.5-9b-instruct")
    fake = _FakeNativeHTTP(native_models=[
        {"id": "qwen2.5-9b-instruct", "state": "loaded"},
        {"id": "qwen2.5-coder-7b-instruct", "state": "not-loaded"},
    ])
    c = _client(fake)
    c.generate_chat_completion(
        [{"role": "user", "content": "code"}], complexity="code")
    assert fake.load_calls == []
    # pinned coder is not loaded -> the honest main-lane fallback
    assert fake.completion_payloads[0]["model"] == "qwen2.5-9b-instruct"


def test_code_lane_without_native_api_degrades_honestly(monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "qwen2.5-coder-7b-instruct")
    monkeypatch.setattr(settings, "CODE_MODEL_AUTOSWAP", "1")
    monkeypatch.setattr(settings, "MAIN_MODEL", "qwen2.5-9b-instruct")
    fake = _FakeNativeHTTP(
        native_available=False,
        legacy_models=["qwen2.5-9b-instruct"],
    )
    c = _client(fake)
    res = c.generate_chat_completion(
        [{"role": "user", "content": "code"}], complexity="code")
    assert fake.load_calls == []
    assert res.get("simulated") is not True
