"""P1 (live 2026-09-01, owner review): requested model -> is it actually
loaded? -> use it / select a known loaded fallback — NEVER straight to a
400 and a simulated reply while perfectly good models sit loaded.

Live incident: MAIN_MODEL=qwen2.5-9b-instruct was not loaded (the owner
had qwen3.5-9b and others loaded); every main-route call returned HTTP
400 and Arena silently degraded real tasks to simulation. The fallback
must be intentional and observable: a WARNING that names both models, a
model_fallback tag on the response, and simulation only as the last
resort (server unreachable / nothing loaded).
"""

import httpx
import pytest

from app.config import settings
from app.llm import LocalLLMClient

# The owner's real loaded-model list from the 2026-09-01 live run.
OWNER_LOADED = [
    "qwen2.5-3b-instruct", "qwen3.5-9b", "qwen/qwen3-14b",
    "qwen2.5-vl-3b-instruct", "qwen2.5-coder-7b-instruct",
    "omnicoder-qwen3.5-9b-claude-4.6-opus-uncensored-v2",
]


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code}' for url "
                f"'http://test/v1/chat/completions'",
                request=httpx.Request("POST", "http://test/v1/chat/completions"),
                response=httpx.Response(self.status_code, text=self.text),
            )

    def json(self):
        return self._json


def _ok_completion(model="any"):
    return {"id": "chat-1", "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"completion_tokens": 2}}


class _FakeHTTP:
    """Stands in for the httpx.Client on a LocalLLMClient.

    models_sequence: popped per GET /models — each entry is either a list
    of loaded model ids or None (server unreachable). post_results: popped
    per POST /chat/completions — each entry is a _FakeResp (or raises if
    it is an Exception instance).
    """

    def __init__(self, models_sequence=None, post_results=None):
        self.models_sequence = list(models_sequence or [])
        self.post_results = list(post_results or [])
        self.get_calls = 0
        self.post_models = []
        self.is_closed = False

    def get(self, url, timeout=None):
        self.get_calls += 1
        if not self.models_sequence:
            raise httpx.ConnectError("connection refused")
        item = self.models_sequence.pop(0)
        if item is None:
            raise httpx.ConnectError("connection refused")
        return _FakeResp(200, {"data": [{"id": m} for m in item]})

    def close(self):
        self.is_closed = True

    def post(self, url, json=None, timeout=None):
        self.post_models.append((json or {}).get("model"))
        if self.post_results:
            item = self.post_results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return _FakeResp(200, _ok_completion())


def _client_with(fake):
    client = LocalLLMClient(base_url="http://test/v1")
    real_client = client.client
    client.client = fake
    client._real_httpx = real_client  # keep a ref for teardown
    return client


@pytest.fixture(autouse=True)
def _pinned_models(monkeypatch):
    monkeypatch.setattr(settings, "MAIN_MODEL", "qwen2.5-9b-instruct")
    monkeypatch.setattr(settings, "FAST_MODEL", "qwen2.5-3b-instruct")


@pytest.fixture(autouse=True)
def _loud_app_logger():
    """app_logger does not propagate (it owns its handlers); let caplog
    see its WARNINGs for the duration of the test."""
    from app.utils.logger import app_logger
    old = app_logger.propagate
    app_logger.propagate = True
    yield
    app_logger.propagate = old


def test_requested_model_loaded_is_used_unchanged(caplog):
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED + ["qwen2.5-9b-instruct"]])
    client = _client_with(fake)
    with caplog.at_level("WARNING"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen2.5-9b-instruct"]
    assert "model_fallback" not in result
    assert result["choices"][0]["message"]["content"] == "ok"
    assert "not loaded" not in caplog.text


def test_unloaded_main_model_falls_back_to_closest_loaded(caplog):
    """The exact live incident: qwen2.5-9b-instruct is NOT loaded while
    qwen3.5-9b (and others) are — the request must go to a loaded model,
    loudly, not to a 400 and a simulated reply."""
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED])
    client = _client_with(fake)
    with caplog.at_level("WARNING"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen3.5-9b"]
    assert result["model_fallback"]["requested"] == "qwen2.5-9b-instruct"
    assert result["model_fallback"]["used"] == "qwen3.5-9b"
    assert "qwen2.5-9b-instruct" in caplog.text
    assert "qwen3.5-9b" in caplog.text
    assert "not loaded" in caplog.text


def test_fallback_selection_prefers_same_family_same_size():
    client = LocalLLMClient(base_url="http://test/v1")
    chosen = client.select_loaded_fallback("qwen2.5-9b-instruct", OWNER_LOADED)
    assert chosen == "qwen3.5-9b"


def test_fallback_selection_none_when_nothing_else_loaded():
    client = LocalLLMClient(base_url="http://test/v1")
    assert client.select_loaded_fallback(
        "qwen2.5-9b-instruct", ["qwen2.5-9b-instruct"]) is None
    assert client.select_loaded_fallback("qwen2.5-9b-instruct", []) is None


def test_stale_cache_recovers_via_observable_retry(caplog):
    """Cache said the model was loaded; the provider disagrees (400
    model-not-found). One forced re-probe and a single retry with a
    loaded fallback — then a REAL completion, not simulation."""
    fake = _FakeHTTP(
        models_sequence=[
            ["qwen2.5-9b-instruct"],   # stale cache content
            OWNER_LOADED,              # fresh probe after the 400
        ],
        post_results=[
            _FakeResp(400, text="Error: model qwen2.5-9b-instruct not found",
                      json_data={"error": "model not found"}),
            _FakeResp(200, _ok_completion("qwen3.5-9b")),
        ],
    )
    client = _client_with(fake)
    client.list_loaded_models()  # seed the (stale) cache
    with caplog.at_level("WARNING"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen2.5-9b-instruct", "qwen3.5-9b"]
    assert result["choices"][0]["message"]["content"] == "ok"
    assert result["model_fallback"]["used"] == "qwen3.5-9b"
    assert "retry" in caplog.text.lower()


def test_non_model_400_does_not_retry():
    """A 400 that is NOT about the model (e.g. context overflow) must not
    trigger the model fallback retry — one request, then simulation."""
    fake = _FakeHTTP(
        models_sequence=[["qwen2.5-9b-instruct", "qwen3.5-9b"]],
        post_results=[
            _FakeResp(400, text="Error: maximum context length is 8192 tokens",
                      json_data={"error": "context length"}),
        ],
    )
    client = _client_with(fake)
    result = client.generate_chat_completion(
        [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen2.5-9b-instruct"]  # exactly one attempt
    assert result["simulated"] is True


def test_unreachable_server_still_simulates():
    """Server down entirely: no loaded models to select — simulation is
    the honest last resort (unchanged behavior)."""
    fake = _FakeHTTP(models_sequence=[None],
                     post_results=[httpx.ConnectError("connection refused")])
    client = _client_with(fake)
    result = client.generate_chat_completion(
        [{"role": "user", "content": "hi"}], complexity="main")
    assert result["simulated"] is True
    assert result["model"] == "qwen2.5-9b-instruct"


def test_fallback_events_are_recorded_for_inspection():
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED])
    client = _client_with(fake)
    client.generate_chat_completion(
        [{"role": "user", "content": "hi"}], complexity="main")
    assert len(client.fallback_events) == 1
    assert client.fallback_events[0]["used"] == "qwen3.5-9b"
