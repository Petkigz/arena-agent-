"""ProcessManager tests — list/inspect/kill, deterministic (psutil) and guarded
so the agent can never kill itself or a protected system process."""

import os
import subprocess
import sys
import time

from app.tools.process_manager import ProcessManager


def test_list_processes_includes_current():
    res = ProcessManager.list_processes(limit=500)
    assert res["success"] is True
    pids = [p["pid"] for p in res["processes"]]
    assert os.getpid() in pids


def test_list_processes_filter():
    res = ProcessManager.list_processes(filter="python", limit=50)
    assert res["success"] is True
    # The current test runner is a python process and should match.
    pids = [p["pid"] for p in res["processes"]]
    assert os.getpid() in pids


def test_list_processes_invalid_sort():
    assert ProcessManager.list_processes(sort_by="bogus")["success"] is False


def test_get_current_process():
    res = ProcessManager.get_process(os.getpid())
    assert res["success"] is True
    assert res["pid"] == os.getpid()
    assert res["name"]


def test_get_process_invalid_pid():
    assert ProcessManager.get_process("notanint")["success"] is False
    assert ProcessManager.get_process(0)["success"] is False


def test_get_process_missing():
    assert ProcessManager.get_process(99999999)["success"] is False


def test_kill_guards_self():
    res = ProcessManager.kill_process(os.getpid())
    assert res["success"] is False
    assert "itself" in res["error"]


def test_kill_guards_system_pids():
    assert ProcessManager.kill_process(1)["success"] is False
    assert ProcessManager.kill_process(0)["success"] is False


def test_kill_missing_process():
    assert ProcessManager.kill_process(99999999)["success"] is False


def test_kill_real_process():
    # sys.executable, not the Unix `sleep` binary — the owner runs the
    # suite on Windows where `sleep` does not exist (FileNotFoundError,
    # owner run 2026-09-02).
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        res = ProcessManager.kill_process(proc.pid)
        assert res["success"] is True
        time.sleep(0.2)
        assert proc.poll() is not None  # terminated
    finally:
        if proc.poll() is None:
            proc.kill()


def test_restart_guards_self():
    assert ProcessManager.restart_process(os.getpid())["success"] is False


def test_restart_missing_process():
    assert ProcessManager.restart_process(99999999)["success"] is False
