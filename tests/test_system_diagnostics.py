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
    # The live rate is a separate, measured fact (real machine).
    tp = result["current_throughput"]
    assert tp["available"] is True
    assert tp["measured_interval_s"] > 0
    assert tp["bytes_sent_per_s"] >= 0 and tp["bytes_recv_per_s"] >= 0


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


# ── temperature says temperature; throttling needs evidence (P1 review) ─────
# 'hottest >= 80' is a high-temperature HEURISTIC, not throttling detection.
# The old field name (thermal_throttling_possible) overstated that fact; the
# commit/manifest wording ("throttling flag") did too. Now: the heuristic is
# named for what it measures and carries its threshold; actual throttling is
# a separate, platform-evidence-only observation.

class _Sensor:
    def __init__(self, current, label="CPU", high=None, critical=None):
        self.current = current
        self.label = label
        self.high = high
        self.critical = critical


class _ProcResult:
    def __init__(self, rc=0, stdout=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = ""


def _fake_sensors(monkeypatch, current_c):
    import app.tools.system_diagnostics as mod
    monkeypatch.setattr(
        mod.psutil, "sensors_temperatures",
        staticmethod(lambda: {"coretemp": [_Sensor(current_c)]}),
        raising=False)  # Windows psutil lacks the attribute entirely


def test_hot_sensor_reports_threshold_fact_not_throttling(monkeypatch):
    _fake_sensors(monkeypatch, 85.0)
    result = SystemDiagnostics.temperature()
    # The honest rename: no more 'thermal_throttling_possible'.
    assert "thermal_throttling_possible" not in result
    assert result["thermal_threshold_exceeded"] is True
    # The heuristic's basis is visible, inspectable evidence.
    assert result["threshold_celsius"] == 80.0
    assert result["hottest"]["current_celsius"] == 85.0


def test_cool_sensor_threshold_not_exceeded(monkeypatch):
    _fake_sensors(monkeypatch, 42.0)
    result = SystemDiagnostics.temperature()
    assert result["thermal_threshold_exceeded"] is False
    assert result["threshold_celsius"] == 80.0


def test_throttling_observed_is_platform_evidence_never_the_heuristic(monkeypatch):
    """A hot sensor with NO readable platform source must NOT report
    throttling — the evidence field says honestly unavailable instead."""
    import app.tools.system_diagnostics as mod
    _fake_sensors(monkeypatch, 95.0)  # very hot: heuristic maxed
    monkeypatch.setattr(mod, "run_cancellable_subprocess",
                        lambda cmd, timeout: _ProcResult(rc=1))
    result = SystemDiagnostics.temperature()
    evidence = result["thermal_throttling_observed"]
    assert evidence["available"] is False
    assert evidence["reason"]
    assert "observed" not in evidence  # no claim without evidence


def test_kernel_log_throttling_record_is_observed(monkeypatch):
    import app.tools.system_diagnostics as mod
    _fake_sensors(monkeypatch, 85.0)
    monkeypatch.setattr(mod, "run_cancellable_subprocess", lambda cmd, timeout: _ProcResult(
        stdout="Jul 12 10:00:01 host kernel: cpu clock throttled\n"))
    result = SystemDiagnostics.temperature()
    evidence = result["thermal_throttling_observed"]
    assert evidence["available"] is True
    assert evidence["observed"] is True
    assert evidence["source"].startswith("kernel log")


def test_clean_kernel_log_is_negative_evidence(monkeypatch):
    """A readable source with no throttling records is a real observation:
    observed=False, not 'unknown'."""
    import app.tools.system_diagnostics as mod
    _fake_sensors(monkeypatch, 85.0)
    monkeypatch.setattr(mod, "run_cancellable_subprocess",
                        lambda cmd, timeout: _ProcResult(stdout=""))
    result = SystemDiagnostics.temperature()
    evidence = result["thermal_throttling_observed"]
    assert evidence["available"] is True
    assert evidence["observed"] is False


def test_windows_speed_limit_event_is_observed(monkeypatch):
    """Platform routing: the Windows path reads Kernel-Processor-Power
    Event 37 (firmware is limiting the processor)."""
    import app.tools.system_diagnostics as mod
    _fake_sensors(monkeypatch, 85.0)
    seen = {}

    def fake_run(cmd, timeout):
        seen["cmd"] = cmd
        return _ProcResult(stdout="TimeCreated: 2026-08-30\nMessage: The speed of processor 0 is being limited\n")

    monkeypatch.setattr(mod, "run_cancellable_subprocess", fake_run)
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    result = SystemDiagnostics.temperature()
    evidence = result["thermal_throttling_observed"]
    assert evidence["available"] is True and evidence["observed"] is True
    assert "Kernel-Processor-Power" in " ".join(seen["cmd"])


def test_macos_cpu_speed_limit_is_observed(monkeypatch):
    import app.tools.system_diagnostics as mod
    _fake_sensors(monkeypatch, 85.0)
    monkeypatch.setattr(mod, "run_cancellable_subprocess", lambda cmd, timeout: _ProcResult(
        stdout="CPU/thermal level = 2\nCPU_Speed_Limit = 75\n"))
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    result = SystemDiagnostics.temperature()
    evidence = result["thermal_throttling_observed"]
    assert evidence["available"] is True
    assert evidence["observed"] is True
    assert evidence["cpu_speed_limit_percent"] == 75


def test_macos_full_speed_limit_is_not_throttling(monkeypatch):
    import app.tools.system_diagnostics as mod
    _fake_sensors(monkeypatch, 85.0)
    monkeypatch.setattr(mod, "run_cancellable_subprocess", lambda cmd, timeout: _ProcResult(
        stdout="CPU_Speed_Limit = 100\n"))
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    result = SystemDiagnostics.temperature()
    evidence = result["thermal_throttling_observed"]
    assert evidence["observed"] is False


# ── current throughput is a MEASURED rate, not a cumulative counter ─────────
# P1 review: io_since_boot cannot answer 'what is happening right now' —
# 100 MB accumulated over 3 days and 100 MB over 10 minutes produce the
# same counter. The rate is a delta over a real window, reported separately.

class _FakeIO:
    def __init__(self, sent, recv, psent, precv):
        self.bytes_sent = sent
        self.bytes_recv = recv
        self.packets_sent = psent
        self.packets_recv = precv


def _fake_net_psutil(monkeypatch, readings):
    """readings: list of _FakeIO returned by successive net_io_counters()
    calls. Also fakes the connection table (empty)."""
    import app.tools.system_diagnostics as mod
    calls = {"n": 0}

    class _FakePsutilNet:
        CONN_NONE = "NONE"
        AccessDenied = type(mod.psutil.AccessDenied)

        @staticmethod
        def net_io_counters():
            i = min(calls["n"], len(readings) - 1)
            calls["n"] += 1
            return readings[i]

        @staticmethod
        def net_connections(kind="inet"):
            return []

    monkeypatch.setattr(mod, "psutil", _FakePsutilNet)
    return calls


def test_current_throughput_is_a_measured_rate(monkeypatch):
    """50 MB sent inside the window -> ~50MB/s reported, with the actual
    elapsed window reported (never assumed)."""
    _fake_net_psutil(monkeypatch, [
        _FakeIO(1_000_000_000, 2_000_000_000, 1_000, 2_000),
        _FakeIO(1_050_000_000, 2_075_000_000, 1_500, 2_300),
    ])
    result = SystemDiagnostics.network_activity(interval=0.15)
    assert result["success"] is True
    tp = result["current_throughput"]
    assert tp["available"] is True
    assert tp["measured_interval_s"] >= 0.15
    # rate x window == the measured delta (within timer slop)
    sent_over_window = tp["bytes_sent_per_s"] * tp["measured_interval_s"]
    assert abs(sent_over_window - 50_000_000) / 50_000_000 < 0.05, tp
    recv_over_window = tp["bytes_recv_per_s"] * tp["measured_interval_s"]
    assert abs(recv_over_window - 75_000_000) / 75_000_000 < 0.05, tp
    # The cumulative fact is separate and reflects the latest reading.
    assert result["io_since_boot"]["bytes_sent_mb"] == 1050.0


def test_idle_network_distinguishes_now_from_history(monkeypatch):
    """The review's exact case: 100 MB sent since boot but ZERO traffic in
    the window -> rate 0.0 while the counter stays huge. One number cannot
    carry both facts; two fields do."""
    _fake_net_psutil(monkeypatch, [
        _FakeIO(100_000_000, 100_000_000, 10_000, 10_000),
        _FakeIO(100_000_000, 100_000_000, 10_000, 10_000),
    ])
    result = SystemDiagnostics.network_activity(interval=0.1)
    tp = result["current_throughput"]
    assert tp["available"] is True
    assert tp["bytes_sent_per_s"] == 0.0
    assert tp["bytes_recv_per_s"] == 0.0
    assert result["io_since_boot"]["bytes_sent_mb"] == 100.0


def test_counter_reset_during_window_is_honest(monkeypatch):
    """Interface counters can reset (link down/up): a window straddling the
    reset measures nothing real — reported honestly unavailable, never a
    bogus negative or wrapped rate."""
    _fake_net_psutil(monkeypatch, [
        _FakeIO(5_000_000_000, 5_000_000_000, 50_000, 50_000),
        _FakeIO(1_000, 1_000, 10, 10),   # reset mid-window
    ])
    result = SystemDiagnostics.network_activity(interval=0.1)
    tp = result["current_throughput"]
    assert tp["available"] is False
    assert tp["reason"]
    # The cumulative fact survives from the latest (post-reset) reading.
    assert result["io_since_boot"]["bytes_sent_mb"] == 0.0


def test_second_counter_read_failure_degrades_honestly(monkeypatch):
    """If the second reading fails, the rate is honestly unavailable but
    the since-boot counters (from the first reading) still ship."""
    import app.tools.system_diagnostics as mod

    class _FlakyPsutil:
        CONN_NONE = "NONE"
        AccessDenied = type(mod.psutil.AccessDenied)
        calls = {"n": 0}

        @classmethod
        def net_io_counters(cls):
            cls.calls["n"] += 1
            if cls.calls["n"] == 1:
                return _FakeIO(1_000_000, 1_000_000, 100, 100)
            raise OSError("counter read failed")

        @staticmethod
        def net_connections(kind="inet"):
            return []

    monkeypatch.setattr(mod, "psutil", _FlakyPsutil)
    result = SystemDiagnostics.network_activity(interval=0.1)
    assert result["success"] is True
    assert result["current_throughput"]["available"] is False
    assert result["current_throughput"]["reason"]
    assert result["io_since_boot"]["bytes_sent_mb"] == 1.0


# ── Windows event-log entries are WHOLE events, not lines (P1 review) ───────
# wevtutil /f:text and Get-WinEvent Format-List both emit multi-line blocks
# per event. The old line-splitting made 1 event count as ~8 entries and
# truncation cut events in half: 'last 50 events' was really 'first 50
# non-empty lines'. Downstream reasoning deserves whole records.

_WEVTUTIL_SAMPLE = """Event[0]:
  Date: 2026-08-30 10:00:01
  Event ID: 6005
  Level: Information
  Computer: OWNER-PC
  Description:
    The Event log service was started.

Event[1]:
  Date: 2026-08-30 10:02:33
  Event ID: 37
  Level: Warning
  Computer: OWNER-PC
  Description:
    The speed of processor 0 is being limited by system firmware.
    The processor has been in this limited performance state for 6 seconds.

Event[2]:
  Date: 2026-08-30 10:05:12
  Event ID: 41
  Description:
    First paragraph of the description.

    Second paragraph after an internal blank line.
"""

_WINEVENT_SAMPLE = """TimeCreated  : 2026/08/30 10:05:12
ProviderName : Microsoft-Windows-Kernel-Power
Id           : 41
Message      : The system has rebooted without cleanly shutting down.

TimeCreated  : 2026/08/30 10:02:33
ProviderName : Microsoft-Windows-Kernel-Processor-Power
Id           : 37
Message      : The speed of processor 0 is being limited by system firmware.
"""


def _fake_windows_logs(monkeypatch, winevent_rc=1, winevent_out="",
                       wevtutil_out=_WEVTUTIL_SAMPLE):
    import app.tools.system_diagnostics as mod
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")

    def fake_run(cmd, timeout):
        if "Get-WinEvent" in " ".join(cmd):
            return _ProcResult(rc=winevent_rc, stdout=winevent_out)
        return _ProcResult(rc=0, stdout=wevtutil_out)

    monkeypatch.setattr(mod, "run_cancellable_subprocess", fake_run)


def test_wevtutil_entries_are_whole_events(monkeypatch):
    """Three Event[N] blocks -> exactly 3 entries, each carrying its full
    record from Date through Description."""
    _fake_windows_logs(monkeypatch)
    result = SystemDiagnostics.recent_logs(lines=50)
    src = result["sources"][0]
    assert src["status"] == "ok"
    assert src["entries"] == 3, "3 events, not ~30 lines"
    entries = result["entries"]
    assert len(entries) == 3
    # Each entry is a complete record, not a fragment.
    for entry, eid in zip(entries, ("6005", "37", "41")):
        assert f"Event ID: {eid}" in entry
        assert "Description:" in entry
    # The multi-line throttling description stays ONE entry, whole.
    assert "limited performance state" in entries[1]


def test_wevtutil_internal_blank_line_keeps_one_event(monkeypatch):
    """A Description containing its own blank line (Event[2]) must not split
    the record — Event[N] markers are authoritative."""
    _fake_windows_logs(monkeypatch)
    result = SystemDiagnostics.recent_logs(lines=50)
    third = result["entries"][2]
    assert "First paragraph" in third and "Second paragraph" in third


def test_truncation_cuts_events_never_halves(monkeypatch):
    """lines=2 returns the first 2 COMPLETE events — no entry ends
    mid-record."""
    _fake_windows_logs(monkeypatch)
    result = SystemDiagnostics.recent_logs(lines=2)
    entries = result["entries"]
    assert len(entries) == 2
    assert "Event ID: 6005" in entries[0]
    assert "Event ID: 37" in entries[1] and "Description:" in entries[1]
    assert all("Description:" in e for e in entries)  # whole records only


def test_get_winevent_blocks_group_by_blank_lines(monkeypatch):
    """Primary path (Get-WinEvent Format-List): events separated by blank
    lines; each entry keeps its multi-line Message."""
    _fake_windows_logs(monkeypatch, winevent_rc=0,
                       winevent_out=_WINEVENT_SAMPLE)
    result = SystemDiagnostics.recent_logs(lines=10)
    src = result["sources"][0]
    assert src["source"] == "event-log (Get-WinEvent)"
    assert src["entries"] == 2
    first = result["entries"][0]
    assert "Id           : 41" in first
    assert "cleanly shutting down" in first  # multi-line Message intact
    assert "Id           : 37" in result["entries"][1]
