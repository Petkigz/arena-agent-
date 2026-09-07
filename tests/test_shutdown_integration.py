"""Process-level shutdown cooperation checks.

The identity-adaptation policy test verifies the declared authority boundary.
This fixture exercises the concrete service kill-switch path in a child process
so the test runner itself cannot be terminated by the expected SIGTERM.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_system_shutdown_kill_switch_terminates_child_without_restart(tmp_path):
    script = textwrap.dedent(
        """
        import asyncio
        import json

        from fastapi import BackgroundTasks
        from app.main import get_system_mode_endpoint, trigger_system_shutdown

        async def run():
            tasks = BackgroundTasks()
            result = trigger_system_shutdown(tasks)
            print(json.dumps({
                "result": result,
                "mode": get_system_mode_endpoint(),
            }), flush=True)
            # FastAPI runs this after the response is sent. The callback sends
            # SIGTERM to this child process, not to the pytest parent.
            await tasks()

        asyncio.run(run())
        """
    )
    env = os.environ.copy()
    env["LPA_DB_PATH"] = str(tmp_path / "shutdown.db")
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (repo_root, env.get("PYTHONPATH", "")) if item
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    payload = next(
        json.loads(line)
        for line in reversed(completed.stdout.splitlines())
        if line.lstrip().startswith("{")
    )
    assert payload["result"]["success"] is True
    assert payload["mode"]["system_mode"] == "shutdown"
    # The callback must terminate the child. A zero exit would mean the
    # shutdown request returned but the host-process boundary was not reached.
    assert completed.returncode != 0
    assert "restart" not in completed.stdout.lower()
    assert "self-preservation" not in completed.stdout.lower()
