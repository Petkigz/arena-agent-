"""Process manager — list / inspect / terminate local processes.

Deterministic (psutil), no LLM. Typed `{"success": bool, ...}` responses,
graceful degradation when psutil can't read a process (permissions, zombie,
gone-between-iterations).

Safety model (manifest authoritative):
- list_processes / get_process → Level 0 (read).
- kill_process / restart_process → Level 3 (irreversible: killing a process can
  lose unsaved work), gated behind explicit owner approval.

Self-protection: the manager refuses to kill PID 0/1 (init), or the Arena
process itself (os.getpid()), so a bad tool call can't take down the agent.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

import psutil

from app.utils.logger import app_logger, audit_logger


class ProcessManager:
    @staticmethod
    def _snapshot(proc: psutil.Process) -> Dict[str, Any]:
        """Best-effort snapshot of one process; never raises."""
        try:
            return {
                "pid": proc.pid,
                "name": proc.name() or "",
                "status": proc.status(),
                "cpu_percent": round(proc.cpu_percent(interval=None), 2),
                "memory_percent": round(proc.memory_percent(), 2),
                "memory_bytes": proc.memory_info().rss if proc.memory_info() else 0,
                "num_threads": proc.num_threads() if proc.num_threads() else 0,
                "create_time": proc.create_time(),
                "cmdline": " ".join(proc.cmdline())[:500] if proc.cmdline() else "",
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return {"pid": proc.pid, "name": None, "status": "gone"}

    # ── read (Level 0) ──────────────────────────────────────────────────────
    @classmethod
    def list_processes(cls, filter: Optional[str] = None, limit: int = 50,
                       sort_by: str = "cpu_percent") -> Dict[str, Any]:
        """List processes, optionally filtered by name, sorted by cpu/mem/pid."""
        if sort_by not in ("cpu_percent", "memory_percent", "pid"):
            return {"success": False, "error": f"sort_by must be cpu_percent, memory_percent, or pid."}
        limit = max(1, min(int(limit), 500))
        try:
            procs = list(psutil.process_iter())
        except Exception as e:
            app_logger.warning(f"process_iter failed: {e}")
            return {"success": False, "error": f"Could not enumerate processes: {e}"}

        rows = []
        for proc in procs:
            snap = cls._snapshot(proc)
            if filter and filter.lower() not in (snap.get("name") or "").lower():
                continue
            rows.append(snap)

        rows.sort(key=lambda r: r.get(sort_by) or 0, reverse=(sort_by != "pid"))
        return {"success": True, "count": len(rows), "processes": rows[:limit], "truncated": len(rows) > limit}

    @classmethod
    def get_process(cls, pid: int) -> Dict[str, Any]:
        """Detailed info for a single process by PID."""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return {"success": False, "error": "pid must be an integer."}
        if pid <= 0:
            return {"success": False, "error": "pid must be a positive integer."}
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"No process with PID {pid}."}
        snap = cls._snapshot(proc)
        if snap.get("status") == "gone":
            return {"success": False, "error": f"Process {pid} no longer exists.", **snap}
        return {"success": True, **snap}

    # ── write (Level 3) ─────────────────────────────────────────────────────
    @classmethod
    def kill_process(cls, pid: int, force: bool = False) -> Dict[str, Any]:
        """Terminate (SIGTERM) or force-kill (SIGKILL) a process by PID."""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return {"success": False, "error": "pid must be an integer."}

        guard = cls._guard(pid)
        if guard:
            return {"success": False, "error": guard}

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"No process with PID {pid}."}

        name = (proc.name() or "?") if proc.is_running() else "?"
        try:
            if force:
                proc.kill()
                audit_logger.info(f"Force-killed process {pid} ({name})")
            else:
                proc.terminate()
                audit_logger.info(f"Terminated process {pid} ({name})")
            return {"success": True, "pid": pid, "name": name, "force": force}
        except psutil.NoSuchProcess:
            return {"success": True, "pid": pid, "name": name, "force": force, "note": "Process already gone."}
        except psutil.AccessDenied as e:
            return {"success": False, "error": f"Permission denied killing {pid}: {e}"}

    @classmethod
    def restart_process(cls, pid: int) -> Dict[str, Any]:
        """Best-effort restart: re-launch the process from its recorded command line.

        This is inherently fragile (the command line may be relative to a cwd we
        can't recover, or the process may be a service). It kills the old process
        and re-spawns the command line as-is; on any failure it reports cleanly.
        """
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return {"success": False, "error": "pid must be an integer."}

        guard = cls._guard(pid)
        if guard:
            return {"success": False, "error": guard}

        try:
            proc = psutil.Process(pid)
            cmdline = proc.cmdline()
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"No process with PID {pid}."}
        except psutil.AccessDenied:
            return {"success": False, "error": f"Permission denied reading command line for {pid}."}

        if not cmdline:
            return {"success": False, "error": f"Process {pid} has no recoverable command line; cannot restart."}

        killed = cls.kill_process(pid)
        if not killed.get("success"):
            return {"success": False, "error": f"Could not stop {pid}: {killed.get('error')}"}

        try:
            subprocess.Popen(cmdline, start_new_session=True)
            audit_logger.info(f"Restarted process {pid} as: {' '.join(cmdline)[:200]}")
            return {"success": True, "pid": pid, "command": " ".join(cmdline)[:500]}
        except Exception as e:
            app_logger.warning(f"Restart spawn failed: {e}")
            return {"success": False, "error": f"Process stopped, but restart failed: {e}"}

    # ── safety guard ────────────────────────────────────────────────────────
    @staticmethod
    def _guard(pid: int) -> Optional[str]:
        """Refuse to kill protected PIDs. Returns an error string, or None if allowed."""
        if pid <= 1:
            return f"Refusing to kill PID {pid} (protected system process)."
        if pid == os.getpid():
            return "Refusing to kill the Arena process itself."
        return None
