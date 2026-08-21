"""Native webcam capture (browser-free).

Captures still photos directly from the desktop webcam using OpenCV — no browser,
no getUserMedia permission prompt, no HTTPS requirement. The browser UI can never
touch the camera directly; this native tool does.

Gracefully degrades: if OpenCV or a camera device is unavailable, it returns a
clear failure result instead of crashing the pipeline.
"""

import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False
    app_logger.warning("OpenCV not installed. Webcam capture unavailable. Install with: pip install opencv-python")


class CameraCaptureTool:
    """Native desktop webcam capture."""

    PHOTOS_DIR = settings.DATA_DIR / "workspace" / "photos"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_available(cls) -> bool:
        """Whether a webcam is actually reachable (OpenCV + a camera device)."""
        if not CV2_AVAILABLE:
            return False
        try:
            cap = cv2.VideoCapture(0)
            ok = cap.isOpened()
            cap.release()
            return ok
        except Exception:
            return False

    @classmethod
    def capture_photo(
        cls,
        filename: Optional[str] = None,
        width: int = 1280,
        height: int = 720,
    ) -> Dict[str, Any]:
        """
        Capture a single frame from the default webcam (device 0).

        Returns a dict with success, file_path, and image_url on success.
        """
        cls.ensure_dir()
        if not filename:
            filename = f"photo_{uuid.uuid4().hex[:8]}.jpg"

        file_path = cls.PHOTOS_DIR / filename

        if not CV2_AVAILABLE:
            return {
                "success": False,
                "error": "OpenCV not installed. Run: pip install opencv-python",
                "file_path": "",
                "image_url": "",
            }

        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                cap.release()
                return {
                    "success": False,
                    "error": "No webcam device found (device 0 could not be opened).",
                    "file_path": "",
                    "image_url": "",
                }

            # Request a reasonable capture size (best-effort).
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            ok, frame = cap.read()
            cap.release()

            if not ok or frame is None:
                return {
                    "success": False,
                    "error": "Failed to read a frame from the webcam.",
                    "file_path": "",
                    "image_url": "",
                }

            cv2.imwrite(str(file_path), frame)

            h, w = frame.shape[:2]
            rel_path = f"workspace/photos/{filename}"
            app_logger.info(f"Captured webcam photo: {file_path}")
            audit_logger.info(f"Captured webcam photo at {file_path}")

            return {
                "success": True,
                "file_name": filename,
                "file_path": str(file_path),
                "image_url": f"/static/{rel_path}",
                "width": w,
                "height": h,
            }

        except Exception as e:
            app_logger.error(f"Webcam capture error: {e}")
            return {
                "success": False,
                "error": f"Webcam capture error: {str(e)}",
                "file_path": "",
                "image_url": "",
            }
