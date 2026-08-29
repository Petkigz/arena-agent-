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


def _run(data_dir, *flags):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", str(data_dir), *flags],
        capture_output=True, text=True, timeout=60,
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
