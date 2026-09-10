"""Shutdown-cooperation checks across the supported in-repo runners (8.9).

Queue item 5 of the execution status: "Test the service, desktop launcher,
scheduler, and any supported process supervisor separately." The child-process
kill-switch path is covered by tests/test_shutdown_integration.py; this module
covers the remaining deterministic paths:

- the scheduler that owns the hourly autonomous cycle must STOP when the
  unified server's lifespan shuts down (no surviving background thread, no
  mid-job death at interpreter exit);
- the desktop launcher (system tray) must terminate its child server and exit
  its icon cleanly, including when the child is already gone.

Host-scale runners (real supervisors, real desktop sessions) stay explicitly
unverified here; nothing in this module upgrades 8.9 beyond its recorded
conditional status.
"""

import asyncio
import subprocess
import sys

import pytest


# ── scheduler cooperation ────────────────────────────────────────────────────

def test_scheduler_shutdown_without_a_scheduler_is_a_safe_noop(monkeypatch):
    from app.scheduler.scheduler import ProactiveScheduler

    monkeypatch.setattr(ProactiveScheduler, "_scheduler", None)
    assert ProactiveScheduler.shutdown() is False
    # A shutdown path must never lazily START a scheduler thread.
    assert ProactiveScheduler._scheduler is None


def test_scheduler_shutdown_stops_recurring_jobs_and_resets():
    from app.scheduler.scheduler import ProactiveScheduler

    def _no_op() -> None:  # pragma: no cover — never executed
        pass

    assert ProactiveScheduler.schedule_recurring(
        "shutdown_coop_probe", _no_op, interval_seconds=3600) is True
    running = ProactiveScheduler._scheduler
    assert running is not None
    assert any(j.id == "shutdown_coop_probe" for j in running.get_jobs())

    assert ProactiveScheduler.shutdown(wait=False) is True
    assert ProactiveScheduler._scheduler is None

    # A later get_scheduler() starts a FRESH scheduler with no stale jobs,
    # and the probe job must not have survived the shutdown.
    fresh = ProactiveScheduler.get_scheduler()
    try:
        assert fresh is not running
        assert not any(j.id == "shutdown_coop_probe" for j in fresh.get_jobs())
    finally:
        ProactiveScheduler.shutdown(wait=False)


def test_unified_lifespan_shutdown_stops_the_autonomous_cycle_scheduler(monkeypatch):
    """The real unified server lifespan must stop the job scheduler on exit.

    This is the exact cooperation contract of queue item 5: entering the
    lifespan schedules the autonomous cycle; exiting it must leave NO
    scheduler thread behind.

    Phase 0 (owner plan 2026-09-10): the AUTONOMY_MODE default is now
    'off', so the test ENABLES supervised mode explicitly — the contract
    under test is the shutdown cooperation when jobs are actually
    scheduled, not the default posture (pinned separately in
    tests/test_startup_readiness.py::TestPhase0Defaults).
    """
    import app.server as server
    from app.config import settings as _settings
    from app.scheduler.scheduler import ProactiveScheduler

    monkeypatch.setattr(_settings, "AUTONOMY_MODE", "supervised")

    async def _run() -> None:
        lifecycle = server.lifespan(server.app)
        await lifecycle.__aenter__()
        try:
            # The lifespan scheduled its recurring work through the shared
            # scheduler (supervised mode enabled above).
            assert ProactiveScheduler._scheduler is not None
        finally:
            await lifecycle.__aexit__(None, None, None)

    asyncio.run(_run())
    assert ProactiveScheduler._scheduler is None


# ── desktop launcher (system tray) cooperation ───────────────────────────────

def _import_desktop_tray():
    """Import the tray module, skipping cleanly where the tray stack cannot
    initialize (pystray's X11 backend needs a display; the same environment
    boundary the Qt widget tests document). The cleanup logic under test is
    display-free, but its import chain is not."""
    try:
        import app.desktop_tray as tray
        return tray
    except Exception as exc:  # noqa: BLE001 — display-less sandbox
        pytest.skip(f"tray backend unavailable in this environment: {exc}")


def _fake_process(terminate_raises: bool = False):
    class _FakeProcess:
        def __init__(self) -> None:
            self.calls: list = []

        def terminate(self) -> None:
            self.calls.append("terminate")
            if terminate_raises:
                raise RuntimeError("process already exited")

        def wait(self, timeout=None):
            self.calls.append(f"wait:{timeout}")
            return 0

    return _FakeProcess()


def _fake_icon():
    class _FakeIcon:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    return _FakeIcon()


def test_tray_cleanup_terminates_child_server_then_stops_icon(monkeypatch):
    tray = _import_desktop_tray()

    process = _fake_process()
    icon = _fake_icon()
    monkeypatch.setattr(tray, "SERVER_PROCESS", process)

    tray.cleanup_and_exit(icon)

    assert process.calls == ["terminate", "wait:3"]
    assert icon.stopped is True


def test_tray_cleanup_survives_an_already_dead_child(monkeypatch):
    tray = _import_desktop_tray()

    process = _fake_process(terminate_raises=True)
    icon = _fake_icon()
    monkeypatch.setattr(tray, "SERVER_PROCESS", process)

    # A dead child must not prevent the launcher itself from exiting.
    tray.cleanup_and_exit(icon)

    assert icon.stopped is True


def test_tray_cleanup_with_no_child_process_still_stops_icon(monkeypatch):
    tray = _import_desktop_tray()

    icon = _fake_icon()
    monkeypatch.setattr(tray, "SERVER_PROCESS", None)

    tray.cleanup_and_exit(icon)

    assert icon.stopped is True


# ── desktop launcher: process-level evidence ─────────────────────────────────

def test_tray_cleanup_terminates_a_real_child_server_process(monkeypatch):
    """The fake-process contracts above pin call ORDER; this test proves a
    REAL child server process actually dies — the launcher path's counterpart
    to the service path's child-process integration test. Deterministic and
    headless-safe: only the tray icon is a stub."""
    tray = _import_desktop_tray()

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert child.poll() is None  # a real, running child
        monkeypatch.setattr(tray, "SERVER_PROCESS", child)
        icon = _fake_icon()

        tray.cleanup_and_exit(icon)

        assert child.poll() is not None  # terminated within cleanup's 3s wait
        assert icon.stopped is True
    finally:
        # Never leak the sleeper into CI if an assertion fired first.
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
