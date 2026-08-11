import os
import sys
import subprocess
from typing import Dict, Any, List
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class DesktopControl:
    APPROVED_APPS: Dict[str, List[str]] = {
        "vscode": ["code"],
        "chrome": ["chrome", "google-chrome", "google-chrome-stable"],
        "lm_studio": ["lm-studio", "LM Studio"],
        "notepad": ["notepad"],
        "calculator": ["calc", "calculator"],
        "explorer": ["explorer"],
        "terminal": ["powershell", "cmd", "bash", "gnome-terminal"]
    }

    @classmethod
    def launch_application(cls, app_key: str) -> Dict[str, Any]:
        """
        Launches an approved local desktop application on Windows/Linux under Level 2 Safety Policy.
        """
        app_key_clean = app_key.lower().strip()

        # Policy Evaluation: Level 2 Reversible Desktop Action
        allowed, reason, level = PolicyEvaluator.evaluate_action("open_application", {"app_name": app_key_clean})
        if not allowed:
            return {
                "success": False,
                "error": f"Policy Blocked: {reason}",
                "authority_level": level,
                "app_name": app_key_clean
            }

        # Check if app is in approved list
        exec_candidates = cls.APPROVED_APPS.get(app_key_clean, [app_key_clean])

        for cmd in exec_candidates:
            try:
                app_logger.info(f"Attempting to launch desktop app: '{cmd}'...")
                if sys.platform == "win32":
                    subprocess.Popen(f"start {cmd}", shell=True)
                else:
                    subprocess.Popen([cmd])

                audit_logger.info(f"Launched approved desktop application: '{app_key_clean}'")
                return {
                    "success": True,
                    "app_name": app_key_clean,
                    "command_executed": cmd,
                    "message": f"Successfully launched application '{app_key_clean}'."
                }
            except Exception as e:
                app_logger.warning(f"Could not launch command '{cmd}': {e}")

        return {
            "success": False,
            "error": f"Could not launch application '{app_key_clean}'. Make sure the app is installed and on system PATH.",
            "app_name": app_key_clean
        }

    @classmethod
    def list_approved_apps(cls) -> List[str]:
        return list(cls.APPROVED_APPS.keys())
