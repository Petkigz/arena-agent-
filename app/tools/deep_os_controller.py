import sys
import os
import re
from typing import Dict, Any, List, Optional
from app.cognition.execution_control import run_cancellable_subprocess
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

# SECURITY: package names must match a conservative identifier pattern so they
# cannot inject shell metacharacters (;, &&, |, $(), backticks, etc.).
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+@-]{0,127}$")

class DeepOSController:
    @classmethod
    def mouse_click(cls, x: int, y: int, double: bool = False) -> Dict[str, Any]:
        """
        Executes a GUI mouse click at (x, y) screen coordinates.
        """
        try:
            import pyautogui
            if double:
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.click(x, y)
            audit_logger.info(f"Mouse click at ({x}, {y})")
            return {"success": True, "action": "click", "x": x, "y": y}
        except Exception as e:
            app_logger.warning(f"PyAutoGUI display click unavailable: {e}")
            return {
                "success": False,
                "available": False,
                "attempted": False,
                "error": f"Mouse click unavailable: {e}",
                "x": x,
                "y": y,
            }

    @classmethod
    def type_text(cls, text: str) -> Dict[str, Any]:
        """
        Types text onto active desktop input window.
        """
        try:
            import pyautogui
            pyautogui.write(text, interval=0.02)
            audit_logger.info(f"Typed text: '{text[:50]}'")
            return {"success": True, "typed_text": text}
        except Exception as e:
            app_logger.warning(f"PyAutoGUI typing unavailable: {e}")
            return {
                "success": False,
                "available": False,
                "attempted": False,
                "error": f"Text typing unavailable: {e}",
            }

    @classmethod
    def press_hotkey(cls, keys: List[str]) -> Dict[str, Any]:
        """
        Presses a key combination (e.g. ['ctrl', 'c'] or ['alt', 'tab'] or ['win', 'r']).
        """
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            audit_logger.info(f"Pressed hotkey combination: {keys}")
            return {"success": True, "hotkey": keys}
        except Exception as e:
            app_logger.warning(f"PyAutoGUI hotkey unavailable: {e}")
            return {
                "success": False,
                "available": False,
                "attempted": False,
                "error": f"Hotkey unavailable: {e}",
                "keys": keys,
            }

    @classmethod
    def check_and_update_software(cls, package_name: str = "vlc") -> Dict[str, Any]:
        """
        Checks for software updates (e.g., VLC) using native package managers (winget/apt/brew)
        and initiates update under Level 3 Policy Approval.
        """
        # SECURITY: reject package names with shell metacharacters BEFORE any
        # policy evaluation or subprocess construction (no shell=True).
        if not isinstance(package_name, str) or not _PACKAGE_NAME_RE.match(package_name):
            app_logger.warning(f"Rejected software-update request with unsafe package name: {package_name!r}")
            return {
                "success": False,
                "error": "Invalid package name (unsafe characters).",
                "package": str(package_name)[:64],
            }

        # Policy Evaluation: Software installation / updates require Level 3 approval
        allowed, reason, level = PolicyEvaluator.evaluate_action("system_update", {"package": package_name})
        if not allowed:
            return {
                "success": False,
                "error": f"Policy Blocked: {reason}",
                "authority_level": level,
                "package": package_name,
                "note": "Software updates require explicit user approval (Level 3)."
            }

        try:
            app_logger.info(f"Checking for software update for '{package_name}'...")
            # Argument-list form (no shell) — package_name is validated above and
            # passed as a single argv element, so it cannot be interpreted by a shell.
            if sys.platform == "win32":
                args = ["winget", "upgrade", "--id", package_name,
                        "--accept-source-agreements", "--accept-package-agreements"]
            elif sys.platform == "darwin":
                args = ["brew", "upgrade", package_name]
            else:
                args = ["sudo", "apt", "install", "--only-upgrade", "-y", package_name]

            res = run_cancellable_subprocess(args, timeout=30)
            audit_logger.info(f"Software update command executed for '{package_name}'")

            return {
                "success": res.returncode == 0,
                "package": package_name,
                "output": res.stdout[:2000] if res.stdout else res.stderr[:2000],
                "command": " ".join(args)
            }
        except Exception as e:
            app_logger.error(f"Error checking update for '{package_name}': {e}")
            return {"success": False, "error": f"Update error: {str(e)}", "package": package_name}
