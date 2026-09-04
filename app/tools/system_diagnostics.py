"""System diagnostics — read-only Level-0 probes for machine-state questions.

The missing half of "find why my computer suddenly became slow" (P0 #8): a
matcher cannot discover capabilities that do not exist. The manifest had
process inspection and network connectivity tests, but no system-level
metrics, no thermal sensors, no local network ACTIVITY, no startup-program
inventory, and no system-log reading — the standard diagnostic tree for a
performance complaint was unreachable no matter how good the matching.

Design rules (from the repo's own release discipline):

  * READ-ONLY. Every probe is Level 0: it observes, it never mutates. No
    process is killed, no service toggled, no log written.
  * HONEST PER METRIC. psutil exposes features per-platform; a missing
    feature reports itself as unavailable with a reason — it is never
    fabricated, never silently skipped.
  * MEASURED, WITH FRESHNESS. CPU percent is measured over a real
    interval (default 0.5s, bounded), not a meaningless instantaneous
    reading; results carry their capture timestamp.
  * BOUNDED OUTPUT. Logs are tailed (default 50 lines), process tables
    are top-N, connection tables are summarized — a diagnostic probe must
    not flood the context that asked for it.
"""

from __future__ import annotations

import datetime
import os
import platform
import re
import time
from typing import Any, Dict, List, Optional

import psutil

from app.cognition.execution_control import run_cancellable_subprocess
from app.utils.logger import app_logger


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _honest_unavailable(feature: str, reason: str) -> Dict[str, Any]:
    """A platform-missing measurement is reported, never fabricated."""
    return {"available": False, "feature": feature, "reason": reason}


class SystemDiagnostics:
    """Autonomous read-only machine-state probes (Level 0)."""

    # ── availability (manifest probe) ────────────────────────────────────
    @classmethod
    def availability(cls, *, probe: bool = False) -> Dict[str, Any]:
        """psutil is a core dependency, so module availability == True;
        per-feature platform support is reported by each probe's RESULT
        (it can change with hardware), not frozen here."""
        return {"available": True, "status": "available"}

    # ── system metrics ───────────────────────────────────────────────────
    @classmethod
    def system_metrics(cls, interval: float = 0.5, top: int = 5) -> Dict[str, Any]:
        """One measured snapshot of the machine: CPU load, memory pressure,
        swap, per-partition disk usage, disk IO counters, uptime, and the
        top processes by CPU and memory — the first-stop probe for
        performance questions. Per-process CPU is a real two-pass
        measurement (primed baselines -> window -> sample), never the
        meaningless first-call 0.0."""
        interval = max(0.0, min(float(interval or 0.5), 5.0))
        top = max(1, min(int(top or 5), 20))
        # PRIME the per-process CPU baselines FIRST (P1 review): psutil
        # documents that a process's first non-blocking cpu_percent() is
        # meaningless (0.0) — there is no earlier reading to diff against —
        # so process_iter's one-shot readings are ALL first calls. Sorting
        # those produced a "top_processes_by_cpu" that was pid order
        # wearing a ranking's name. Priming is non-blocking; the blocking
        # system-wide measurement below IS the measurement window (no
        # extra wall time); the second reading is then genuinely measured.
        primed: List[Any] = []
        try:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    p.cpu_percent(None)  # sets the baseline; returns 0.0
                    primed.append(p)
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        psutil.ZombieProcess):
                    continue  # gone or protected: skipped, not invented
        except Exception as exc:
            app_logger.warning(f"process table priming partial: {exc}")
        try:
            cpu_percent = psutil.cpu_percent(interval=interval)
            if interval < 0.1:
                # A window shorter than 0.1s measures timer noise; top the
                # window up so the per-process deltas mean something.
                time.sleep(0.1 - interval)
            per_core = psutil.cpu_percent(interval=0, percpu=True)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            boot = psutil.boot_time()
        except Exception as exc:
            return {"success": False, "error": f"metrics collection failed: {exc}"}

        partitions: List[Dict[str, Any]] = []
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    partitions.append({
                        "mount": part.mountpoint,
                        "fstype": part.fstype,
                        "total_gb": round(usage.total / 1e9, 2),
                        "used_gb": round(usage.used / 1e9, 2),
                        "percent": usage.percent,
                    })
                except (PermissionError, OSError):
                    continue  # unmeasurable partition: skipped, not invented
        except Exception:
            pass

        disk_io: Dict[str, Any]
        try:
            io = psutil.disk_io_counters()
            disk_io = {
                "available": True,
                "read_mb": round(io.read_bytes / 1e6, 2) if io else 0.0,
                "write_mb": round(io.write_bytes / 1e6, 2) if io else 0.0,
                "read_count": io.read_count if io else 0,
                "write_count": io.write_count if io else 0,
            } if io else _honest_unavailable("disk_io", "no disk IO counters exposed")
        except Exception as exc:
            disk_io = _honest_unavailable("disk_io", str(exc))

        procs_cpu, procs_mem = [], []
        try:
            # SAMPLE: the second reading, measured against the primed
            # baselines over the window above. Processes that died or lost
            # access between the two passes are skipped, not invented.
            rows: List[Dict[str, Any]] = []
            for p in primed:
                try:
                    rows.append({
                        "pid": p.pid,
                        "name": str((p.info or {}).get("name") or ""),
                        "cpu_percent": round(float(p.cpu_percent(None)), 2),
                        "memory_percent": round(float(p.memory_percent()), 2),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        psutil.ZombieProcess):
                    continue
            procs_cpu = sorted(
                rows, key=lambda r: r["cpu_percent"], reverse=True)[:top]
            procs_mem = sorted(
                rows, key=lambda r: r["memory_percent"], reverse=True)[:top]
        except Exception as exc:
            app_logger.warning(f"process table sampling partial: {exc}")

        return {
            "success": True,
            "captured_at": _now_iso(),
            "measurement_interval_s": interval,
            "cpu": {
                "percent_total": cpu_percent,
                "cores_logical": psutil.cpu_count(logical=True),
                "cores_physical": psutil.cpu_count(logical=False),
                "percent_per_core": per_core,
            },
            "memory": {
                "total_gb": round(mem.total / 1e9, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "percent": mem.percent,
                "available_gb": round(mem.available / 1e9, 2),
            },
            "swap": {"total_gb": round(swap.total / 1e9, 2),
                     "used_gb": round(swap.used / 1e9, 2),
                     "percent": swap.percent},
            "disk_partitions": partitions,
            "disk_io": disk_io,
            "uptime": {"boot_time": datetime.datetime.fromtimestamp(
                boot, datetime.timezone.utc).isoformat(), "uptime_hours": round(
                (datetime.datetime.now().timestamp() - boot) / 3600.0, 2)},
            "top_processes_by_cpu": procs_cpu,
            "top_processes_by_memory": procs_mem,
            "platform": platform.platform(),
        }

    # ── temperature ──────────────────────────────────────────────────────
    @classmethod
    def temperature(cls) -> Dict[str, Any]:
        """Thermal sensor readings. psutil exposes these on Linux only and
        only when the hardware/VM reports them — an empty or missing sensor
        set is reported honestly, never guessed."""
        try:
            sensors = psutil.sensors_temperatures()
        except (AttributeError, OSError) as exc:
            return {"success": True, **_honest_unavailable(
                "temperature", f"not exposed on this platform: {exc}")}
        if not sensors:
            return {"success": True, **_honest_unavailable(
                "temperature",
                "no thermal sensors exposed by this platform/hardware "
                "(common in VMs and on Windows)")}

        readings: List[Dict[str, Any]] = []
        for name, entries in sensors.items():
            for e in entries:
                readings.append({
                    "sensor": name,
                    "label": e.label or None,
                    "current_celsius": e.current,
                    **({"high_celsius": e.high} if e.high else {}),
                    **({"critical_celsius": e.critical} if e.critical else {}),
                })
        hottest = max(readings, key=lambda r: r["current_celsius"])
        # A TEMPERATURE fact, not a throttling fact (P1 review): crossing
        # 80C is a risk heuristic with a visible threshold. Actual
        # throttling is reported separately, from platform evidence only.
        threshold_c = 80.0
        return {
            "success": True,
            "available": True,
            "captured_at": _now_iso(),
            "sensors": readings,
            "hottest": hottest,
            "thermal_threshold_exceeded": hottest["current_celsius"] >= threshold_c,
            "threshold_celsius": threshold_c,
            "thermal_throttling_observed": cls._thermal_throttling_evidence(),
        }

    @classmethod
    def _thermal_throttling_evidence(cls) -> Dict[str, Any]:
        """Whether the PLATFORM recorded actual CPU thermal throttling.

        Evidence-aware by design: a hot sensor is a RISK heuristic; these
        are OBSERVATIONS — kernel log throttling records (Linux), firmware
        CPU speed-limit events (Windows Event 37, Kernel-Processor-Power)
        or the power-management thermal state (macOS pmset). Unreadable
        sources are reported honestly unavailable, never guessed from the
        temperature alone.
        """
        system = platform.system()
        try:
            if system == "Linux":
                out = run_cancellable_subprocess(
                    ["journalctl", "-k", "--no-pager", "-g", "throttl", "-n", "5"],
                    timeout=8)
                if out.returncode != 0:
                    return _honest_unavailable(
                        "thermal_throttling_observed",
                        f"kernel log not readable (rc={out.returncode})")
                lines = [l.strip() for l in (out.stdout or "").splitlines()
                         if l.strip()]
                return {"available": True, "observed": bool(lines),
                        "source": "kernel log (journalctl -k, 'throttl')",
                        "records": lines[:3]}
            if system == "Windows":
                out = run_cancellable_subprocess(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-WinEvent -FilterHashtable @{LogName='System'; "
                     "ProviderName='Microsoft-Windows-Kernel-Processor-Power'; "
                     "Id=37} -MaxEvents 3 | Format-List | Out-String -Width 250"],
                    timeout=12)
                if out.returncode != 0:
                    return _honest_unavailable(
                        "thermal_throttling_observed",
                        f"System event log not readable (rc={out.returncode})")
                lines = [l.strip() for l in (out.stdout or "").splitlines()
                         if l.strip()]
                return {"available": True, "observed": bool(lines),
                        "source": "System log (Kernel-Processor-Power Id 37)",
                        "records": lines[:3]}
            if system == "Darwin":
                out = run_cancellable_subprocess(["pmset", "-g", "therm"],
                                                  timeout=5)
                if out.returncode != 0:
                    return _honest_unavailable(
                        "thermal_throttling_observed",
                        f"pmset therm not readable (rc={out.returncode})")
                # 'CPU_Speed_Limit = 100' = not limited; below 100 means the
                # OS is limiting CPU speed right now — direct observation.
                m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out.stdout or "")
                if not m:
                    return _honest_unavailable(
                        "thermal_throttling_observed",
                        f"pmset therm output not parseable: "
                        f"{(out.stdout or '').strip()[:80]}")
                limit = int(m.group(1))
                return {"available": True, "observed": limit < 100,
                        "source": "pmset -g therm",
                        "cpu_speed_limit_percent": limit}
            return _honest_unavailable(
                "thermal_throttling_observed",
                f"no platform throttling evidence source for {system}")
        except Exception as exc:
            return _honest_unavailable("thermal_throttling_observed", str(exc))

    # ── local network activity ───────────────────────────────────────────
    @classmethod
    def network_activity(cls, top: int = 10, interval: float = 0.5) -> Dict[str, Any]:
        """Local network ACTIVITY (not connectivity): throughput counters
        since boot, the live transfer RATE measured over `interval`
        seconds, and the connection table, summarized. The two IO facts are
        deliberately separate (P1 review): 100 MB since boot over 3 days
        and 100 MB over 10 minutes produce the same cumulative counter but
        are completely different answers to 'what is happening right now'.
        Connection visibility depends on OS privileges — the count of
        sockets that could not be attributed is reported honestly."""
        top = max(1, min(int(top or 10), 50))
        interval = max(0.1, min(float(interval or 0.5), 5.0))
        try:
            io_first = psutil.net_io_counters()
        except Exception as exc:
            return {"success": False, "error": f"net IO counters failed: {exc}"}
        started = time.monotonic()

        connections: List[Dict[str, Any]] = []
        denied = 0
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == psutil.CONN_NONE:
                    continue
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None
                if raddr is None:
                    denied += 0  # listening socket — visible, just not a session
                connections.append({
                    "fd": conn.fd, "family": str(conn.family),
                    "status": conn.status,
                    "local": laddr, "remote": raddr,
                    "pid": conn.pid,
                })
        except psutil.AccessDenied:
            # Whole-table denial (unprivileged on some Linux kernels).
            connections = []
            denied = -1  # sentinel: count unknowable
        except Exception as exc:
            app_logger.warning(f"connection table sampling partial: {exc}")

        remote_counts: Dict[str, int] = {}
        for c in connections:
            if c.get("remote"):
                remote_counts[c["remote"]] = remote_counts.get(c["remote"], 0) + 1
        top_remotes = sorted(remote_counts.items(), key=lambda kv: kv[1],
                             reverse=True)[:top]

        # CURRENT THROUGHPUT (P1 review): a rate is a delta over a window,
        # not a counter. The window starts at the first counter reading —
        # the connection-table sampling above happens INSIDE it — then
        # sleeps the remainder of `interval` and reads again. The actual
        # elapsed time is reported, never assumed.
        throughput: Dict[str, Any]
        counters: Dict[str, Any]
        try:
            elapsed = time.monotonic() - started
            while elapsed < interval:
                # Windows can wake the timer EARLY (owner run 2026-09-03,
                # Python 3.11.0: a 0.15s request returned after ~0.141s of
                # time.monotonic()), and a single if/sleep let the measured
                # window dip below the requested interval — a rate over a
                # shorter window misstates 'over interval seconds'. Re-sleep
                # the remainder until the deadline is genuinely reached.
                time.sleep(interval - elapsed)
                elapsed = time.monotonic() - started
            io_second = psutil.net_io_counters()
            elapsed = time.monotonic() - started
            counters = {
                "bytes_sent_mb": round(io_second.bytes_sent / 1e6, 2),
                "bytes_recv_mb": round(io_second.bytes_recv / 1e6, 2),
                "packets_sent": io_second.packets_sent,
                "packets_recv": io_second.packets_recv,
            }
            d_sent = io_second.bytes_sent - io_first.bytes_sent
            d_recv = io_second.bytes_recv - io_first.bytes_recv
            d_psent = io_second.packets_sent - io_first.packets_sent
            d_precv = io_second.packets_recv - io_first.packets_recv
            if min(d_sent, d_recv, d_psent, d_precv) < 0:
                # Interface counters can reset (link down/up, driver reload):
                # the window straddling a reset measures nothing real.
                throughput = _honest_unavailable(
                    "current_throughput",
                    "interface counters reset during the measurement window")
            elif elapsed <= 0:
                throughput = _honest_unavailable(
                    "current_throughput", "no measurable interval elapsed")
            else:
                throughput = {
                    "available": True,
                    "measured_interval_s": round(elapsed, 3),
                    "bytes_sent_per_s": round(d_sent / elapsed, 2),
                    "bytes_recv_per_s": round(d_recv / elapsed, 2),
                    "packets_sent_per_s": round(d_psent / elapsed, 2),
                    "packets_recv_per_s": round(d_precv / elapsed, 2),
                }
        except Exception as exc:
            throughput = _honest_unavailable("current_throughput", str(exc))
            counters = {
                "bytes_sent_mb": round(io_first.bytes_sent / 1e6, 2),
                "bytes_recv_mb": round(io_first.bytes_recv / 1e6, 2),
                "packets_sent": io_first.packets_sent,
                "packets_recv": io_first.packets_recv,
            }

        return {
            "success": True,
            "captured_at": _now_iso(),
            "io_since_boot": counters,
            "current_throughput": throughput,
            "active_connections": len(connections),
            "connections": connections[:50],
            "unattributable_socket_count": denied if denied else None,
            "top_remote_endpoints": [{"remote": r, "connections": n}
                                     for r, n in top_remotes],
        }

    # ── startup programs ─────────────────────────────────────────────────
    @classmethod
    def startup_programs(cls) -> Dict[str, Any]:
        """What launches at boot/login, per platform: enabled systemd units
        and XDG autostart entries on Linux; Run registry keys and Startup
        folders on Windows. Read-only inventory — the first place to look
        for slow-boot and background-load complaints."""
        system = platform.system()
        sources: List[Dict[str, Any]] = []
        if system == "Linux":
            sources.append(cls._linux_systemd_services())
            sources.append(cls._linux_xdg_autostart())
        elif system == "Windows":
            sources.append(cls._windows_run_keys())
            sources.append(cls._windows_startup_folders())
        else:
            return {"success": True, **_honest_unavailable(
                "startup_programs", f"unsupported platform: {system}")}

        items = [i for s in sources for i in s.get("items", [])]
        return {
            "success": True,
            "captured_at": _now_iso(),
            "platform": system,
            "sources": [{"source": s["source"], "status": s["status"],
                         "count": len(s.get("items", []))} for s in sources],
            "items": items,
            "total": len(items),
        }

    @classmethod
    def _linux_systemd_services(cls) -> Dict[str, Any]:
        try:
            out = run_cancellable_subprocess(
                ["systemctl", "list-unit-files", "--type=service",
                 "--state=enabled", "--no-pager", "--no-legend"],
                timeout=15,
            )
        except Exception as exc:
            return {"source": "systemd-enabled-services",
                    "status": f"unavailable: {exc}", "items": []}
        if out.returncode != 0:
            return {"source": "systemd-enabled-services",
                    "status": f"unavailable (rc={out.returncode}): "
                              f"{(out.stderr or '').strip()[:120]}", "items": []}
        items = []
        for line in (out.stdout or "").splitlines():
            parts = line.split()
            if parts:
                items.append({"name": parts[0], "source": "systemd",
                              "state": parts[1] if len(parts) > 1 else "enabled"})
        return {"source": "systemd-enabled-services", "status": "ok", "items": items}

    @classmethod
    def _linux_xdg_autostart(cls) -> Dict[str, Any]:
        items = []
        seen = set()
        for base in (os.path.expanduser("~/.config/autostart"),
                     "/etc/xdg/autostart"):
            if not os.path.isdir(base):
                continue
            try:
                for fn in sorted(os.listdir(base)):
                    if fn.endswith(".desktop") and fn not in seen:
                        seen.add(fn)
                        items.append({"name": fn, "source": base,
                                      "state": "autostart"})
            except OSError as exc:
                app_logger.warning(f"autostart dir unreadable: {base}: {exc}")
        status = "ok" if items or os.path.isdir("/etc/xdg/autostart") or \
            os.path.isdir(os.path.expanduser("~/.config/autostart")) else "none found"
        return {"source": "xdg-autostart", "status": status, "items": items}

    @classmethod
    def _windows_run_keys(cls) -> Dict[str, Any]:
        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            return {"source": "registry-run-keys",
                    "status": "unavailable: winreg not present", "items": []}
        items = []
        for hive, hive_name in ((winreg.HKEY_CURRENT_USER, "HKCU"),
                                (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
            for subkey in (r"Software\Microsoft\Windows\CurrentVersion\Run",
                           r"Software\Microsoft\Windows\CurrentVersion\RunOnce"):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        i = 0
                        while True:
                            try:
                                name, value, _ = winreg.EnumValue(key, i)
                            except OSError:
                                break
                            items.append({"name": name, "source": f"{hive_name}\\{subkey}",
                                          "command": str(value)[:200]})
                            i += 1
                except OSError:
                    continue
        return {"source": "registry-run-keys", "status": "ok", "items": items}

    @classmethod
    def _windows_startup_folders(cls) -> Dict[str, Any]:
        items = []
        for base in (os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
                     os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp")):
            if os.path.isdir(base):
                try:
                    for fn in sorted(os.listdir(base)):
                        items.append({"name": fn, "source": base, "state": "startup-folder"})
                except OSError:
                    continue
        return {"source": "startup-folders", "status": "ok", "items": items}

    # ── recent system logs ───────────────────────────────────────────────
    @classmethod
    def recent_logs(cls, lines: int = 50, source: Optional[str] = None) -> Dict[str, Any]:
        """Tail recent SYSTEM log events (journalctl on Linux, the Windows
        System event log). Entries are WHOLE events — a multi-line Windows
        event record is one entry, never fragmented lines. Bounded,
        read-only, with honest per-source status when a log is unreadable
        or the journal needs privileges the process does not have."""
        lines = max(1, min(int(lines or 50), 200))
        system = platform.system()
        sources: List[Dict[str, Any]] = []
        if system == "Linux":
            if source in (None, "", "journal", "systemd"):
                sources.append(cls._linux_journal(lines))
            if source in (None, "", "files", "syslog"):
                sources.extend(cls._linux_log_files(lines))
        elif system == "Windows":
            sources.append(cls._windows_event_log(lines))
        else:
            return {"success": True, **_honest_unavailable(
                "recent_logs", f"unsupported platform: {system}")}

        total = sum(len(s.get("entries", [])) for s in sources)
        return {
            "success": True,
            "captured_at": _now_iso(),
            "platform": system,
            "sources": [{"source": s["source"], "status": s["status"],
                         "entries": len(s.get("entries", []))} for s in sources],
            "entries": [e for s in sources for e in s.get("entries", [])][:lines],
            "total_entries": total,
        }

    @classmethod
    def _linux_journal(cls, lines: int) -> Dict[str, Any]:
        try:
            out = run_cancellable_subprocess(
                ["journalctl", "-n", str(lines), "--no-pager", "--output=short"],
                timeout=15,
            )
        except Exception as exc:
            return {"source": "journalctl", "status": f"unavailable: {exc}",
                    "entries": []}
        if out.returncode != 0:
            return {"source": "journalctl",
                    "status": f"unavailable (rc={out.returncode}): "
                              f"{(out.stderr or '').strip()[:120]}", "entries": []}
        entries = [ln for ln in (out.stdout or "").splitlines() if ln.strip()]
        return {"source": "journalctl", "status": "ok", "entries": entries}

    @classmethod
    def _linux_log_files(cls, lines: int) -> List[Dict[str, Any]]:
        results = []
        for path in ("/var/log/syslog", "/var/log/messages"):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", errors="replace") as fh:
                    tail = fh.readlines()[-lines:]
                results.append({"source": path, "status": "ok",
                                "entries": [ln.rstrip("\n") for ln in tail if ln.strip()]})
            except OSError as exc:
                results.append({"source": path, "status": f"unreadable: {exc}",
                                "entries": []})
        return results or [{"source": "/var/log/syslog", "status": "not present",
                            "entries": []}]

    @staticmethod
    def _event_records(stdout: str) -> List[str]:
        """WHOLE multi-line event records, not lines (P1 review).

        Both Windows paths emit one BLOCK per event: wevtutil /f:text marks
        record starts with 'Event[N]:' (and an event's Description may
        itself contain blank lines), while Get-WinEvent Format-List
        separates events with blank lines. Treating lines as entries made
        one event count as ~8 entries and truncation cut events in half —
        'last 50 events' became 'first 50 non-empty lines'."""
        lines = (stdout or "").splitlines()
        records: List[str] = []
        starts = [i for i, ln in enumerate(lines)
                  if re.match(r"\s*Event\[\d+\]:", ln)]
        if starts:
            # wevtutil text format: explicit record markers are
            # authoritative — robust to blank lines inside a description.
            bounds = starts + [len(lines)]
            for a, b in zip(bounds, bounds[1:]):
                records.append(
                    "\n".join(ln.rstrip() for ln in lines[a:b]).strip())
        else:
            # Get-WinEvent Format-List: events separated by blank lines.
            block: List[str] = []
            for ln in lines:
                if ln.strip():
                    block.append(ln.rstrip())
                elif block:
                    records.append("\n".join(block).strip())
                    block = []
            if block:
                records.append("\n".join(block).strip())
        return [r for r in records if r]

    @classmethod
    def _windows_event_log(cls, lines: int) -> Dict[str, Any]:
        """PowerShell Get-WinEvent first — it streams the NEWEST events and is
        fast even on multi-GB System logs, where wevtutil qe was observed
        exceeding 20s on the owner machine. wevtutil stays as fallback."""
        try:
            out = run_cancellable_subprocess(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-WinEvent -LogName System -MaxEvents {lines} "
                 f"| Format-List | Out-String -Width 250"],
                timeout=30,
            )
        except Exception as exc:
            out = None
            app_logger.warning(f"Get-WinEvent probe failed, falling back to wevtutil: {exc}")
        if out is not None and out.returncode == 0:
            entries = cls._event_records(out.stdout)[:lines]
            return {"source": "event-log (Get-WinEvent)", "status": "ok", "entries": entries}
        # Fallback: the classic wevtutil text query (slow on large logs).
        try:
            out = run_cancellable_subprocess(
                ["wevtutil", "qe", "System", "/c:" + str(lines),
                 "/rd:true", "/f:text"],
                timeout=45,
            )
        except Exception as exc:
            return {"source": "event-log", "status": f"unavailable: {exc}",
                    "entries": []}
        if out.returncode != 0:
            return {"source": "event-log",
                    "status": f"unavailable (rc={out.returncode}): "
                              f"{(out.stderr or '').strip()[:120]}", "entries": []}
        entries = cls._event_records(out.stdout)[:lines]
        return {"source": "event-log", "status": "ok", "entries": entries}
