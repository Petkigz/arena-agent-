"""Round 11 — the persistent embedding cache (owner go-ahead 2026-09-13).

Her live log: the embedding backend timed out (~6s) mid-cycle and the
machine degraded to fuzzy string matching. The in-memory caches die
with the process and only help within one run; this round persists
what the provider ACTUALLY computed, so a timeout or restart degrades
to REAL vectors instead of fuzzy guesses. Rescue is all-or-nothing and
never fabricates; hermetic mode (ARENA_LLM_DISABLED) is unchanged.
"""

import httpx
import pytest

from app.cognition import semantic_matcher as sm


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class StubClient:
    """Minimal httpx.Client stand-in: model discovery always works; the
    embeddings POST works or times out per fail_post."""

    fail_post = False
    vector = [0.1, 0.2, 0.3]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, timeout=None):
        return StubResponse({"data": [{"id": "nomic-embed-text"}]})

    def post(self, url, json=None, timeout=None):
        if StubClient.fail_post:
            raise httpx.TimeoutException("embedder timed out")
        inputs = (json or {}).get("input") or []
        return StubResponse(
            {"data": [{"embedding": list(StubClient.vector)} for _ in inputs]})


@pytest.fixture
def cache_env(monkeypatch, tmp_path):
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "embed.db"))
    database_module.db._init_db()
    # hermetic mode off: these tests simulate the provider at the HTTP
    # boundary — no real network, no real LM Studio.
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
    monkeypatch.setenv("ARENA_EMBEDDING_URL", "http://stub:9/v1")
    monkeypatch.setattr(sm, "_embed_model_cache", {})
    monkeypatch.setattr(sm, "_backend_state", {"current": None})
    monkeypatch.setattr(sm, "_embeddings_cache_model", None)
    StubClient.fail_post = False
    monkeypatch.setattr(sm.httpx, "Client", StubClient)
    return database_module.db


class TestPersistentCache:
    def test_success_persists_real_vectors(self, cache_env):
        out = sm.embed_texts(["open itunes on my pc"])
        assert out == [[0.1, 0.2, 0.3]]
        with cache_env._get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        assert n == 1

    def test_timeout_degrades_to_real_vectors_not_fuzzy(self, cache_env):
        sm.embed_texts(["open itunes on my pc"])  # seeds the cache
        import time as _time
        sm._backend_state["timeout_until"] = _time.monotonic() + 999
        out = sm.embed_texts(["open itunes on my pc"])
        assert out == [[0.1, 0.2, 0.3]]  # served from disk, provider never called

    def test_unknown_text_still_falls_back_honestly(self, cache_env):
        sm.embed_texts(["open itunes on my pc"])
        import time as _time
        sm._backend_state["timeout_until"] = _time.monotonic() + 999
        assert sm.embed_texts(["something never embedded"]) is None

    def test_rescue_is_all_or_nothing(self, cache_env):
        sm.embed_texts(["known text"])
        import time as _time
        sm._backend_state["timeout_until"] = _time.monotonic() + 999
        assert sm.embed_texts(["known text", "unknown text"]) is None

    def test_provider_exception_rescues_and_opens_cooldown(self, cache_env):
        sm.embed_texts(["open itunes on my pc"])  # seeds the cache
        StubClient.fail_post = True
        out = sm.embed_texts(["open itunes on my pc"])
        assert out == [[0.1, 0.2, 0.3]]
        assert sm._backend_state.get("timeout_until")  # cooldown opened

    def test_kill_switch(self, cache_env, monkeypatch):
        monkeypatch.setenv("ARENA_EMBED_CACHE", "0")
        sm.embed_texts(["open itunes on my pc"])
        with cache_env._get_connection() as conn:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE name='embedding_cache'"
            ).fetchone()
            n = 0
            if exists:
                n = conn.execute(
                    "SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        assert n == 0
        import time as _time
        sm._backend_state["timeout_until"] = _time.monotonic() + 999
        assert sm.embed_texts(["open itunes on my pc"]) is None

    def test_hermetic_mode_is_unchanged(self, cache_env, monkeypatch):
        # seed the cache live, then flip hermetic mode ON: the guard must
        # still short-circuit to the fuzzy matcher (test-suite contract)
        sm.embed_texts(["open itunes on my pc"])
        monkeypatch.setenv("ARENA_LLM_DISABLED", "1")
        assert sm.embed_texts(["open itunes on my pc"]) is None

    def test_case_and_whitespace_normalized_keys(self, cache_env):
        sm.embed_texts(["Open iTunes on my PC"])
        import time as _time
        sm._backend_state["timeout_until"] = _time.monotonic() + 999
        assert sm.embed_texts(["  open itunes on my pc  "]) == [[0.1, 0.2, 0.3]]

    def test_broken_db_fails_open(self, monkeypatch, tmp_path):
        import app.database as database_module
        monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
        monkeypatch.setattr(
            database_module.db, "db_path", str(tmp_path / "no_dir" / "x.db"))
        monkeypatch.setattr(sm, "_embed_model_cache", {})
        monkeypatch.setattr(sm, "_backend_state", {"current": None})
        monkeypatch.setattr(sm.httpx, "Client", StubClient)
        # provider still answers; the dead cache must not break embedding
        assert sm.embed_texts(["hello"]) == [[0.1, 0.2, 0.3]]


def test_wiring_is_in_place():
    import inspect

    src = inspect.getsource(sm)
    assert "_cache_put(texts, model, vectors)" in src
    assert src.count("return _cache_rescue(texts)") == 2  # cooldown + exception
    from app.config import settings
    assert hasattr(settings, "ARENA_EMBED_CACHE")
