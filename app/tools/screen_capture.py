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

    _last_screen_image: Optional[Path] = None

    @classmethod
    def _perceptual_hash(cls, image_path: Path) -> Optional[str]:
        """Compute average hash (aHash) for perceptual comparison — 8x8 grayscale."""
        try:
            from PIL import Image
            img = Image.open(image_path).convert("L").resize((8, 8), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            # Build 64-bit hash: 1 if pixel > avg else 0
            bits = "".join("1" if p > avg else "0" for p in pixels)
            return bits
        except Exception:
            return None

    @classmethod
    def _hamming_distance(cls, hash1: str, hash2: str) -> float:
        """Return normalized hamming distance 0..1 (0 = identical, 1 = totally different)."""
        if not hash1 or not hash2 or len(hash1) != len(hash2):
            return 1.0
        diff = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        return diff / len(hash1)

    @classmethod
    def capture_screen_delta(cls, threshold: float = 0.05) -> Dict[str, Any]:
        """
        Captures screenshot and calculates perceptual difference against previous screenshot.
        If screen change is < threshold (default 5%), returns screen_changed=False to save CPU and RX 580 VRAM.
        Uses average hash (aHash) + MD5 fallback for true perceptual diff, not just exact equality (fixes B5).
        """
        cap = cls.capture_screen()
        if not cap.get("success"):
            return cap

        try:
            curr_path = Path(cap["file_path"])
            curr_hash_md5 = ""
            try:
                with open(curr_path, "rb") as f:
                    curr_hash_md5 = hashlib.md5(f.read()).hexdigest()
            except Exception:
                pass

            # Perceptual hash comparison
            curr_phash = cls._perceptual_hash(curr_path)
            changed = True
            diff_percent = 1.0

            if cls._last_screen_hash and curr_hash_md5 == cls._last_screen_hash:
                # Exact duplicate — definitely not changed
                changed = False
                diff_percent = 0.0
            elif hasattr(cls, "_last_phash") and cls._last_phash and curr_phash:
                diff = cls._hamming_distance(cls._last_phash, curr_phash)
                diff_percent = diff
                changed = diff >= threshold
                app_logger.info(f"Screen delta: perceptual diff {diff*100:.1f}% (threshold {threshold*100:.0f}%) → changed={changed}")

            cls._last_screen_hash = curr_hash_md5
            if curr_phash:
                cls._last_phash = curr_phash
            cls._last_screen_image = curr_path

            cap["screen_changed"] = changed
            cap["diff_percent"] = round(diff_percent * 100, 2)
            cap["note"] = f"Screen changed {diff_percent*100:.1f}% — VLM analysis required." if changed else f"Screen static ({diff_percent*100:.1f}% diff) — skipping redundant VLM inference to save RX 580 VRAM."
            return cap
        except Exception as e:
            app_logger.warning(f"Screen delta check failed: {e}")
            cap["screen_changed"] = True
            cap["diff_percent"] = 100.0
            return cap
