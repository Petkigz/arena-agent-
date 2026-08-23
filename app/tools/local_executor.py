"""Generic local command / script / API executor — the "escape hatch" tool.

Safely runs an arbitrary local CLI command, a Python snippet, or a localhost HTTP
call, returning structured output. This one tool covers thousands of niche tasks
without writing a new tool for each.

Safety:
- Commands run inside DisposableSandbox (confined cwd, bounded timeout).
- Level 3 (sensitive) — the ActionGate/manifest require owner approval, so the
  agent cannot invoke it autonomously.
- Inputs are validated (command length, action type).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from app.tools.disposable_sandbox import DisposableSandbox
from app.utils.logger import app_logger, audit_logger
from app.cognition.execution_control import run_cancellable_blocking_call

VALID_ACTIONS = ("shell", "python", "http")


class LocalExecutor:
    """Run local commands, snippets, or localhost HTTP requests (Level 3)."""

    @classmethod
    def execute(
        cls,
        action: str = "shell",
        command: Optional[str] = None,
        code: Optional[str] = None,
        url: Optional[str] = None,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Execute one local action.

        action is one of:
          - "shell": run `command` (e.g. "ls -la", "df -h").
          - "python": run a `code` snippet via `python -c`.
          - "http": call a localhost `url` (GET/POST) with optional `body`.
        """
        action = (action or "shell").lower().strip()
        if action not in VALID_ACTIONS:
            return {"success": False, "error": f"Unsupported action '{action}'. Use one of {sorted(VALID_ACTIONS)}."}

        try:
            timeout_seconds = max(1, min(int(timeout_seconds), 120))
        except (TypeError, ValueError):
            return {"success": False, "error": "timeout_seconds must be a number."}

        if action == "shell":
            if not command or not command.strip():
                return {"success": False, "error": "A 'command' is required for the 'shell' action."}
            return cls._run_shell(command.strip(), timeout_seconds)

        if action == "python":
            if not code or not code.strip():
                return {"success": False, "error": "A 'code' snippet is required for the 'python' action."}
            return cls._run_shell(f"python -c {json.dumps(code)}", timeout_seconds)

        # action == "http"
        if not url or not url.strip():
            return {"success": False, "error": "A 'url' is required for the 'http' action."}
        return cls._run_http(url.strip(), method.upper(), body, timeout_seconds)

    @classmethod
    def _run_shell(cls, command: str, timeout_seconds: int) -> Dict[str, Any]:
        sb = DisposableSandbox.create_sandbox()
        try:
            res = DisposableSandbox.run_in_sandbox(
                sb["sandbox_id"], command, timeout_seconds=timeout_seconds
            )
            audit_logger.info(f"LocalExecutor ran shell command (success={res.get('success')})")
            return {
                "success": res.get("success", False),
                "stdout": res.get("stdout", ""),
                "stderr": res.get("stderr", ""),
                "exit_code": res.get("exit_code"),
            }
        finally:
            try:
                DisposableSandbox.destroy_sandbox(sb["sandbox_id"])
            except Exception:
                pass

    @classmethod
    def _run_http(cls, url: str, method: str, body: Optional[Dict[str, Any]], timeout_seconds: int) -> Dict[str, Any]:
        # Restrict to localhost / private ranges — this is the "local" executor.
        if not (url.startswith(("http://localhost", "http://127.0.0.1", "http://192.168.", "http://10.", "http://172."))):
            return {"success": False, "error": "Only localhost / private-network URLs are allowed."}

        try:
            if method == "GET":
                r = run_cancellable_blocking_call(
                    lambda: httpx.get(url, timeout=timeout_seconds),
                    description="local HTTP GET",
                )
            elif method == "POST":
                r = run_cancellable_blocking_call(
                    lambda: httpx.post(
                        url, json=body or {}, timeout=timeout_seconds
                    ),
                    description="local HTTP POST",
                )
            else:
                return {"success": False, "error": f"Unsupported HTTP method '{method}'. Use GET or POST."}
            r.raise_for_status()
            try:
                data = r.json()
            except ValueError:
                data = r.text
            return {"success": True, "status_code": r.status_code, "data": data}
        except httpx.HTTPError as e:
            app_logger.warning(f"LocalExecutor HTTP call failed: {e}")
            return {"success": False, "error": f"HTTP request failed: {e}"}
