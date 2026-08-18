import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
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

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
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
    def list_connected_devices(cls) -> Dict[str, Any]:
        """
        Lists all Android phones connected over USB or local Wi-Fi.
        """
        res = cls.run_adb_cmd(["devices"])
        devices = []
        if res["success"] and res["stdout"]:
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
