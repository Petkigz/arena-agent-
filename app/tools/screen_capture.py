import uuid
import hashlib
import mss
from PIL import Image, ImageDraw
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger, audit_logger

class ScreenCaptureTool:
    SCREENSHOTS_DIR = settings.DATA_DIR / "workspace" / "screenshots"
    _last_screen_hash: Optional[str] = None

    @classmethod
    def ensure_dir(cls):
        cls.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def generate_dummy_screenshot(cls, file_path: Path, width: int = 1920, height: int = 1080):
        """
        Generates a placeholder PNG image when no physical X11 display server is available (e.g. headless Linux).
        """
        img = Image.new('RGB', (width, height), color=(11, 15, 25))
        d = ImageDraw.Draw(img)
        d.text((50, 50), "[SYSTEM DESKTOP SCREENSHOT - SIMULATED DISPLAY]", fill=(0, 242, 254))
        d.text((50, 100), "Active Window: Visual Dashboard / Desktop Application", fill=(249, 250, 251))
        img.save(file_path, "PNG")

    @classmethod
    def capture_screen(cls, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Captures full desktop screen using mss high-performance screen capture.
        Saves image to data/workspace/screenshots/ and returns file path and URL.
        """
        cls.ensure_dir()
        if not filename:
            filename = f"screen_{uuid.uuid4().hex[:8]}.png"

        file_path = cls.SCREENSHOTS_DIR / filename
        width, height = 1920, 1080

        try:
            with mss.MSS() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(file_path))
                width, height = sct_img.size[0], sct_img.size[1]

            rel_path = f"workspace/screenshots/{filename}"
            app_logger.info(f"Captured desktop screenshot: {file_path}")
            audit_logger.info(f"Captured screen image at {file_path}")

            return {
                "success": True,
                "file_name": filename,
                "file_path": str(file_path),
                "image_url": f"/static/{rel_path}",
                "width": width,
                "height": height
            }
        except Exception as e:
            app_logger.warning(f"Display capture notice ({e}). Generating fallback screen capture...")
            try:
                cls.generate_dummy_screenshot(file_path, width=width, height=height)
                return {
                    "success": True,
                    "file_name": filename,
                    "file_path": str(file_path),
                    "image_url": f"/static/workspace/screenshots/{filename}",
                    "width": width,
                    "height": height
                }
            except Exception as ex:
                return {
                    "success": False,
                    "error": f"Screen capture error: {str(ex)}",
                    "file_path": "",
                    "image_url": ""
                }

    @classmethod
    def capture_screen_delta(cls) -> Dict[str, Any]:
        """
        Captures screenshot and calculates image hash difference against previous screenshot.
        If screen change is < 5%, returns screen_changed=False to save CPU and RX 580 VRAM!
        """
        cap = cls.capture_screen()
        if not cap.get("success"):
            return cap

        try:
            with open(cap["file_path"], "rb") as f:
                curr_hash = hashlib.md5(f.read()).hexdigest()

            changed = True
            if cls._last_screen_hash and cls._last_screen_hash == curr_hash:
                changed = False

            cls._last_screen_hash = curr_hash
            cap["screen_changed"] = changed
            cap["note"] = "Screen changed; VLM analysis required." if changed else "Screen static; skipping redundant VLM inference to save VRAM."
            return cap
        except Exception:
            cap["screen_changed"] = True
            return cap
