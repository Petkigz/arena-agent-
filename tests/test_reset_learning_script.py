"""scripts/reset_learning.py — the learning-reset utility must be safe:
dry-run by default, back up before deleting, keep user history, and refuse
to run against a live server."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reset_learning.py"


@pytest.fixture()
def data_dir(tmp_path):
    """A fabricated data dir with polluted learning rows + learning files."""
    db = tmp_path / "assistant.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE memories (id INTEGER PRIMARY KEY, text TEXT);
        INSERT INTO memories (text) VALUES ('lesson: launching always works');
        CREATE TABLE structured_lessons (id INTEGER PRIMARY KEY, lesson TEXT);
        INSERT INTO structured_lessons (lesson) VALUES ('x');
        CREATE TABLE planning_patterns (id INTEGER PRIMARY KEY, pattern TEXT);
        INSERT INTO planning_patterns (pattern) VALUES ('open_application');
        CREATE TABLE conversations (id INTEGER PRIMARY KEY, text TEXT);
        INSERT INTO conversations (text) VALUES ('real chat history');
        CREATE TABLE installed_apps (id INTEGER PRIMARY KEY, app_name TEXT);
        INSERT INTO installed_apps (app_name) VALUES ('notepad');
        """
    )
    conn.commit()
    conn.close()
    for name in ("memory_vectors.npz", "memory_vectors.meta.json",
                 "training_examples.db", "action_outcomes.db", "continual_learning.db"):
        (tmp_path / name).write_bytes(b"stale")
    return tmp_path


def _free_port():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run(data_dir, *flags):
    import os

    # Hermetic: the subprocess's HTTP probe targets a closed port on this
    # machine. monkeypatch cannot cross the process boundary, so without
    # this a REAL Arena server on port 8000 flipped these tests to
    # 'refused' (owner run 2026-09-09: three failures while her server
    # was up). The heartbeat check is hermetic by construction: nothing
    # writes server.heartbeat.json into the tmp data dir.
    env = {**os.environ,
           "ARENA_HOST": "127.0.0.1",
           "ARENA_PORT": str(_free_port())}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", str(data_dir), *flags],
        capture_output=True, text=True, timeout=60, env=env,
    )


def _count(data_dir, table):
    conn = sqlite3.connect(data_dir / "assistant.db")
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_dry_run_deletes_nothing(data_dir):
    result = _run(data_dir)
    assert result.returncode == 0, result.stderr
    assert "[DRY RUN" in result.stdout
    assert _count(data_dir, "memories") == 1
    assert (data_dir / "memory_vectors.npz").exists()
    assert not list((data_dir / "backups").glob("*")) if (data_dir / "backups").exists() else True


def test_apply_clears_learning_keeps_history(data_dir):
    result = _run(data_dir, "--apply")
    assert result.returncode == 0, result.stderr
    # Learning cleared.
    assert _count(data_dir, "memories") == 0
    assert _count(data_dir, "structured_lessons") == 0
    assert _count(data_dir, "planning_patterns") == 0
    # User history kept.
    assert _count(data_dir, "conversations") == 1
    assert _count(data_dir, "installed_apps") == 1
    # Learning files removed …
    assert not (data_dir / "memory_vectors.npz").exists()
    assert not (data_dir / "training_examples.db").exists()
    # … but backed up.
    backups = list((data_dir / "backups").rglob("assistant.db"))
    assert backups, "backup of assistant.db must exist"
    assert (backups[0].parent / "memory_vectors.npz").exists()


def test_full_wipe_removes_database(data_dir):
    result = _run(data_dir, "--apply", "--full")
    assert result.returncode == 0, result.stderr
    assert not (data_dir / "assistant.db").exists()
    assert list((data_dir / "backups").rglob("assistant.db")), "full wipe must still back up"


def test_missing_database_is_an_error(tmp_path):
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "not found" in result.stdout.lower()


def test_refuses_when_server_running(data_dir, monkeypatch):
    """The script must not race a live server that could rewrite rows."""
    import urllib.request

    class _FakeResponse:
        status = 200

        def read(self, n=-1):
            return b'{"status": "healthy", "service": "arena-backend"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=None):
        assert ":8000/health" in url
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    # Import the script as a module to test main() in-process.
    import importlib.util
    spec = importlib.util.spec_from_file_location("reset_learning", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rc = mod.main(["--data-dir", str(data_dir), "--apply"])
    assert rc == 2
    assert _count(data_dir, "memories") == 1, "nothing must be deleted when the server is up"


# ── Audit 2026-09-09: database-aware server protection ──────────────────────
#
# The fixed-port HTTP probe had two holes: an Arena server on any other
# port was invisible (the script could reset under an active writer), and
# any unrelated process on 8000 could block a legitimate reset. The
# server now beats a heartbeat file beside its database; the script
# refuses while it is fresh, and the probe requires Arena's own marker.


def _load_script_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("reset_learning", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unrelated_process_on_the_port_does_not_block(data_dir, monkeypatch):
    import urllib.request

    class _FakeResponse:
        status = 200

        def read(self, n=-1):
            return b"<html>some other application</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=None: _FakeResponse())
    assert _load_script_module()._server_is_running() is False


def test_refuses_when_heartbeat_fresh(data_dir):
    import json
    import time as _time

    (data_dir / "server.heartbeat.json").write_text(
        json.dumps({"pid": 4242, "ts": _time.time()}))
    result = _run(data_dir, "--apply")
    assert result.returncode == 2
    assert "heartbeat" in result.stdout.lower()
    assert _count(data_dir, "memories") == 1, "nothing deleted under a live server"


def test_stale_heartbeat_does_not_block(data_dir):
    import os
    import time as _time

    hb = data_dir / "server.heartbeat.json"
    hb.write_text("{}")
    old = _time.time() - 3600
    os.utime(hb, (old, old))
    result = _run(data_dir)
    assert result.returncode == 0, result.stdout


def test_server_heartbeat_writer_roundtrip(tmp_path):
    from app.utils import heartbeat

    db = tmp_path / "assistant.db"
    db.write_bytes(b"")
    path = heartbeat.write_server_heartbeat(str(db))
    assert path == tmp_path / "server.heartbeat.json"
    assert path.exists()
    # The freshness window must outlast several missed beats.
    assert heartbeat.HEARTBEAT_FRESH_S > 4 * heartbeat.HEARTBEAT_INTERVAL_S
    heartbeat.remove_server_heartbeat(str(db))
    assert not path.exists()


def test_server_heartbeat_kill_switch(tmp_path, monkeypatch):
    from app.utils import heartbeat

    monkeypatch.setenv("ARENA_SERVER_HEARTBEAT", "0")
    db = tmp_path / "assistant.db"
    db.write_bytes(b"")
    assert heartbeat.write_server_heartbeat(str(db)) is None
    assert not (tmp_path / "server.heartbeat.json").exists()


def test_lifespan_wires_the_heartbeat():
    """The seam: startup schedules the beat, shutdown removes the file."""
    import inspect

    import app.server as server_module

    src = inspect.getsource(server_module.lifespan)
    assert "write_server_heartbeat" in src
    assert "remove_server_heartbeat" in src
    assert "heartbeat_task.cancel()" in src
