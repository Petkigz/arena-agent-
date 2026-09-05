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


@pytest.fixture(autouse=True)
def _real_llm_transport(monkeypatch):
    """These tests exercise the REAL transport/embedding internals
    (fallback ladder, retry, embedding backends) — remove the suite's
    hermeticity guard (tests/conftest.py sets ARENA_LLM_DISABLED) so the
    mocked transports are actually reached."""
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)


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


def test_unloaded_main_model_falls_back_to_best_loaded(caplog):
    """The exact live incident: qwen2.5-9b-instruct is NOT loaded while
    others are — the request must go to a loaded model, loudly, not to a
    400 and a simulated reply. Since 2026-09-05 the pick is ROLE-SCORED
    (best loaded model for the main route), not closest-to-the-stale-id:
    with the owner's real loaded list that is qwen/qwen3-14b (14B
    general), not qwen3.5-9b (which only won on closeness to the
    configured id)."""
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED])
    client = _client_with(fake)
    with caplog.at_level("WARNING"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen/qwen3-14b"]
    assert result["model_fallback"]["requested"] == "qwen2.5-9b-instruct"
    assert result["model_fallback"]["used"] == "qwen/qwen3-14b"
    assert "qwen2.5-9b-instruct" in caplog.text
    assert "qwen/qwen3-14b" in caplog.text
    assert "not loaded" in caplog.text
    assert "auto" in caplog.text  # the escape hatch is named in the warning


def test_fallback_selection_is_role_scored_not_id_closeness():
    """Policy change (owner request 2026-09-05): a stale configured id
    must not shape the pick. The old closeness heuristic preferred
    qwen3.5-9b (same family, same size as the configured
    qwen2.5-9b-instruct) over the better qwen/qwen3-14b. Role scoring
    ranks by what the main route needs: size, chat tuning, no
    specialism penalties."""
    client = LocalLLMClient(base_url="http://test/v1")
    chosen = client.select_loaded_fallback("qwen2.5-9b-instruct", OWNER_LOADED)
    assert chosen == "qwen/qwen3-14b"


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
            _FakeResp(200, _ok_completion("qwen/qwen3-14b")),
        ],
    )
    client = _client_with(fake)
    client.list_loaded_models()  # seed the (stale) cache
    with caplog.at_level("WARNING"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    # Role-scored pick since 2026-09-05: the retry goes to the best
    # loaded main model, not the closest id.
    assert fake.post_models == ["qwen2.5-9b-instruct", "qwen/qwen3-14b"]
    assert result["choices"][0]["message"]["content"] == "ok"
    assert result["model_fallback"]["used"] == "qwen/qwen3-14b"
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
    assert client.fallback_events[0]["used"] == "qwen/qwen3-14b"


# ── role-scored selection + auto mode (owner request 2026-09-05) ───────
# "Scan the loaded models and use the best one" — with a criterion the
# owner can inspect: parameter count (anchor), chat tuning, specialism
# penalties. Fine-tunes ('uncensored', merges) are NEVER excluded for
# their tuning; only non-chat tools (embedders, rerankers, speech) are
# passed over for chat routes. MAIN_MODEL/FAST_MODEL=auto makes the scan
# explicit; an exact loaded id always wins; a drifting id (vendor
# prefix, .gguf) resolves silently to the same model.

def test_auto_main_selects_the_largest_general_model():
    client = LocalLLMClient(base_url="http://test/v1")
    chosen = client.select_loaded_fallback("auto", OWNER_LOADED, role="main")
    # 14B general beats the 9b merge and the coder/vl specialists
    assert chosen == "qwen/qwen3-14b"


def test_auto_fast_selects_a_small_instruct_model():
    client = LocalLLMClient(base_url="http://test/v1")
    chosen = client.select_loaded_fallback("auto", OWNER_LOADED, role="fast")
    assert chosen == "qwen2.5-3b-instruct"


def test_main_model_auto_end_to_end(caplog):
    """MAIN_MODEL=auto: the request goes to the role-scored best loaded
    model, logged as a POLICY decision (INFO), not a failure."""
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED] * 4)
    client = _client_with(fake)
    settings.MAIN_MODEL = "auto"  # undone by the autouse _pinned_models fixture
    with caplog.at_level("INFO"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen/qwen3-14b"]
    assert "model_fallback" not in result  # auto is policy, not fallback
    assert any(e["requested"] == "auto" and e["used"] == "qwen/qwen3-14b"
               for e in client.fallback_events)
    assert "Model auto-selection (main route)" in caplog.text
    assert "not loaded" not in caplog.text


def test_configured_id_drift_resolves_to_the_same_model_silently(caplog):
    """MAIN_MODEL=qwen3-14b while the provider lists 'qwen/qwen3-14b'
    (vendor prefix drift): the PROVIDER's id is used, silently — the
    same model, so it is not a fallback and must not warn."""
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED] * 4)
    client = _client_with(fake)
    settings.MAIN_MODEL = "qwen3-14b"
    with caplog.at_level("INFO"):
        result = client.generate_chat_completion(
            [{"role": "user", "content": "hi"}], complexity="main")
    assert fake.post_models == ["qwen/qwen3-14b"]
    assert "model_fallback" not in result
    assert client.fallback_events == []
    assert "not loaded" not in caplog.text


def test_uncensored_finetune_is_never_excluded():
    """The owner runs uncensored/edited fine-tunes and must be able to
    use them without the system rejecting them: a fine-tune competes on
    the same scale, and when it is the best (or only) chat model loaded
    it IS the main model."""
    client = LocalLLMClient(base_url="http://test/v1")
    only_ft = ["omnicoder-qwen3.5-9b-claude-4.6-opus-uncensored-v2"]
    assert client.select_loaded_fallback(
        "auto", only_ft, role="main") == only_ft[0]
    # and it loses only to a strictly better general model, never to a
    # tag filter
    both = only_ft + ["qwen/qwen3-14b"]
    assert client.select_loaded_fallback(
        "auto", both, role="main") == "qwen/qwen3-14b"


def test_non_chat_models_are_not_selected_for_chat_routes():
    """Embedders/rerankers/speech models are the wrong tool for a chat
    route — a role judgment, not a quality judgment; with nothing else
    loaded the client must return None (the caller then fails honestly
    rather than routing chat to an embedder)."""
    client = LocalLLMClient(base_url="http://test/v1")
    non_chat = ["bge-m3-embedding", "whisper-large-v3", "bge-reranker-v2"]
    for role in ("main", "fast"):
        assert client.select_loaded_fallback(
            "auto", non_chat, role=role) is None


def test_selection_is_deterministic_on_ties():
    client = LocalLLMClient(base_url="http://test/v1")
    tied = ["mistral-7b-instruct", "llama-7b-instruct"]
    assert client.select_loaded_fallback(
        "auto", tied, role="main") == "llama-7b-instruct"


def test_specialists_rank_below_general_models_of_the_same_size():
    client = LocalLLMClient(base_url="http://test/v1")
    s = LocalLLMClient._role_score
    assert s("qwen2.5-3b-instruct", "main") > s("qwen2.5-vl-3b-instruct", "main")
    assert s("qwen3.5-9b", "main") > s("qwen2.5-coder-7b-instruct", "main")


def test_stale_config_warning_is_loud_once_then_debug(caplog):
    """The same stale-config fallback fired its WARNING before every
    main-route call (6x per live diag run). The first occurrence stays
    loud; repeats drop to DEBUG — the diag env row keeps the permanent
    record, and every fallback still lands in fallback_events."""
    import logging
    fake = _FakeHTTP(models_sequence=[OWNER_LOADED] * 6)
    client = _client_with(fake)
    with caplog.at_level("DEBUG", logger="app"):
        for _ in range(3):
            client.generate_chat_completion(
                [{"role": "user", "content": "hi"}], complexity="main")
    warnings_ = [r for r in caplog.records
                 if r.levelno == logging.WARNING and "is not loaded" in r.message]
    assert len(warnings_) == 1  # once loud
    assert len(client.fallback_events) == 3  # every decision still recorded
    assert fake.post_models == ["qwen/qwen3-14b"] * 3


def test_auto_selection_generalizes_to_unseen_vendor_lists():
    """No qwen anywhere: role scoring must still pick sensibly on a
    vendor list it has never seen - largest general instruct for main,
    smallest instruct for fast, embedder passed over."""
    client = LocalLLMClient(base_url="http://test/v1")
    unseen = ["gemma-2-9b-it", "mistral-7b-instruct-v0.3",
              "llama-3.1-8b-instruct", "nomic-embed-text"]
    assert client.select_loaded_fallback(
        "auto", unseen, role="main") == "llama-3.1-8b-instruct"
    assert client.select_loaded_fallback(
        "auto", unseen, role="fast") == "mistral-7b-instruct-v0.3"
