"""P0 #8 (capability half): the read-only system diagnostic probes.

A matcher cannot discover capabilities that do not exist. These tests pin
the five Level-0 probes that complete the standard diagnostic tree for a
performance complaint: system metrics, thermals, local network activity,
startup inventory, and system log tails — every one read-only, bounded,
and honest per metric (a missing platform feature reports itself, it is
never fabricated).
"""

from __future__ import annotations

import psutil
import pytest

from app.tools.manifest import get_tool_manifest
from app.tools.system_diagnostics import SystemDiagnostics


# ── registration: reachable, read-only, honestly probeable ─────────────────

REGISTRATION = ("system_metrics", "temperature_status", "network_activity",
                "startup_programs", "recent_logs")


def test_all_probes_registered_at_level_0():
    manifest = get_tool_manifest()
    for name in REGISTRATION:
        assert name in manifest, f"{name} not registered"
        entry = manifest[name]
        assert entry["safety_level"] == 0, f"{name} must be read-only"
        assert callable(entry["handler"])


def test_probes_discoverable_through_the_manifest():
    """Registration is not enough — the probes must be FINDABLE by
    discovery (name + description carry the diagnostic vocabulary)."""
    from app.cognition.tool_matcher import rank_tools
    for name in REGISTRATION:
        hits = rank_tools(name.replace("_", " "), limit=15)
        assert any(h.action_type == name for h in hits), name


# ── system metrics ──────────────────────────────────────────────────────────

def test_system_metrics_measures_the_machine():
    result = SystemDiagnostics.system_metrics(interval=0.1, top=3)
    assert result["success"] is True
    assert result["captured_at"]
    assert 0.0 <= result["cpu"]["percent_total"] <= 100.0
    assert result["cpu"]["cores_logical"] >= 1
    assert result["memory"]["total_gb"] > 0
    assert result["memory"]["percent"] >= 0
    assert result["uptime"]["uptime_hours"] >= 0
    # Measured over a real interval, and the interval is reported.
    assert result["measurement_interval_s"] == 0.1
    # Top-process lists are bounded as requested.
    assert len(result["top_processes_by_cpu"]) <= 3
    assert len(result["top_processes_by_memory"]) <= 3
    # And the CPU list is an actual ranking: non-negative measured floats
    # in descending order (the fake-psutil suite proves the two-pass
    # measurement; this catches a real regression in the real path).
    cpu_vals = [p["cpu_percent"] for p in result["top_processes_by_cpu"]]
    assert all(isinstance(v, float) and v >= 0.0 for v in cpu_vals), cpu_vals
    assert cpu_vals == sorted(cpu_vals, reverse=True), cpu_vals


def test_system_metrics_inputs_are_bounded():
    """A diagnostic probe must not flood the context that asked for it."""
    result = SystemDiagnostics.system_metrics(interval=999, top=999)
    assert result["success"] is True
    assert result["measurement_interval_s"] <= 5.0
    assert len(result["top_processes_by_cpu"]) <= 20


def test_disk_io_reported_or_honestly_unavailable():
    result = SystemDiagnostics.system_metrics(interval=0.05)
    io = result["disk_io"]
    assert io["available"] in (True, False)
    if io["available"]:
        assert "read_mb" in io and "write_mb" in io
    else:
        assert io.get("reason"), "unavailable must say why"


# ── temperature: honest per platform ────────────────────────────────────────

def test_temperature_never_fabricates():
    result = SystemDiagnostics.temperature()
    assert result["success"] is True
    if result.get("available"):
        assert result["sensors"], "available=True requires actual readings"
        hottest = result["hottest"]
        assert isinstance(hottest["current_celsius"], (int, float))
    else:
        # VMs and Windows commonly expose no sensors — reported, not guessed.
        assert result["reason"]


# ── network activity ────────────────────────────────────────────────────────

def test_network_activity_reports_counters_and_connections():
    result = SystemDiagnostics.network_activity()
    assert result["success"] is True
    io = result["io_since_boot"]
    assert io["bytes_sent_mb"] >= 0 and io["bytes_recv_mb"] >= 0
    assert isinstance(result["active_connections"], int)
    # The connection table is bounded even on busy hosts.
    assert len(result["connections"]) <= 50


# ── startup programs ────────────────────────────────────────────────────────

def test_startup_programs_inventory_with_source_status():
    result = SystemDiagnostics.startup_programs()
    assert result["success"] is True
    # Every source reports an explicit status — never silently missing.
    for source in result["sources"]:
        assert source["status"]
    # Items carry where they came from.
    for item in result["items"]:
        assert item.get("source")


@pytest.mark.skipif(psutil.LINUX is False, reason="linux-specific source check")
def test_startup_programs_linux_sources_probed():
    result = SystemDiagnostics.startup_programs()
    names = {s["source"] for s in result["sources"]}
    assert "systemd-enabled-services" in names
    assert "xdg-autostart" in names


# ── recent logs ─────────────────────────────────────────────────────────────

def test_recent_logs_bounded_and_honest_per_source():
    result = SystemDiagnostics.recent_logs(lines=10)
    assert result["success"] is True
    assert len(result["entries"]) <= 10, "log tail must respect the bound"
    for source in result["sources"]:
        assert source["status"], "each source reports a status"


def test_recent_logs_single_source_filter():
    import platform
    result = SystemDiagnostics.recent_logs(lines=5, source="journal")
    names = {s["source"] for s in result["sources"]}
    if platform.system() == "Windows":
        # The journal source does not exist on Windows; the platform's own
        # system log (Event Log) is what a 'journal' request maps to there.
        assert any("event-log" in n for n in names), names
    else:
        assert "journalctl" in names
        assert "/var/log/syslog" not in names


# ── read-only discipline ────────────────────────────────────────────────────

def test_probes_are_read_only_by_construction():
    """The module imports no mutation API: no kill/terminate/write calls.
    (Guarded by the manifest safety level too — pinned above.)"""
    import inspect
    from app.tools import system_diagnostics as mod
    source = inspect.getsource(mod)
    for forbidden in (".kill(", ".terminate(", ".send_signal(", "os.remove(",
                      "shutil.rmtree(", "os.system("):
        assert forbidden not in source, forbidden


# ── per-process CPU is MEASURED, not a first-call 0.0 (P1 review) ───────────
# psutil documents that a process's first non-blocking cpu_percent() is
# meaningless (no baseline to diff against). The old one-pass sampling
# sorted those zeros — "top_processes_by_cpu" was pid order wearing a
# ranking's name. These tests use a fake psutil that faithfully reproduces
# the documented first-call behavior and prove the ranking uses the SECOND
# (measured) reading.

class _FakeProc:
    """Emulates psutil.Process: first cpu_percent() = 0.0 (documented),
    subsequent calls = the measured usage over the window."""

    def __init__(self, pid, name, measured_cpu, memory_percent,
                 die_after_prime=False):
        self.pid = pid
        self.info = {"pid": pid, "name": name}
        self._measured = measured_cpu
        self._mem = memory_percent
        self._die_after_prime = die_after_prime
        self.cpu_calls = 0

    def cpu_percent(self, interval=None):
        self.cpu_calls += 1
        if self.cpu_calls == 1:
            return 0.0                     # documented first-call behavior
        if self._die_after_prime:
            raise _FakePsutil.NoSuchProcess(pid=self.pid)
        return self._measured

    def memory_percent(self):
        if self._die_after_prime:
            raise _FakePsutil.NoSuchProcess(pid=self.pid)
        return self._mem


class _FakePsutil:
    class NoSuchProcess(Exception):
        def __init__(self, pid=None): super().__init__(f"no such pid {pid}")
    class AccessDenied(Exception): pass
    class ZombieProcess(Exception): pass

    def __init__(self, procs):
        self._procs = procs

    def process_iter(self, attrs=None):
        return list(self._procs)

    @staticmethod
    def cpu_percent(interval=None, percpu=False):
        if percpu:
            return [12.5, 7.5]
        return 20.0

    @staticmethod
    def cpu_count(logical=True):
        return 2 if logical else 1

    @staticmethod
    def virtual_memory():
        class _M: total = 16e9; used = 8e9; percent = 50.0; available = 8e9
        return _M()

    @staticmethod
    def swap_memory():
        class _S: total = 8e9; used = 1e9; percent = 12.5
        return _S()

    @staticmethod
    def boot_time():
        import time as _t
        return _t.time() - 3600.0

    @staticmethod
    def disk_partitions(all=False):
        return []

    @staticmethod
    def disk_io_counters():
        return None                       # honest-unavailable path


def _with_fake_psutil(monkeypatch, procs):
    import app.tools.system_diagnostics as mod
    fake = _FakePsutil(procs)
    monkeypatch.setattr(mod, "psutil", fake)
    return fake


def test_top_processes_by_cpu_ranks_measured_values(monkeypatch):
    """The ranking must come from the SECOND (measured) reading — the
    process actually burning CPU ranks first even though its first reading
    is the documented 0.0."""
    busy = _FakeProc(101, "busy_app", 88.9, 5.0)
    idle = _FakeProc(102, "idle_app", 1.2, 3.0)
    _with_fake_psutil(monkeypatch, [busy, idle])
    result = SystemDiagnostics.system_metrics(interval=0.1, top=5)
    assert result["success"] is True
    top_cpu = result["top_processes_by_cpu"]
    assert [p["name"] for p in top_cpu] == ["busy_app", "idle_app"], top_cpu
    assert top_cpu[0]["cpu_percent"] == 88.9
    assert top_cpu[1]["cpu_percent"] == 1.2
    # Memory ranking is independent of CPU.
    assert [p["name"] for p in result["top_processes_by_memory"]] == \
        ["busy_app", "idle_app"]


def test_every_process_is_primed_then_sampled(monkeypatch):
    """Proof of the two-pass protocol: each process's cpu_percent is called
    exactly twice (prime, then measure) — a one-pass implementation calls
    it once and sorts first-call zeros."""
    procs = [_FakeProc(1, "a", 10.0, 1.0), _FakeProc(2, "b", 20.0, 2.0)]
    _with_fake_psutil(monkeypatch, procs)
    SystemDiagnostics.system_metrics(interval=0.1, top=5)
    for p in procs:
        assert p.cpu_calls == 2, (p.info["name"], p.cpu_calls)


def test_process_dying_between_passes_is_skipped_not_invented(monkeypatch):
    """A process that disappears after priming (the window is real time)
    is absent from both rankings — never carried with a stale or zero
    reading."""
    survivor = _FakeProc(1, "survivor", 5.0, 4.0)
    gone = _FakeProc(2, "gone_app", 99.0, 99.0, die_after_prime=True)
    _with_fake_psutil(monkeypatch, [survivor, gone])
    result = SystemDiagnostics.system_metrics(interval=0.1, top=5)
    names = [p["name"] for p in result["top_processes_by_cpu"]]
    assert names == ["survivor"], names
    assert "gone_app" not in [p["name"] for p in result["top_processes_by_memory"]]
