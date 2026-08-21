"""VisualObserver — deterministic "understand the screen" step for the vision loop.

The vision cognitive loop is:

    capture → OBSERVE (understand content) → reason → act → verify

`screen_capture` only saves a PNG; `_observe_screen_capture` in perception.py only
verified the file existed. That meant the loop stopped at "screenshot saved" and
never knew WHAT was on screen — the core gap in "screen capture alone ≠ vision".

This module closes the OBSERVE step deterministically (no LLM): it reads the
captured image and produces a structured `VisualObservation` carrying the actual
content (OCR text, image dimensions, whether there is readable content). The LLM
"understanding" remains a separate tool (`vision_analyze`) the model orchestrates;
this is the cheap, always-available, evidence-backed layer beneath it.

Degrades gracefully: missing file / missing tesseract / unreadable image all
produce a typed observation rather than raising, so it is safe inside the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.ocr_reader import OCRReaderTool
from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VisualObservation:
    """Structured, evidence-backed description of a captured screen."""
    timestamp: str
    file_path: str
    image_name: str
    has_content: bool          # True if OCR produced non-empty text
    visible_text: str          # OCR text (truncated)
    word_count: int
    width: Optional[int] = None
    height: Optional[int] = None
    error: str = ""            # degradation reason, if any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "image_name": self.image_name,
            "has_content": self.has_content,
            "visible_text": self.visible_text,
            "word_count": self.word_count,
            "width": self.width,
            "height": self.height,
            "error": self.error,
        }


class VisualObserver:
    MAX_TEXT_CHARS = 4000

    @classmethod
    def observe_screenshot(cls, file_path: str) -> VisualObservation:
        """Produce a structured observation of a screenshot's CONTENT (deterministic).

        Reads the image dimensions (Pillow) and OCR text (tesseract). Never raises.
        """
        p = Path(file_path)
        name = p.name or "screenshot"
        obs = VisualObservation(
            timestamp=_now(),
            file_path=str(p),
            image_name=name,
            has_content=False,
            visible_text="",
            word_count=0,
        )

        if not p.exists():
            obs.error = f"file not found: '{p}'"
            return obs

        # Image dimensions (best-effort, optional).
        try:
            from PIL import Image
            with Image.open(p) as img:
                obs.width, obs.height = img.size
        except Exception as e:
            app_logger.debug(f"VisualObserver: could not read image dims for {name}: {e}")

        # Content via OCR (deterministic; degrades if tesseract absent).
        ocr = OCRReaderTool.extract_text_from_image(str(p))
        if ocr.get("success"):
            text = (ocr.get("extracted_text") or "").strip()
            obs.visible_text = text[: cls.MAX_TEXT_CHARS]
            obs.word_count = int(ocr.get("word_count", len(obs.visible_text.split())))
            obs.has_content = bool(obs.visible_text)
        else:
            obs.error = ocr.get("error", "OCR unavailable")

        return obs
