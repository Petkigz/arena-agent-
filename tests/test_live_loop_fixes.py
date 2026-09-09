"""Owner live test 2026-09-08 (round 3) regression pins.

The owner's log showed four failures at once:

1. The parked-goal auto-recheck chained FOREVER: every recheck went through
   the FULL cognitive cycle (re-launching RICHST TV each time — six Electron
   instances fighting over one disk cache), parked its own trace as
   waiting_for_evidence, and got rechecked in turn with an ever-growing
   "(automatic re-check #1) (automatic re-check #1) ..." prefix.
   Root cause: the post-launch process probe watched payload key
   ``app_name``, the launch proposal payload carried no app key (the name
   was extracted from the sentence inside the launch branch), so the probe
   observed a process named 'app' and the goal never verified.
2. The honesty guard counted the execution layer's STRING action records as
   "nothing executed" and told the owner 'nothing ran' right after the
   machine had visibly launched the app.
3. The 14B model was requested while not loaded → LM Studio JIT-loaded it
   over the owner's loaded 9B models (LM Studio's /models lists downloaded
   models too; only /api/v0/models knows the real load state).
4. The UI did not open with the server (now: desktop client merged with the
   server lifecycle, browser fallback).
"""
import os


import pytest

from app.cognition.completion_honesty import enforce_completion_honesty


class _FakeProc:
    def __init__(self, name, pid=4321, exe=""):
        self.info = {"name": name, "pid": pid, "exe": exe}
        self.pid = pid


# ── 1a. The launch probe resolves the app from the owner's words ──────


def _world(tmp_path):
    from app.cognition.world_model import WorldModel

    return WorldModel(str(tmp_path / "world.db"))


def test_launch_probe_resolves_app_name_from_user_text(tmp_path, monkeypatch):
    """THE root-cause pin: payload has no app key; the probe must watch the
    app the owner actually named (extracted from their sentence), not 'app'."""
    from app.cognition import perception

    scans = {"n": 0}

    def fake_process_iter(attrs=None):
        scans["n"] += 1
        return iter([_FakeProc("RICHST TV.exe", exe="C:/apps/RICHST TV/RICHST TV.exe")])

    monkeypatch.setattr(perception.psutil, "process_iter", fake_process_iter)
    monkeypatch.setattr(perception.time, "sleep", lambda *_: None)

    wm = _world(tmp_path)
    ingested = []
    user_text = "hey theres an app on my pc called richst tv open it"
    perception.ObservationCollector._observe_open_application(
        {"original_goal": user_text}, wm, ingested, user_text=user_text
    )
    assert ingested, "a direct observation must be recorded"
    assert ingested[0].subject == "richst tv"
    assert ingested[0].value == "running"


def test_launch_probe_retries_until_process_appears(tmp_path, monkeypatch):
    """os.startfile returns before the process object exists; the probe
    must re-check briefly instead of recording a false not_running."""
    from app.cognition import perception

    calls = {"n": 0}

    def fake_process_iter(attrs=None):
        calls["n"] += 1
        if calls["n"] < 2:
            return iter([])
        return iter([_FakeProc("richst tv.exe")])

    monkeypatch.setattr(perception.psutil, "process_iter", fake_process_iter)
    monkeypatch.setattr(perception.time, "sleep", lambda *_: None)

    wm = _world(tmp_path)
    ingested = []
    perception.ObservationCollector._observe_open_application(
        {"app_name": "richst tv"}, wm, ingested, user_text=""
    )
    assert ingested[0].value == "running"
    assert calls["n"] >= 2, "the probe polled more than once"


def test_launch_probe_still_records_not_running_honestly(tmp_path, monkeypatch):
    from app.cognition import perception

    monkeypatch.setattr(
        perception.psutil, "process_iter", lambda attrs=None: iter([]))
    monkeypatch.setattr(perception.time, "sleep", lambda *_: None)

    wm = _world(tmp_path)
    ingested = []
    perception.ObservationCollector._observe_open_application(
        {"app_name": "ghost app"}, wm, ingested, user_text=""
    )
    assert ingested[0].value == "not_running"


def test_collect_passes_user_text_to_observers(tmp_path):
    """The signature wiring: collect_and_ingest_observations accepts and
    forwards user_text (the runtime call site relies on it)."""
    import inspect

    from app.cognition.perception import ObservationCollector

    sig = inspect.signature(ObservationCollector.collect_and_ingest_observations)
    assert "user_text" in sig.parameters


# ── 1b. The recheck loop is dead: no chains, evidence first ───────────


@pytest.fixture
def recheck_db(monkeypatch, tmp_path):
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "recheck.db"))
    database_module.db._init_db()
    # Reduced cognitive_traces (production DDL lives in trace.py against the
    # real DB); only the columns the recheck module touches are needed.
    with database_module.db._get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE cognitive_traces (
                trace_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_input TEXT NOT NULL,
                assistant_reply TEXT NOT NULL DEFAULT '',
                actions_json TEXT NOT NULL DEFAULT '[]',
                model_used TEXT NOT NULL DEFAULT 'fast',
                latency_ms REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                goal_verified INTEGER,
                goal_lifecycle_state TEXT,
                goal_park_reason TEXT
            )
            """
        )
        conn.commit()
    with database_module.db._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cognitive_traces
                (trace_id, session_id, user_input, assistant_reply,
                 actions_json, model_used, latency_ms, created_at,
                 goal_verified, goal_lifecycle_state)
            VALUES (?, 'desktop-chat', ?, '', '[]', 'fast', 10.0, ?, 0,
                    'waiting_for_evidence')
            """,
            ("t-original", "hey theres an app on my pc called richst tv open it",
             "2026-09-08T10:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO cognitive_traces
                (trace_id, session_id, user_input, assistant_reply,
                 actions_json, model_used, latency_ms, created_at,
                 goal_verified, goal_lifecycle_state)
            VALUES (?, 'desktop-chat', ?, '', '[]', 'fast', 10.0, ?, 0,
                    'waiting_for_evidence')
            """,
            ("t-recheck-artifact",
             "(automatic re-check #1) hey theres an app on my pc called "
             "richst tv open it",
             "2026-09-08T10:01:00+00:00"),
        )
        conn.commit()
    return database_module.db


def test_recheck_artifacts_are_never_rechecked(recheck_db):
    """A recheck's own parked trace must never be picked up again — that is
    what made the loop self-amplifying."""
    from app.cognition import parked_goal_recheck as pgr

    goals = pgr.collect_parked_goals(limit=5)
    ids = [g["trace_id"] for g in goals]
    assert "t-original" in ids
    assert "t-recheck-artifact" not in ids, (
        "recheck artifacts must be excluded from future rechecks"
    )


def test_recheck_markers_are_stripped_not_accumulated():
    from app.cognition.parked_goal_recheck import _strip_recheck_markers

    dirty = "(automatic re-check #1) (automatic re-check #1) hey theres an app"
    assert _strip_recheck_markers(dirty) == "hey theres an app"


def test_probe_close_verifies_without_reexecuting(recheck_db, monkeypatch):
    """Evidence FIRST: when the app is actually running, the goal closes as
    achieved via a process scan — no LLM cycle, no re-launch."""
    from app.cognition import parked_goal_recheck as pgr

    pgr.reset_for_tests()
    monkeypatch.setattr(pgr, "_MIN_AGE_S", 0.0)
    monkeypatch.setattr(pgr, "_RECHECK_GAP_S", 0.0)

    posted = []
    monkeypatch.setattr(pgr, "_post_to_conversation",
                        lambda conv, text: posted.append(text))

    proc = _FakeProc("RICHST TV.exe")
    from app.tools.app_inventory import SystemAppInventory

    monkeypatch.setattr(SystemAppInventory, "_find_app_process",
                        classmethod(lambda cls, q, ep="": proc))

    submitted = []

    def _no_submit(coro, loop):
        submitted.append(coro)
        coro.close()
        raise AssertionError("probe-close must not run a full LLM cycle")

    monkeypatch.setattr("asyncio.run_coroutine_threadsafe", _no_submit)

    class _Loop:
        def is_running(self):
            return True

    pgr.set_main_loop(_Loop())

    result = pgr.parked_goal_recheck_tick()
    assert result == {"trace_id": "t-original", "probe_closed": True}
    assert not submitted, "no cycle was submitted for a probe-verified goal"
    assert posted and "evidence only" in posted[0] and "running" in posted[0]

def test_probe_close_marks_trace_achieved(recheck_db, monkeypatch):
    from app.cognition import parked_goal_recheck as pgr

    pgr.reset_for_tests()
    monkeypatch.setattr(pgr, "_MIN_AGE_S", 0.0)
    monkeypatch.setattr(pgr, "_RECHECK_GAP_S", 0.0)
    monkeypatch.setattr(pgr, "_post_to_conversation", lambda conv, text: None)

    proc = _FakeProc("RICHST TV.exe")
    from app.tools.app_inventory import SystemAppInventory

    monkeypatch.setattr(SystemAppInventory, "_find_app_process",
                        classmethod(lambda cls, q, ep="": proc))
    monkeypatch.setattr("asyncio.run_coroutine_threadsafe",
                        lambda coro, loop: coro.close() or None)
    pgr.set_main_loop(type("L", (), {"is_running": lambda self: True})())

    pgr.parked_goal_recheck_tick()

    with recheck_db._get_connection() as conn:
        row = conn.execute(
            "SELECT goal_lifecycle_state, goal_verified FROM cognitive_traces "
            "WHERE trace_id = 't-original'").fetchone()
    assert row[0] == "achieved"
    assert row[1] == 1


def test_probe_miss_closes_without_reexecuting(recheck_db, monkeypatch):
    """Evidence says the app is NOT running → close honestly, NEVER
    re-execute. Owner round-4 verdict: rechecks must not re-run actions on
    their own (the surprise re-launch WAS the bug)."""
    from app.cognition import parked_goal_recheck as pgr

    pgr.reset_for_tests()
    monkeypatch.setattr(pgr, "_MIN_AGE_S", 0.0)
    monkeypatch.setattr(pgr, "_RECHECK_GAP_S", 0.0)

    from app.tools.app_inventory import SystemAppInventory

    monkeypatch.setattr(SystemAppInventory, "_find_app_process",
                        classmethod(lambda cls, q, ep="": None))

    calls = []
    posted = []
    monkeypatch.setattr(pgr, "_post_to_conversation",
                        lambda conv, text: posted.append(text))

    class _Future:
        def result(self, timeout=None):
            return None

    def _fake_run_coroutine_threadsafe(coro, loop):
        coro.close()
        calls.append(coro)
        return _Future()

    monkeypatch.setattr("asyncio.run_coroutine_threadsafe",
                        _fake_run_coroutine_threadsafe)
    pgr.set_main_loop(type("L", (), {"is_running": lambda self: True})())

    assert pgr.parked_goal_recheck_tick() is None
    assert not calls, "a probe miss must NOT submit a full LLM cycle"
    assert posted and "nothing was re-run" in posted[0]
    assert "not re-launching" in posted[0]
    # The goal is closed: a second tick does nothing at all.
    assert pgr.parked_goal_recheck_tick() is None
    assert len(calls) == 0


def test_launch_probe_returns_none_for_non_launch_goals():
    from app.cognition.parked_goal_recheck import _probe_launch_goal

    assert _probe_launch_goal("what is the capital of France") is None


# ── 2. The honesty guard reads the execution layer's string records ───


def test_honesty_guard_counts_string_executed_actions():
    result = {
        "assistant_reply": "I'm working on it now!",
        "executed_actions": ["Launched application 'Richst Tv' on your PC."],
        "user_text": "open richst tv",
        "goal_verified": False,
    }
    out = enforce_completion_honesty(result)
    assert "Straight answer" not in out["assistant_reply"], (
        "the machine DID run the launch — it must not be told 'nothing ran'"
    )
    assert "Honest status" in out["assistant_reply"]
    assert out.get("announcement_guard") == "unverified_outcome_surfaced"


def test_honesty_guard_silent_when_string_actions_verified():
    result = {
        "assistant_reply": "I'm launching it now.",
        "executed_actions": ["Launched application 'Richst Tv' on your PC."],
        "user_text": "open richst tv",
        "goal_verified": True,
    }
    out = enforce_completion_honesty(result)
    assert "announcement_guard" not in out
    assert "Honest status" not in out["assistant_reply"]


def test_string_action_filter_still_excludes_answer_formulation():
    from app.cognition.completion_honesty import real_executed_actions

    real = real_executed_actions([
        "formulate_answer completed",
        "Launched application 'X'.",
    ])
    assert len(real) == 1
    assert "Launched" in real[0]["detail"]


# ── 3. Model selection: only TRULY loaded models (no JIT auto-load) ───


def _native_client(models):
    """LocalLLMClient whose provider implements the native load-state API."""
    from app.llm import LocalLLMClient

    class _Resp:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status
            self.ok = status < 400

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    class _HTTP:
        def get(self, url, timeout=None):
            if "/api/v0/models" in url:
                return _Resp({"data": models})
            return _Resp({"data": [{"id": m["id"]} for m in models]})

        def close(self):
            pass

    client = LocalLLMClient(base_url="http://test/v1")
    client.client = _HTTP()
    return client


def test_native_endpoint_filters_to_truly_loaded(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
    """The exact live incident: 9B models LOADED, 14B only DOWNLOADED.
    Selection must see only the loaded ones — requesting the 14B is what
    made LM Studio JIT-load it over the owner's 9B."""
    client = _native_client([
        {"id": "qwen/qwen3-14b", "state": "not-loaded"},
        {"id": "qwen2.5-9b-instruct", "state": "loaded"},
        {"id": "qwen2.5-3b-instruct", "state": "loaded"},
    ])
    loaded = client.list_loaded_models(force=True)
    assert loaded == ["qwen2.5-3b-instruct", "qwen2.5-9b-instruct"]
    chosen = client.select_loaded_fallback("qwen2.5-14b-instruct", loaded)
    assert chosen == "qwen2.5-9b-instruct", (
        "the loaded 9B must serve the main route, never the unloaded 14B"
    )


def test_native_endpoint_reports_nothing_loaded_honestly(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
    client = _native_client([
        {"id": "qwen/qwen3-14b", "state": "not-loaded"},
    ])
    assert client.list_loaded_models(force=True) == []


def test_stateless_payload_falls_back_to_legacy_listing(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
    """Providers/proxies that mirror /models without a state field keep the
    legacy behavior (this also pins the existing test doubles' contract)."""
    from app.llm import LocalLLMClient

    class _Resp:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status
            self.ok = status < 400

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    class _HTTP:
        def get(self, url, timeout=None):
            # Both paths answer the SAME stateless listing.
            return _Resp({"data": [{"id": "qwen2.5-3b-instruct"}]})

        def close(self):
            pass

    client = LocalLLMClient(base_url="http://test/v1")
    client.client = _HTTP()
    assert client.list_loaded_models(force=True) == ["qwen2.5-3b-instruct"]


# ── 4. Launch honesty: already-running guard + verified process ───────


def test_find_app_process_matches_lnk_stem():
    from app.tools.app_inventory import SystemAppInventory

    proc = _FakeProc("RICHST TV.exe",
                     exe="C:/apps/RICHST TV/RICHST TV.exe")
    with patch_process_iter([proc]):
        found = SystemAppInventory._find_app_process(
            "richst tv", "C:/Users/PETAR/AppData/Roaming/Microsoft/Windows/"
            "Start Menu/Programs/RICHST TV.lnk")
    assert found is not None


def _patch_process_iter(monkeypatch, procs):
    from app.tools import app_inventory as inv

    monkeypatch.setattr(
        inv, "psutil",
        type("P", (), {"process_iter": staticmethod(lambda attrs=None: iter(procs)),
                       "NoSuchProcess": Exception,
                       "AccessDenied": Exception,
                       "ZombieProcess": Exception})(),
    )


def patch_process_iter(procs):
    """Context-manager variant for call sites that already use `with`."""
    from contextlib import contextmanager
    from app.tools import app_inventory as inv

    @contextmanager
    def _ctx():
        real = inv.psutil.process_iter
        inv.psutil.process_iter = lambda attrs=None: iter(procs)
        try:
            yield
        finally:
            inv.psutil.process_iter = real

    return _ctx()


def test_verify_app_running_immediate_hit(monkeypatch):
    from app.tools.app_inventory import SystemAppInventory

    _patch_process_iter(monkeypatch, [_FakeProc("richst tv.exe", pid=77)])
    out = SystemAppInventory.verify_app_running("richst tv", wait_seconds=0)
    assert out["process_verified"] is True
    assert out["pid"] == 77


def test_verify_app_running_honest_miss(monkeypatch):
    from app.tools.app_inventory import SystemAppInventory

    _patch_process_iter(monkeypatch, [])
    out = SystemAppInventory.verify_app_running(
        "richst tv", wait_seconds=0.05, poll_interval=0.02)
    assert out == {"process_verified": False}


def test_launch_any_app_already_running_spawns_nothing(monkeypatch):
    """The anti-pileup pin: six Electron instances were spawned by the loop.
    An already-open app must answer, not spawn a duplicate."""
    from app.tools import app_inventory as inv
    from app.tools.app_inventory import SystemAppInventory

    SystemAppInventory._cached_apps = [{
        "app_name": "richst tv",
        "executable_path": "C:/apps/RICHST TV.lnk",
        "source_category": "test",
    }]
    try:
        proc = _FakeProc("RICHST TV.exe", pid=99)
        _patch_process_iter(monkeypatch, [proc])

        spawned = []

        class _NP:
            def __init__(self, *a, **k):
                spawned.append(a)

        monkeypatch.setattr(inv.subprocess, "Popen", _NP)
        monkeypatch.setattr(inv, "os",
                            type("O", (), {"startfile": staticmethod(
                                lambda p: (_ for _ in ()).throw(
                                    AssertionError("must not spawn"))),
                                "path": __import__("os").path})())

        res = SystemAppInventory.launch_any_app("richst tv")
        assert res["success"] is True
        assert res["already_running"] is True
        assert res["process_verified"] is True
        assert res["pid"] == 99
        assert not spawned, "no process may be spawned for an open app"
    finally:
        SystemAppInventory._cached_apps = []


def test_launch_result_carries_process_verification(monkeypatch):
    """After a real spawn, the launch result must carry machine-observed
    verification (not just 'trust me')."""
    import tempfile

    from app.tools.app_inventory import SystemAppInventory

    script = "#!/usr/bin/env python3\nimport time; time.sleep(30)"

    with tempfile.NamedTemporaryFile("w", suffix="_sleep_helper.py",
                                     delete=False) as fh:
        fh.write(script)
        helper = fh.name
    os.chmod(helper, 0o755)
    SystemAppInventory._cached_apps = [{
        "app_name": "sleep helper",
        "executable_path": helper,
        "source_category": "test",
    }]
    try:
        # Process scan sees nothing (name never matches) → honest
        # process_verified False with pid from the Popen handle.
        _patch_process_iter(monkeypatch, [])
        res = SystemAppInventory.launch_any_app("sleep helper")
        assert res["success"] is True
        assert res["process_verified"] is False
        assert res["pid"], "the direct-spawn pid must still be reported"
        assert "NOT confirmed" in res["message"]
    finally:
        SystemAppInventory._cached_apps = []
        try:
            os.unlink(helper)
        except OSError:
            pass


# ── 5. UI opens with the server (desktop client merged lifecycle) ─────


def test_server_auto_open_launches_desktop_client_with_browser_fallback():
    """Source pin on the merged lifecycle: the server starts the native
    desktop client itself and falls back to the browser dashboard only
    when the desktop client dies immediately."""
    import pathlib

    src = pathlib.Path("app/server.py").read_text()
    assert '"-m", "desktop.main"' in src, (
        "the desktop client must be launched by the server at startup"
    )
    assert "CREATE_NEW_PROCESS_GROUP" in src
    assert "_webbrowser.open(url)" in src, (
        "browser fallback for machines without PySide6"
    )
    assert "ARENA_AUTO_OPEN_DASHBOARD" in src, "headless opt-out preserved"
