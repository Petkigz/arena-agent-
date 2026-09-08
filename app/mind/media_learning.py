"""MediaLearning — Phase 8 (Beanie AGI roadmap): learning from images,
video, and web media.

Roadmap tree: audio/speech/frames/OCR/objects/UI elements/actions/temporal
relationships/context → understanding → procedure inference → concept
extraction → knowledge candidate. This phase builds the honest foundation of
that tree:

- deterministic observation FIRST — file facts via PIL, YouTube transcripts
  without an LLM, web scraping without an LLM, OCR only when a tesseract
  binary actually exists;
- the EXISTING LLM analysers (``YouTubeLearner``, ``UniversalMediaLearner``)
  stay the deep-analysis capabilities; this organ turns observations (and,
  on request, their analyses) into experiences for the Phase-6 door;
- the Phase-6 loop then does what it does for every experience: compare,
  novelty, store (deduped), ledger — media is another EXPERIENCE KIND, not
  another loop.

Honesty rules:
- watching is not verification: media experiences ALWAYS carry success=None;
- every failure is typed (no transcript, unreadable image, OCR binary
  missing, model unavailable) — deterministic facts still land when they
  are real, and nothing is fabricated when they are not;
- provenance rides along: the stored record names the source target.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
_MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".wav", ".mp3",
               ".m4a", ".flac", ".ogg"}
TRANSCRIPT_SAMPLE = 400
CONTENT_BUDGET = 800


class MediaLearning:
    """Media experiences enter the one learning loop through here."""

    def __init__(self, mind: Any) -> None:
        self.mind = mind

    # ── the door ─────────────────────────────────────────────────────────
    def learn_from_media(self, target: str, focus: Optional[str] = None,
                         context: Optional[str] = None,
                         deep: bool = False) -> Dict[str, Any]:
        """Observe one media target and run the experience through the
        Phase-6 loop. ``deep=True`` additionally asks the existing LLM
        analysers for a summary (may fail honestly when no model is
        loaded)."""
        target = str(target or "").strip()
        if not target:
            return {"success": False, "reason": "no media target given"}
        kind = self._classify(target)
        if kind == "youtube":
            return self._learn_youtube(target, focus=focus,
                                       context=context, deep=deep)
        if kind == "image":
            return self._learn_image(target, context=context)
        if kind == "media_file":
            return self._learn_media_file(target, context=context)
        if kind == "web":
            return self._learn_web(target, focus=focus, context=context)
        return {"success": False,
                "reason": f"unsupported media target: '{target[:120]}'",
                "supported": "YouTube URL, image file, audio/video file, "
                             "web URL"}

    @staticmethod
    def _classify(target: str) -> str:
        low = target.lower()
        if "youtube.com" in low or "youtu.be" in low:
            return "youtube"
        if os.path.isfile(target):
            ext = os.path.splitext(target)[1].lower()
            if ext in _IMAGE_EXTS:
                return "image"
            if ext in _MEDIA_EXTS:
                return "media_file"
            return "unsupported"
        if re.match(r"^https?://", low):
            return "web"
        return "unsupported"

    # ── YouTube: transcript first (no LLM), deep analysis optional ────────
    def _learn_youtube(self, target: str, focus: Optional[str],
                       context: Optional[str], deep: bool) -> Dict[str, Any]:
        from app.tools.youtube_learner import YouTubeLearner
        try:
            t = YouTubeLearner.get_transcript(target)
        except Exception as exc:
            return {"success": False, "kind": "youtube",
                    "reason": f"transcript fetch failed: {exc}"}
        if not t.get("success") or not t.get("transcript"):
            return {"success": False, "kind": "youtube",
                    "reason": str(t.get("error") or "no transcript available")}
        transcript = str(t["transcript"])
        terms = _terms(transcript)[:10]
        parts = [f"YouTube video {t.get('video_id')}: concepts — "
                 f"{', '.join(terms) if terms else '(none extracted)'}."]
        parts.append(f"Transcript sample: {transcript[:TRANSCRIPT_SAMPLE]}")
        if context:
            parts.append(f"Owner context: {str(context)[:200]}")
        summary = ""
        if deep:
            try:
                res = YouTubeLearner.learn_from_video(target, prompt_focus=focus)
                if res.get("success") and res.get("ai_summary"):
                    summary = str(res["ai_summary"])[:300]
                    parts.append(f"Analysis: {summary}")
            except Exception as exc:
                app_logger.warning(f"Deep YouTube analysis skipped: {exc}")
        return self._submit(source_kind="youtube", target=target,
                            content=" ".join(parts)[:CONTENT_BUDGET],
                            facts={"video_id": t.get("video_id"),
                                   "transcript_chars": len(transcript),
                                   "terms": terms,
                                   "deep_analysis": bool(summary)})

    # ── images: deterministic facts + OCR when honestly available ────────
    def _learn_image(self, target: str, context: Optional[str]) -> Dict[str, Any]:
        facts = self._image_facts(target)
        if not facts.get("success"):
            return {"success": False, "kind": "image",
                    "reason": facts.get("reason", "unreadable image")}
        parts = [f"Image {os.path.basename(target)}: {facts['format']} "
                 f"{facts['width']}x{facts['height']} {facts['mode']}."]
        ocr = self._ocr(target)
        if ocr:
            parts.append(f"On it, I can read: {ocr[:300]}")
        elif ocr is None:
            parts.append("(OCR unavailable on this host.)")
        if context:
            parts.append(f"Owner context: {str(context)[:200]}")
        return self._submit(source_kind="image", target=target,
                            content=" ".join(parts)[:CONTENT_BUDGET],
                            facts={**facts, "ocr": bool(ocr)})

    @staticmethod
    def _image_facts(path: str) -> Dict[str, Any]:
        try:
            from PIL import Image
            with Image.open(path) as img:
                return {"success": True, "format": str(img.format),
                        "width": img.width, "height": img.height,
                        "mode": str(img.mode)}
        except Exception as exc:
            return {"success": False, "reason": f"unreadable image: {exc}"}

    @staticmethod
    def _ocr(path: str) -> Optional[str]:
        """OCR text, '' when nothing readable, None when OCR itself is
        unavailable (the distinction matters: absence of text is not
        absence of the tool)."""
        try:
            import pytesseract
            from PIL import Image
            with Image.open(path) as img:
                text = pytesseract.image_to_string(img)
            return str(text or "").strip()
        except Exception as exc:
            app_logger.info(f"OCR unavailable for {path}: {exc}")
            return None

    # ── local audio/video: transcript via existing STT, facts anyway ─────
    def _learn_media_file(self, target: str,
                          context: Optional[str]) -> Dict[str, Any]:
        facts = {"size_bytes": os.path.getsize(target)}
        transcript = ""
        try:
            from app.perception.speech_to_text import LocalSpeechToText
            res = LocalSpeechToText.transcribe_file(target)
            transcript = str(res.get("text") or "").strip()
        except Exception as exc:
            app_logger.warning(f"STT unavailable for {target}: {exc}")
        parts = [f"Media file {os.path.basename(target)} "
                 f"({facts['size_bytes']} bytes)."]
        if transcript:
            parts.append(f"Heard: {transcript[:TRANSCRIPT_SAMPLE]}")
        else:
            parts.append("(transcript unavailable — observed the file only)")
        if context:
            parts.append(f"Owner context: {str(context)[:200]}")
        return self._submit(source_kind="media_file", target=target,
                            content=" ".join(parts)[:CONTENT_BUDGET],
                            facts={**facts, "transcript_chars": len(transcript)})

    # ── web pages: deterministic scrape (no LLM) ─────────────────────────
    def _learn_web(self, target: str, focus: Optional[str],
                   context: Optional[str]) -> Dict[str, Any]:
        from app.tools.universal_media_learner import UniversalMediaLearner
        try:
            page = UniversalMediaLearner._extract_video_urls_from_webpage(target)
        except Exception as exc:
            return {"success": False, "kind": "web",
                    "reason": f"page fetch failed: {exc}"}
        if not page.get("success"):
            return {"success": False, "kind": "web",
                    "reason": str(page.get("error") or "page fetch failed")}
        title = str(page.get("title") or "untitled page")
        snippet = str(page.get("page_text_snippet") or "")[:TRANSCRIPT_SAMPLE]
        videos = len(page.get("video_sources") or []) + \
            len(page.get("iframe_sources") or [])
        parts = [f"Web page '{title}': {snippet}"]
        if videos:
            parts.append(f"(embedded video elements found: {videos})")
        if context:
            parts.append(f"Owner context: {str(context)[:200]}")
        return self._submit(source_kind="web", target=target,
                            content=" ".join(parts)[:CONTENT_BUDGET],
                            facts={"title": title, "video_elements": videos})

    # ── into the one loop: watching is NOT verification ──────────────────
    def _submit(self, *, source_kind: str, target: str, content: str,
                facts: Dict[str, Any]) -> Dict[str, Any]:
        try:
            rec = self.mind.learn({
                "kind": "media", "content": content,
                "source": f"{source_kind}:{target}"[:200],
                "outcome": source_kind,
                "success": None,  # watched ≠ verified — never guessed
            })
        except Exception as exc:
            return {"success": False, "kind": source_kind,
                    "reason": f"learning loop rejected it: {exc}"}
        return {"success": True, "kind": source_kind, "target": target,
                "facts": facts, "novelty": rec.get("novelty"),
                "stored_memory_id": rec.get("stored_memory_id"),
                "store_note": rec.get("store_note"),
                "success_evidence": rec.get("success_evidence")}
