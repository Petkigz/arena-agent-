import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.cognition.execution_control import run_cancellable_subprocess
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class AndroidADBController:
    @classmethod
    def run_adb_cmd(cls, args: List[str], target_device: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes an ADB (Android Debug Bridge) command against a connected Android device over USB/Wi-Fi.
        """
        try:
            cmd = ["adb"]
            if target_device:
                cmd.extend(["-s", target_device])
            cmd.extend(args)

            res = run_cancellable_subprocess(cmd, timeout=15)
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except Exception as e:
            app_logger.warning(f"ADB execution error: {e}")
            return {"success": False, "stdout": "", "stderr": f"ADB Error: {str(e)}"}

    @classmethod
    def is_adb_available(cls) -> bool:
        """
        Lightweight side-effect-free capability discovery check.
        Checks if ADB is executable and an authorized Android device is connected,
        without performing any user-facing operations or battery queries.
        """
        try:
            res = cls.list_connected_devices()
            devices = res.get("connected_android_devices", [])
            return res.get("success", False) and len(devices) > 0
        except Exception:
            return False

    @classmethod
    def make_phone_call(cls, phone_number: str, target_device: Optional[str] = None) -> Dict[str, Any]:
        """Initiates a phone call to phone_number over ADB."""
        clean_num = "".join(c for c in phone_number if c.isdigit() or c in "+*#")
        res = cls.run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{clean_num}"], target_device=target_device)
        audit_logger.info(f"Android ADB initiated phone call to '{clean_num}'")
        res["message"] = f"Initiated phone call to {clean_num}" if res["success"] else f"Failed to initiate call to {clean_num}"
        return res

    @classmethod
    def send_sms(cls, phone_number: str, message_text: str, target_device: Optional[str] = None) -> Dict[str, Any]:
        """Sends an SMS text message over ADB."""
        clean_num = "".join(c for c in phone_number if c.isdigit() or c in "+*#")
        res = cls.run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.SENDTO", "-d", f"sms:{clean_num}", "--es", "sms_body", message_text, "--ez", "exit_on_sent", "true"], target_device=target_device)
        audit_logger.info(f"Android ADB sent SMS to '{clean_num}': '{message_text[:30]}'")
        res["message"] = f"Sent SMS to {clean_num}" if res["success"] else f"Failed to send SMS to {clean_num}"
        return res

    @classmethod
    def get_battery_status(cls, target_device: Optional[str] = None) -> Dict[str, Any]:
        """Queries Android battery level & charging state over ADB."""
        res = cls.run_adb_cmd(["shell", "dumpsys", "battery"], target_device=target_device)
        level = "unknown"
        if res["success"] and res["stdout"]:
            for line in res["stdout"].split("\n"):
                if "level:" in line:
                    level = line.split(":", 1)[1].strip() + "%"
        res["message"] = f"Android Phone Battery Level: {level}" if res["success"] else "Could not query Android battery level"
        res["battery_level"] = level
        return res

    @classmethod
    def take_camera_photo(cls, target_device: Optional[str] = None) -> Dict[str, Any]:
        """Launches camera and triggers photo capture over ADB."""
        cls.run_adb_cmd(["shell", "am", "start", "-a", "android.media.action.IMAGE_CAPTURE"], target_device=target_device)
        res = cls.run_adb_cmd(["shell", "input", "keyevent", "27"], target_device=target_device)
        audit_logger.info("Captured Android camera photo via ADB shutter keyevent")
        res["message"] = "Captured camera photo on Android phone" if res["success"] else "Failed to capture photo"
        return res

    @classmethod
    def list_connected_devices(cls) -> Dict[str, Any]:
        """
        Lists all Android phones connected over USB or local Wi-Fi.
        """
        res = cls.run_adb_cmd(["devices"])
        # Owner review item 10 (2026-09-01): honest measurement. When the
        # adb binary cannot run at all, success=True with an empty list
        # would be a VACUOUS success — the /android/devices endpoint and
        # its unit test 'passed' while measuring nothing. Failure carries
        # the reason and the install path; adb-runs-but-no-device is a
        # genuine success with an empty list (a different, honest answer).
        if not res.get("success"):
            return {
                "success": False,
                "connected_android_devices": [],
                "adb_output": res.get("stdout", ""),
                "error": str(res.get("stderr", ""))[:200],
                "note": ("adb is not runnable on this machine — install "
                         "Android platform-tools (adb) on PATH, connect a "
                         "device over USB/Wi-Fi and authorize USB debugging "
                         "to enable Android control"),
            }
        devices = []
        if res["stdout"]:
            lines = res["stdout"].split("\n")[1:]
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])

        return {
            "success": True,
            "connected_android_devices": devices,
            "adb_output": res["stdout"]
        }

    @classmethod
    def tap_screen(cls, x: int, y: int, target_device: Optional[str] = None) -> Dict[str, Any]:
        """
        Taps coordinates (x, y) on Android phone screen.
        """
        res = cls.run_adb_cmd(["shell", "input", "tap", str(x), str(y)], target_device=target_device)
        audit_logger.info(f"Android ADB tap at ({x}, {y})")
        return res

    @classmethod
    def type_text(cls, text: str, target_device: Optional[str] = None) -> Dict[str, Any]:
        """
        Types text into Android input fields.
        """
        res = cls.run_adb_cmd(["shell", "input", "text", text.replace(" ", "%s")], target_device=target_device)
        audit_logger.info(f"Android ADB typed text: '{text}'")
        return res

    @classmethod
    def capture_phone_screenshot(cls, target_device: Optional[str] = None) -> Dict[str, Any]:
        """
        Captures screenshot from Android phone and saves to data/workspace/screenshots/phone_screen.png.
        """
        save_dir = settings.DATA_DIR / "workspace" / "screenshots"
        save_dir.mkdir(parents=True, exist_ok=True)
        local_path = save_dir / "phone_screen.png"

        try:
            # Take screenshot on phone SDCard
            cls.run_adb_cmd(["shell", "screencap", "-p", "/sdcard/phone_screen.png"], target_device=target_device)
            # Pull screenshot to PC
            pull_res = cls.run_adb_cmd(["pull", "/sdcard/phone_screen.png", str(local_path)], target_device=target_device)

            return {
                "success": pull_res["success"],
                "file_path": str(local_path),
                "image_url": "/static/workspace/screenshots/phone_screen.png",
                "message": "Captured Android phone screenshot successfully."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to capture phone screen: {str(e)}"}

    @classmethod
    def launch_android_app(cls, package_name: str, target_device: Optional[str] = None) -> Dict[str, Any]:
        """
        Launches an Android application by package name (e.g., com.whatsapp, com.android.settings).
        """
        res = cls.run_adb_cmd(["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"], target_device=target_device)
        audit_logger.info(f"Launched Android app: '{package_name}'")
        return res
