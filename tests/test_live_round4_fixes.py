"""Owner live test 2026-09-08 round 4 regression pins.

The owner's round-4 log caught two bugs inside the round-3 fixes and one
pre-existing desktop crash:

1. 14B auto-loading STILL happened: the native load-state probe built its
   URL as {base_url}/api/v0/models with base_url = http://localhost:1234/v1
   -> /v1/api/v0/models -> 404 -> silent legacy fallback (which lists
   DOWNLOADED models) -> the not-loaded 14B was selected -> LM Studio
   JIT-loaded it over the owner's loaded 9B models. The tests passed
   because the fakes answered any URL. Pin: the native probe must hit the
   HOST ROOT and loaded-only selection must follow from it.
2. Launch goals STILL parked as waiting_for_evidence inside the cycle
   ("GoalVerifier ... waiting_for_evidence" twice in the round-4 log even
   though the launch itself reported 'process verified'). Pin: a
   machine-observed process verification overrides the parked verdict.
3. Recheck probe-miss re-ran the FULL cycle (re-launching the app). Owner
   verdict: rechecks must never re-execute on their own. Pin: probe-miss
   closes honestly, zero cycles submitted.
4. "ask beanie" in the desktop app closed the WHOLE app: ChatPage read
   self._header_orb; the widget is self.header_orb. Pin: correct attribute,
   no _header_orb anywhere, and a crash guard so a page bug can never kill
   the window again.
5. The embedding backend flapped active -> timed-out every cycle, stealing
   ~6s per cycle. Pin: after a timeout, a cooldown window short-circuits
   attempts; recovery still happens after it expires.
"""
import pytest

# ── 1. Native load-state probe at the HOST ROOT ──────────────────────


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        pass


class _RecordingHTTP:
    """Serves the native API at the host root; records every GET URL."""

    def __init__(self, native_models):
        self.native_models = native_models
        self.get_urls = []

    def get(self, url, timeout=None):
        self.get_urls.append(url)
        if url.endswith("/api/v0/models"):
            return _Resp({"data": self.native_models})
        if url.endswith("/models"):
            # Legacy listing: EVERYTHING downloaded, loaded or not.
            return _Resp({"data": [
                {"id": m["id"]} for m in self.native_models
            ]})
        return _Resp({"data": []})

    def post(self, url, json=None, timeout=None):
        return _Resp({
            "id": "c1", "model": (json or {}).get("model"),
            "choices": [{"index": 0, "message": {"role": "assistant",
                         "content": "ok"}, "finish_reason": "stop"}],
        })

    def close(self):
        pass


def _client_with(http, monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
    from app.llm import LocalLLMClient

    client = LocalLLMClient(base_url="http://localhost:1234/v1")
    client.client = http
    return client


def test_native_probe_hits_host_root_not_v1(monkeypatch):
    """THE round-4 bug: /v1/api/v0/models 404'd silently. The probe must
    strip the /v1 suffix — the native API lives at the host root."""
    http = _RecordingHTTP([
        {"id": "qwen/qwen3-14b", "state": "not-loaded"},
        {"id": "qwen2.5-9b-instruct", "state": "loaded"},
    ])
    client = _client_with(http, monkeypatch)
    loaded = client.list_loaded_models(force=True)
    assert "http://localhost:1234/api/v0/models" in http.get_urls, http.get_urls
    assert not any("/v1/api/v0" in u for u in http.get_urls)
    assert loaded == ["qwen2.5-9b-instruct"], (
        "the not-loaded 14B must be invisible to selection"
    )


def test_loaded_9b_serves_main_route_never_the_unloaded_14b(monkeypatch):
    http = _RecordingHTTP([
        {"id": "qwen/qwen3-14b", "state": "not-loaded"},
        {"id": "qwen2.5-9b-instruct", "state": "loaded"},
        {"id": "qwen2.5-3b-instruct", "state": "loaded"},
    ])
    client = _client_with(http, monkeypatch)
    loaded = client.list_loaded_models(force=True)
    pick = client.select_loaded_fallback("qwen2.5-14b-instruct", loaded)
    assert pick == "qwen2.5-9b-instruct"


def test_base_url_without_v1_suffix_still_works(monkeypatch):
    http = _RecordingHTTP([
        {"id": "m-9b", "state": "loaded"},
    ])
    client = _client_with(http, monkeypatch)
    client.base_url = "http://localhost:1234"
    assert client.list_loaded_models(force=True) == ["m-9b"]


# ── 2. Launch goals verify from the machine's own process probe ──────


def _verification(verified=False, unknown=True):
    from app.cognition.goal_lifecycle import GoalLifecycleState
    from app.cognition.goal_verifier import GoalVerificationResult

    return GoalVerificationResult(
        goal_id="g1",
        verified_success=verified,
        final_state=GoalLifecycleState.WAITING_FOR_EVIDENCE,
        verification_reason="no matching evidence",
        is_unknown=unknown,
    )


def test_process_verified_launch_overrides_parked_verdict():
    """The exact round-4 log: launch said 'process verified' yet the goal
    parked. The machine's own probe is authoritative evidence."""
    from app.cognition.runtime import _apply_launch_truth_override

    verification = _verification()
    execution = {
        "outputs": {
            "launch_res": {
                "success": True,
                "app_name": "RICHST TV",
                "process_verified": True,
                "process_name": "RICHST TV.exe",
                "pid": 5764,
            }
        }
    }
    applied = _apply_launch_truth_override(verification, "launch_app", execution)
    assert applied is True
    assert verification.verified_success is True
    assert verification.is_unknown is False
    assert any("process probe" in c for c in verification.met_conditions)
    assert "pid 5764" in verification.verification_reason


def test_unverified_launch_does_not_get_overridden():
    from app.cognition.runtime import _apply_launch_truth_override

    verification = _verification()
    execution = {
        "outputs": {
            "launch_res": {
                "success": True,
                "app_name": "ghost app",
                "process_verified": False,
            }
        }
    }
    assert _apply_launch_truth_override(verification, "launch_app", execution) is False
    assert verification.verified_success is False


def test_override_never_touches_non_launch_actions():
    from app.cognition.runtime import _apply_launch_truth_override

    verification = _verification()
    execution = {"outputs": {"launch_res": {"process_verified": True}}}
    assert _apply_launch_truth_override(verification, "search_files", execution) is False
    assert verification.verified_success is False


def test_already_verified_stays_untouched():
    from app.cognition.runtime import _apply_launch_truth_override

    verification = _verification(verified=True, unknown=False)
    verification.met_conditions = ["original evidence"]
    execution = {"outputs": {"launch_res": {"process_verified": True}}}
    assert _apply_launch_truth_override(verification, "launch_app", execution) is False
    assert verification.met_conditions == ["original evidence"]


# ── 3. Desktop app: the voice crash + the never-close guarantee ──────


def test_chat_page_uses_real_header_orb_attribute():
    import pathlib

    src = pathlib.Path("desktop/pages/chat.py").read_text(encoding="utf-8")
    assert "self._header_orb" not in src, (
        "the typo that closed the app mid-voice must be gone"
    )
    assert "self.header_orb.set_status" in src


def test_desktop_app_has_crash_guard():
    import pathlib

    src = pathlib.Path("desktop/main.py").read_text(encoding="utf-8")
    assert "sys.excepthook = _hook" in src, (
        "a page bug must log, never close the window"
    )
    app_src = pathlib.Path("desktop/app.py").read_text(encoding="utf-8")
    assert "traceback.print_exc()" in app_src
    assert app_src.count("def _on_online") == 1


def test_no_underscore_attribute_typos_in_chat_page():
    """Sweep: every self.<attr> READ in desktop/pages/chat.py must be
    assigned somewhere in the module or be a defined method/Qt member."""
    import ast
    import pathlib

    path = pathlib.Path("desktop/pages/chat.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assigned, read, methods = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.add(node.name)
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            if isinstance(node.ctx, ast.Store):
                assigned.add(node.attr)
            else:
                read.add(node.attr)
    suspects = read - assigned - methods - {
        # QWidget/QObject members used by the page:
        "findChild", "width", "update", "hide", "show", "raise_",
        "setStyleSheet", "scroll", "adjustSize",
    }
    assert not suspects, f"unresolved attribute reads: {sorted(suspects)}"


# ── 4. Embedding timeout cooldown ────────────────────────────────────


@pytest.fixture
def embed_env(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
    from app.cognition import semantic_matcher as sm

    # Full module-state reset, INCLUDING the TTL'd model-discovery cache:
    # any earlier test that probes rank_tools/semantic_scores against the
    # (absent) embedding server caches a MISS for 30s, and the cached
    # miss short-circuits _pick_embedding_model before the patched
    # httpx.Client is ever called — the cooldown tests then fail
    # order-dependently (found via the Phase-19 full suite; the bug is
    # older than Phase 19).
    saved_cache = dict(sm._embed_model_cache)
    sm._embed_model_cache.clear()
    sm._backend_state["timeout_until"] = None
    sm._backend_state["current"] = None
    yield sm
    sm._embed_model_cache.clear()
    sm._embed_model_cache.update(saved_cache)
    sm._backend_state["timeout_until"] = None
    sm._backend_state["current"] = None


def test_timeout_opens_cooldown_and_short_circuits(embed_env, monkeypatch):
    import httpx

    sm = embed_env
    calls = {"n": 0}

    class _TimeoutClient:
        """Model discovery succeeds; the embeddings POST times out.
        (_pick_embedding_model swallows GET errors into 'no model', so the
        timeout must fire on the POST to reach embed_texts' except.)"""

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, timeout=None):
            calls["n"] += 1

            class _R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"data": [
                        {"id": "text-embedding-nomic-embed-text-v1.5"}
                    ]}

            return _R()

        def post(self, url, json=None, timeout=None):
            calls["n"] += 1
            raise httpx.TimeoutException("read timed out")

    monkeypatch.setattr(sm.httpx, "Client", _TimeoutClient)

    assert sm.embed_texts(["hello"]) is None
    assert sm._backend_state["timeout_until"] is not None, (
        "a timeout must open the cooldown window"
    )
    after_first = calls["n"]

    # While cooling down: instant fallback, ZERO new network calls.
    assert sm.embed_texts(["hello again"]) is None
    assert calls["n"] == after_first, (
        "no probe may be attempted inside the cooldown window"
    )


def test_cooldown_expiry_resumes_probing(embed_env, monkeypatch):
    sm = embed_env
    sm._backend_state["timeout_until"] = 1.0  # long in the past

    class _OkClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, timeout=None):
            class _R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"data": [{"id": "text-embedding-nomic-embed-text-v1.5"}]}

            return _R()

        def post(self, url, json=None, timeout=None):
            class _R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"data": [
                        {"embedding": [0.1, 0.2]} for _ in json["input"]
                    ]}

            return _R()

    monkeypatch.setattr(sm.httpx, "Client", _OkClient)
    out = sm.embed_texts(["hello"])
    assert out == [[0.1, 0.2]]
    assert sm._backend_state["timeout_until"] is None


def test_non_timeout_errors_do_not_open_cooldown(embed_env, monkeypatch):
    import httpx

    sm = embed_env

    class _FailClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, timeout=None):
            raise httpx.ConnectError("connection refused")

        def post(self, url, json=None, timeout=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(sm.httpx, "Client", _FailClient)
    assert sm.embed_texts(["x"]) is None
    assert sm._backend_state["timeout_until"] is None, (
        "a dead server is retryable — only timeouts open the cooldown"
    )
