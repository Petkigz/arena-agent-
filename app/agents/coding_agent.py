"""Coding Agent — a specialized multi-step agent for code tasks.

This is a *loop*, not a tool: it plans → checkpoints (a "branch") → writes code →
verifies (runs tests in a sandbox) → branches/retries on failure → rolls back on
total failure. It leans on deterministic tools (sandbox, git checkpoints, test
generation) so the weak local model only does small reasoning steps, while
correctness is checked by *running the code*, not by trusting the model.

Design (honest, testable):
- All LLM calls go through `llm_client` and can be injected for tests.
- Verification is deterministic: tests run in DisposableSandbox.
- Git checkpoints/rollback are best-effort (wrapped) so the agent works even
  where git isn't available.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.llm import llm_client, extract_reply
from app.tools.disposable_sandbox import DisposableSandbox
from app.tools.git_manager import GitManagerTool
from app.utils.logger import app_logger, audit_logger


class CodingAgent:
    """Plan → write → verify → branch → rollback loop for code tasks."""

    def __init__(
        self,
        workdir: Optional[str] = None,
        max_attempts: int = 3,
        checkpoint_enabled: bool = True,
        llm=None,
    ) -> None:
        self.workdir = Path(workdir) if workdir else Path(settings.BASE_DIR)
        self.max_attempts = max(1, min(int(max_attempts), 5))
        self.checkpoint_enabled = checkpoint_enabled
        self._llm = llm or llm_client

    # ── main loop ───────────────────────────────────────────────────────────
    def run(
        self,
        task: str,
        target_file: Optional[str] = None,
        test_command: Optional[str] = None,
        context_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute the coding task, iterating until tests pass or attempts run out."""
        if not task or not task.strip():
            return {"success": False, "error": "A task description is required."}

        context = self._read_context(context_files or [])
        attempts: List[Dict[str, Any]] = []
        checkpoint_hash: Optional[str] = None

        if self.checkpoint_enabled:
            checkpoint_hash = self._checkpoint(task)

        for attempt in range(1, self.max_attempts + 1):
            app_logger.info(f"CodingAgent attempt {attempt}/{self.max_attempts} for '{task[:60]}'")

            plan = self._plan(task, context, attempts)
            code = self._generate_code(task, plan, context, attempts)

            if not code:
                attempts.append({"attempt": attempt, "error": "Model produced no code."})
                continue

            write_result = self._write_code(target_file, code)
            attempts.append({"attempt": attempt, "plan": plan, "write": write_result})

            if test_command:
                verify = self._run_tests(test_command)
                attempts[-1]["verify"] = verify
                if verify.get("success"):
                    audit_logger.info(f"CodingAgent succeeded on attempt {attempt}")
                    return self._success_result(task, target_file, attempts, checkpoint_hash)
                # Failure → feed the error back and branch to the next attempt.
                app_logger.warning(f"Attempt {attempt} failed tests: {verify.get('stderr', '')[:200]}")
                if self.checkpoint_enabled and checkpoint_hash:
                    self._rollback(checkpoint_hash)
                continue

            # No test command: treat as "wrote code" success (best-effort).
            audit_logger.info(f"CodingAgent wrote code for '{task}' (no test command)")
            return self._success_result(task, target_file, attempts, checkpoint_hash)

        return {
            "success": False,
            "task": task,
            "attempts": attempts,
            "message": f"Failed after {self.max_attempts} attempts.",
        }

    # ── deterministic helpers (testable) ────────────────────────────────────
    def _read_context(self, files: List[str]) -> str:
        ctx = []
        for f in files:
            p = self.workdir / f
            if p.exists():
                try:
                    ctx.append(f"--- {f} ---\n{p.read_text(encoding='utf-8')[:4000]}")
                except Exception as e:
                    app_logger.warning(f"Could not read context file {f}: {e}")
        return "\n".join(ctx)

    def _checkpoint(self, task: str) -> Optional[str]:
        try:
            res = GitManagerTool.create_checkpoint(f"coding-agent: {task[:40]}")
            if res.get("success"):
                # Return the latest commit hash if available.
                cps = GitManagerTool.list_checkpoints(limit=1)
                if cps:
                    return cps[0]["hash"]
            return None
        except Exception as e:
            app_logger.warning(f"Checkpoint failed (continuing): {e}")
            return None

    def _rollback(self, checkpoint_hash: str) -> None:
        try:
            GitManagerTool.rollback_checkpoint(checkpoint_hash)
        except Exception as e:
            app_logger.warning(f"Rollback failed (continuing): {e}")

    def _run_tests(self, test_command: str) -> Dict[str, Any]:
        sb = DisposableSandbox.create_sandbox()
        try:
            return DisposableSandbox.run_in_sandbox(
                sb["sandbox_id"], test_command, timeout_seconds=60
            )
        finally:
            try:
                DisposableSandbox.destroy_sandbox(sb["sandbox_id"])
            except Exception:
                pass

    def _write_code(self, target_file: Optional[str], code: str) -> Dict[str, Any]:
        if not target_file:
            # No target file → write to a generated file in the workdir.
            target_file = f"data/workspace/coding_agent_output.py"
        path = self.workdir / target_file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── LLM steps (injectable, keep the model's reasoning minimal) ──────────
    def _plan(self, task: str, context: str, attempts: List[Dict[str, Any]]) -> str:
        failures = "\n".join(
            a.get("verify", {}).get("stderr", "")[:400] for a in attempts if a.get("verify") and not a["verify"].get("success")
        )
        system = (
            "You are a senior software engineer. Produce a concise implementation "
            "plan for the task. If there were prior failed attempts, address the "
            "specific test errors listed. Output ONLY the plan, no code."
        )
        user = f"Task: {task}\n\nExisting context:\n{context}\n\nPrior test failures:\n{failures or '(none)'}"
        return extract_reply(self._llm.generate_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            complexity="main", max_tokens=600,
        ), fallback="Implement the task directly.")

    def _generate_code(self, task: str, plan: str, context: str, attempts: List[Dict[str, Any]]) -> str:
        failures = "\n".join(
            a.get("verify", {}).get("stderr", "")[:400] for a in attempts if a.get("verify") and not a["verify"].get("success")
        )
        system = (
            "You are a senior software engineer. Write complete, correct, runnable "
            "code for the task. Output ONLY the code (no explanation, no markdown fences). "
            "If a prior attempt failed tests, fix the specific errors."
        )
        user = (
            f"Task: {task}\n\nPlan:\n{plan}\n\nExisting context:\n{context}\n\n"
            f"Prior test failures:\n{failures or '(none)'}\n\nCode:"
        )
        code = extract_reply(self._llm.generate_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            complexity="main", max_tokens=2000,
        ), fallback="")
        # Strip markdown fences if the model wrapped the code anyway.
        return self._strip_fences(code)

    @staticmethod
    def _strip_fences(code: str) -> str:
        code = code.strip()
        for fence in ("```python", "```"):
            if code.startswith(fence):
                code = code[len(fence):].lstrip("\n")
        if code.endswith("```"):
            code = code[:-3].rstrip()
        return code.strip()

    def _success_result(self, task, target_file, attempts, checkpoint_hash) -> Dict[str, Any]:
        return {
            "success": True,
            "task": task,
            "target_file": target_file,
            "attempts": len(attempts),
            "checkpoint": checkpoint_hash,
            "history": attempts,
        }
