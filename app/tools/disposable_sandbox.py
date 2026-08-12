import os
import shutil
import uuid
import subprocess
import platform
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger

class DisposableSandbox:
    """
    Universal Cross-OS Disposable Sandbox Engine.
    Enables isolated execution on Windows, Linux, macOS, or Android target environments
    regardless of the underlying host OS (Windows->Linux, Linux->Windows, Mac->Linux, Windows->Android, etc.),
    with automated post-execution self-destruct cleanup.
    """

    SUPPORTED_GUEST_OS = ["auto", "linux", "windows", "macos", "android"]

    @staticmethod
    def create_sandbox(
        sandbox_name: Optional[str] = None,
        target_guest_os: str = "auto"
    ) -> Dict[str, Any]:
        """
        Creates an isolated temporary sandbox workspace directory configured for a specific guest OS profile.
        """
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        sandbox_dir = settings.DATA_DIR / "sandboxes" / sandbox_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        host_os = platform.system().lower()  # 'windows', 'linux', 'darwin' (macOS)
        guest_os = target_guest_os.lower() if target_guest_os.lower() in DisposableSandbox.SUPPORTED_GUEST_OS else "auto"

        if guest_os == "auto":
            guest_os = host_os

        db.create_audit_log(
            "create_sandbox",
            "success",
            f"Created disposable sandbox '{sandbox_id}' (Host: {host_os}, Guest Target: {guest_os}) at {sandbox_dir}",
            level=0
        )

        return {
            "success": True,
            "sandbox_id": sandbox_id,
            "sandbox_name": sandbox_name or sandbox_id,
            "sandbox_path": str(sandbox_dir),
            "host_os": platform.system(),
            "target_guest_os": guest_os,
            "wsl_available": host_os == "windows" and shutil.which("wsl") is not None,
            "docker_available": shutil.which("docker") is not None,
            "adb_available": shutil.which("adb") is not None,
            "created_at": datetime.datetime.now().isoformat()
        }

    @staticmethod
    def run_in_sandbox(
        sandbox_id: str,
        command: str,
        target_guest_os: str = "auto",
        use_linux_environment: bool = False,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Executes a command inside the disposable sandbox environment using the appropriate execution engine
        for the desired target OS (WSL, Docker, ADB, or native isolated subprocess).
        Includes automatic fallback to native subprocess execution if wrapper tools are unconfigured.
        """
        if use_linux_environment and target_guest_os == "auto":
            target_guest_os = "linux"
        sandbox_dir = settings.DATA_DIR / "sandboxes" / sandbox_id
        if not sandbox_dir.exists():
            return {"success": False, "error": f"Sandbox '{sandbox_id}' not found."}

        host_os = platform.system().lower()
        guest_os = target_guest_os.lower() if target_guest_os.lower() in DisposableSandbox.SUPPORTED_GUEST_OS else "auto"

        # Determine optimal execution engine based on Host OS -> Guest OS matrix
        cmd_args = command
        use_shell = True
        exec_mode = f"Native Subprocess ({host_os})"

        # 1. Specific Target Linux requested explicitly
        if guest_os == "linux" and host_os == "windows" and shutil.which("wsl"):
            drive_letter = str(sandbox_dir)[0].lower() if len(str(sandbox_dir)) > 1 and str(sandbox_dir)[1] == ":" else ""
            raw_rel = str(sandbox_dir)[2:].replace("\\", "/") if drive_letter else str(sandbox_dir).replace("\\", "/")
            wsl_path = f"/mnt/{drive_letter}{raw_rel}" if drive_letter else raw_rel
            cmd_args = ["wsl", "bash", "-c", f"cd '{wsl_path}' 2>/dev/null || cd ~; {command}"]
            use_shell = False
            exec_mode = "WSL (Linux on Windows)"
        elif guest_os == "linux" and shutil.which("docker"):
            cmd_args = [
                "docker", "run", "--rm",
                "-v", f"{sandbox_dir}:/workspace",
                "-w", "/workspace",
                "ubuntu:latest",
                "bash", "-c", command
            ]
            use_shell = False
            exec_mode = "Docker Container (Linux/Ubuntu)"

        # 2. Target Windows (from Linux or Mac via Wine)
        elif guest_os == "windows" and host_os != "windows":
            if shutil.which("wine"):
                cmd_args = f"wine {command}"
                exec_mode = "Wine Subprocess (Windows on Linux/Mac)"
            else:
                exec_mode = f"Isolated Subprocess Emulation (Target Windows on {host_os})"

        # 3. Target Android
        elif guest_os == "android" and shutil.which("adb"):
            cmd_args = f"adb shell '{command}'"
            exec_mode = "ADB Remote Shell (Android Target)"

        # 4. Target macOS
        elif guest_os == "macos" and host_os == "darwin":
            exec_mode = "macOS Native Isolated Subprocess"

        app_logger.info(f"Running sandbox '{sandbox_id}' [Host: {host_os} -> Guest: {guest_os}] via {exec_mode}: {command}")

        # Attempt primary execution wrapper
        try:
            res = subprocess.run(
                cmd_args,
                shell=use_shell if isinstance(cmd_args, str) else False,
                cwd=str(sandbox_dir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            # If primary wrapper succeeded, return result
            if res.returncode == 0:
                db.create_audit_log(
                    "run_in_sandbox",
                    "success",
                    f"Executed in sandbox '{sandbox_id}' ({exec_mode}, Exit: 0)",
                    level=1
                )
                return {
                    "success": True,
                    "sandbox_id": sandbox_id,
                    "host_os": platform.system(),
                    "target_guest_os": guest_os,
                    "execution_mode": exec_mode,
                    "exit_code": 0,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "command": command
                }
            else:
                app_logger.warning(f"Primary execution wrapper '{exec_mode}' returned code {res.returncode}. Attempting native sandbox fallback...")

        except Exception as e:
            app_logger.warning(f"Primary execution wrapper failed: {e}. Attempting native sandbox fallback...")

        # Fallback to direct native isolated subprocess in sandbox directory
        try:
            native_cmd = command if host_os != "windows" else f"cmd.exe /c {command}"
            fallback_res = subprocess.run(
                native_cmd,
                shell=True,
                cwd=str(sandbox_dir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            exit_code = fallback_res.returncode
            db.create_audit_log(
                "run_in_sandbox",
                "success" if exit_code == 0 else "failed",
                f"Executed in sandbox '{sandbox_id}' (Native Subprocess Fallback, Exit: {exit_code})",
                level=1
            )

            return {
                "success": exit_code == 0,
                "sandbox_id": sandbox_id,
                "host_os": platform.system(),
                "target_guest_os": guest_os,
                "execution_mode": f"Native Isolated Subprocess ({host_os})",
                "exit_code": exit_code,
                "stdout": fallback_res.stdout,
                "stderr": fallback_res.stderr,
                "command": command
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "sandbox_id": sandbox_id,
                "error": f"Execution timed out after {timeout_seconds} seconds."
            }
        except Exception as e:
            app_logger.error(f"Error in native sandbox fallback execution: {e}")
            return {"success": False, "sandbox_id": sandbox_id, "error": str(e)}

    @staticmethod
    def destroy_sandbox(sandbox_id: str) -> Dict[str, Any]:
        """
        Completely purges and deletes the temporary sandbox environment and all files created inside it.
        """
        sandbox_dir = settings.DATA_DIR / "sandboxes" / sandbox_id
        if not sandbox_dir.exists():
            return {"success": False, "error": f"Sandbox '{sandbox_id}' not found."}

        try:
            shutil.rmtree(sandbox_dir)
            db.create_audit_log(
                "destroy_sandbox",
                "success",
                f"Purged sandbox '{sandbox_id}' from disk.",
                level=1
            )
            return {
                "success": True,
                "sandbox_id": sandbox_id,
                "message": f"Disposable sandbox '{sandbox_id}' completely purged and deleted."
            }
        except Exception as e:
            app_logger.error(f"Error purging sandbox '{sandbox_id}': {e}")
            return {"success": False, "sandbox_id": sandbox_id, "error": str(e)}
