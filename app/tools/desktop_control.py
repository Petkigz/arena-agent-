import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.tools.app_inventory import SystemAppInventory

class DesktopControl:
    @classmethod
    def launch_application(cls, app_key: str) -> Dict[str, Any]:
        """
        Launches ANY installed desktop application on Windows/Linux/macOS under Level 2 Safety Policy.
        """
        return SystemAppInventory.launch_any_app(app_key)

    @classmethod
    def list_approved_apps(cls) -> List[str]:
        defaults = ["vscode", "chrome", "firefox", "notepad", "calculator", "terminal", "lm_studio", "explorer"]
        scan_res = SystemAppInventory.scan_installed_applications()
        scanned_names = [a["app_name"].lower() for a in scan_res.get("applications", [])[:50]]
        return list(dict.fromkeys(defaults + scanned_names))

    @classmethod
    def open_url(cls, url: str) -> Dict[str, Any]:
        """
        Opens a target URL in default desktop web browser (or Firefox/Chrome).
        """
        import webbrowser
        try:
            webbrowser.open(url)
            audit_logger.info(f"Opened URL in desktop browser: '{url}'")
            return {
                "success": True,
                "url": url,
                "message": f"Successfully opened URL in browser: {url}"
            }
        except Exception as e:
            app_logger.error(f"Error opening URL: {e}")
            return {"success": False, "error": str(e)}

    # ── Desktop wallpaper (Windows; verified + reversible) ────────────────────
    _SPI_GETDESKWALLPAPER = 0x0073
    _SPI_SETDESKWALLPAPER = 0x0014
    _SPIF_UPDATEINIFILE = 0x01
    _SPIF_SENDCHANGE = 0x02
    _WALLPAPER_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}

    @classmethod
    def _current_wallpaper(cls):
        """Read the live wallpaper path via the native API, or None."""
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(512)
            if ctypes.windll.user32.SystemParametersInfoW(cls._SPI_GETDESKWALLPAPER, 512, buf, 0):
                value = buf.value.strip()
                return value or None
        except Exception as exc:
            app_logger.debug(f"Wallpaper read unavailable: {exc}")
        return None

    @classmethod
    def set_wallpaper(cls, image_path: str = "", path: str = "") -> Dict[str, Any]:
        """Set the desktop wallpaper (Level 2: reversible, verified by re-read).

        Reversibility: the previous wallpaper path is captured BEFORE the
        change and returned as the rollback path — re-running this tool with
        it restores the prior state. Verification is a re-read through the
        native API: command success alone never counts as applied.
        """
        import platform
        chosen = image_path or path
        if not chosen:
            return {
                "success": False, "side_effects": False,
                "error": "Image path required (e.g. set_wallpaper with image_path='C:/pics/wall.jpg').",
            }
        target = Path(str(chosen)).expanduser()
        if not target.is_file():
            return {"success": False, "side_effects": False,
                    "error": f"Image file not found: {target}"}
        if target.suffix.lower() not in cls._WALLPAPER_EXTS:
            return {"success": False, "side_effects": False,
                    "error": f"Not a supported image type ({target.suffix}); expected one of {sorted(cls._WALLPAPER_EXTS)}."}
        if platform.system().lower() != "windows":
            return {"success": False, "available": False, "attempted": False,
                    "error": "Wallpaper control is implemented for Windows (SystemParametersInfoW)."}

        try:
            import ctypes
            previous = cls._current_wallpaper()
            absolute = str(target.resolve())
            ok = bool(ctypes.windll.user32.SystemParametersInfoW(
                cls._SPI_SETDESKWALLPAPER, 0, absolute,
                cls._SPIF_UPDATEINIFILE | cls._SPIF_SENDCHANGE))
            observed = cls._current_wallpaper() if ok else None
            verified = bool(observed) and Path(observed).resolve() == Path(absolute).resolve() if observed else False
            if ok:
                audit_logger.info(f"Wallpaper set to {absolute} (verified={verified}, previous={previous})")
            return {
                "success": verified,
                "request_success": ok,
                "environment_verified": verified,
                "verification_unknown": ok and not verified,
                "image_path": absolute,
                "previous_wallpaper": previous,
                "rollback_supported": bool(previous),
                "rollback_reason": "Re-run set_wallpaper with the previous_wallpaper path to restore it.",
                "side_effects": ok,
            }
        except Exception as exc:
            app_logger.warning(f"Wallpaper change failed: {exc}")
            return {"success": False, "error": str(exc), "side_effects": False}
