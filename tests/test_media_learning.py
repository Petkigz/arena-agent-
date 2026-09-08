"""Phase 8 (Beanie AGI roadmap) — learning from images, video, web media.

Media enters the ONE Phase-6 loop as another experience kind. Contracts
pinned here:
- deterministic observation first (real PIL facts, real temp files);
- watching is NEVER verification: every media event keeps success=None;
- every failure is typed — unreadable image, missing transcript, fetch
  error — and nothing fabricated lands in memory;
- deep LLM analysis is optional and fails honestly;
- provenance rides along (source names the target).
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind


class _Brain:
    def __init__(self, tmp_path):
        self.memory = MemoryStore(tmp_path / "memory.db")
        self.confidence_calibrator = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        self.working_memory = None
        self.hardware_self_model = {}
        self.phase7_preferences = None

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok"}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain, tmp_path
    BeanieMind.reset_instance()


def _png(path, w=24, h=12):
    from PIL import Image
    Image.new("RGB", (w, h), color=(200, 30, 30)).save(path)
    return str(path)


# ── classification + typed failures ────────────────────────────────────────
def test_classification_and_typed_failures(setup):
    mind, _, tmp = setup
    ml = mind.media_learning
    assert ml._classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert ml._classify("https://youtu.be/dQw4w9WgXcQ") == "youtube"
    assert ml._classify(_png(tmp / "a.png")) == "image"
    wav = tmp / "a.wav"
    wav.write_bytes(b"RIFF....")
    assert ml._classify(str(wav)) == "media_file"
    assert ml._classify("https://example.com/page") == "web"
    assert ml._classify(str(tmp / "missing.png")) == "unsupported"

    bad = ml.learn_from_media(str(tmp / "missing.png"))
    assert bad["success"] is False and "unsupported" in bad["reason"]
    assert ml.learn_from_media("   ")["success"] is False
    assert mind.learning.events() == []  # nothing fabricated


# ── images: real facts, stored as knowledge ────────────────────────────────
def test_image_learning_stores_real_facts(setup):
    mind, brain, tmp = setup
    rec = mind.media_learning.learn_from_media(
        _png(tmp / "shot.png"), context="screenshot of my invoice folder")
    assert rec["success"] is True and rec["kind"] == "image"
    assert rec["facts"]["format"] == "PNG"
    assert rec["facts"]["width"] == 24 and rec["facts"]["height"] == 12
    assert rec["novelty"] == "novel" and rec["stored_memory_id"]

    # watching is never verification
    event = mind.learning.events()[0]
    assert event["kind"] == "media" and event["success"] is None
    assert "invoice folder" in event["content"]
    # provenance names the target
    stored = [r for r in brain.memory.search("screenshot invoice", limit=5)
              if r.kind == "semantic"]
    assert stored and "shot.png" in (stored[0].source or "")

    # same image again (no context this time → different content, still
    # rehearsed, still not duplicated)
    again = mind.media_learning.learn_from_media(str(tmp / "shot.png"))
    assert again["novelty"] == "reinforces"
    assert again["store_note"] == "reinforced existing knowledge (rehearsed)"
    assert mind.memory.counts()["semantic"] == 1
    # exact same experience content → the exact-dedupe note
    exact = mind.media_learning.learn_from_media(
        str(tmp / "shot.png"), context="screenshot of my invoice folder")
    assert exact["store_note"] == "already known — rehearsed, not duplicated"
    assert mind.memory.counts()["semantic"] == 1


def test_unreadable_image_is_a_typed_failure(setup):
    mind, _, tmp = setup
    p = tmp / "corrupt.png"
    p.write_bytes(b"not a real image")
    rec = mind.media_learning.learn_from_media(str(p))
    assert rec["success"] is False and "unreadable" in rec["reason"]
    assert mind.learning.events() == []


def test_missing_ocr_is_reported_honestly(setup, monkeypatch):
    mind, _, tmp = setup
    import pytesseract
    def _boom(img):
        raise RuntimeError("tesseract binary not found")
    monkeypatch.setattr(pytesseract, "image_to_string", _boom)
    rec = mind.media_learning.learn_from_media(_png(tmp / "x.png"))
    assert rec["success"] is True  # facts are still real
    assert rec["facts"]["ocr"] is False
    event = mind.learning.events()[0]
    assert "OCR unavailable on this host" in event["content"]


# ── YouTube: transcript first, no fabrication ──────────────────────────────
def test_youtube_transcript_becomes_knowledge(setup, monkeypatch):
    mind, brain, tmp = setup
    from app.tools.youtube_learner import YouTubeLearner
    fake = {"success": True, "video_id": "dQw4w9WgXcQ",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "transcript": "today we learn about backing up databases with "
                          "nightly snapshots and rotation", "segments": []}
    monkeypatch.setattr(YouTubeLearner, "get_transcript",
                        staticmethod(lambda url, languages=("en",): dict(fake)))
    rec = mind.media_learning.learn_from_media(
        "https://youtu.be/dQw4w9WgXcQ")
    assert rec["success"] is True and rec["kind"] == "youtube"
    assert rec["facts"]["video_id"] == "dQw4w9WgXcQ"
    assert rec["facts"]["transcript_chars"] > 0
    event = mind.learning.events()[0]
    assert event["success"] is None and "Transcript sample" in event["content"]
    assert [r for r in brain.memory.search("backing up databases", limit=5)
            if r.kind == "semantic"]


def test_youtube_without_transcript_fails_typed(setup, monkeypatch):
    mind, _, tmp = setup
    from app.tools.youtube_learner import YouTubeLearner
    monkeypatch.setattr(YouTubeLearner, "get_transcript",
                        staticmethod(lambda url, languages=("en",):
                                     {"success": False, "error": "subtitles off"}))
    rec = mind.media_learning.learn_from_media("https://youtu.be/dQw4w9WgXcQ")
    assert rec["success"] is False and "subtitles off" in rec["reason"]
    assert mind.learning.events() == []


def test_deep_analysis_is_optional_and_honest(setup, monkeypatch):
    mind, _, tmp = setup
    from app.tools.youtube_learner import YouTubeLearner
    monkeypatch.setattr(YouTubeLearner, "get_transcript",
                        staticmethod(lambda url, languages=("en",):
                                     {"success": True, "video_id": "abc12345678",
                                      "transcript": "rotate the logs weekly",
                                      "segments": []}))
    # deep analysis unavailable → deterministic facts still land
    monkeypatch.setattr(YouTubeLearner, "learn_from_video",
                        staticmethod(lambda url, prompt_focus=None, complexity="main":
                                     {"success": False, "error": "no model"}))
    rec = mind.media_learning.learn_from_media(
        "https://youtu.be/abc12345678", deep=True)
    assert rec["success"] is True and rec["facts"]["deep_analysis"] is False
    # deep analysis present → summary rides along
    monkeypatch.setattr(YouTubeLearner, "learn_from_video",
                        staticmethod(lambda url, prompt_focus=None, complexity="main":
                                     {"success": True, "ai_summary": "Rotate logs weekly."}))
    rec2 = mind.media_learning.learn_from_media(
        "https://youtu.be/abc12345678", deep=True)
    assert rec2["facts"]["deep_analysis"] is True


# ── local media files: facts always, transcript when honestly available ────
def test_media_file_with_and_without_transcript(setup, monkeypatch):
    mind, _, tmp = setup
    wav = tmp / "voice.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    from app.perception.speech_to_text import LocalSpeechToText
    monkeypatch.setattr(LocalSpeechToText, "transcribe_file",
                        staticmethod(lambda path: {"text": "move the backups off disk"}))
    rec = mind.media_learning.learn_from_media(str(wav))
    assert rec["success"] is True and rec["facts"]["transcript_chars"] > 0
    assert "Heard:" in mind.learning.events()[0]["content"]

    monkeypatch.setattr(LocalSpeechToText, "transcribe_file",
                        staticmethod(lambda path: (_ for _ in ()).throw(RuntimeError("no model"))))
    rec2 = mind.media_learning.learn_from_media(str(wav))
    assert rec2["success"] is True  # the observation is still real
    assert rec2["facts"]["transcript_chars"] == 0
    assert "transcript unavailable" in mind.learning.events()[0]["content"]


# ── web: deterministic scrape, typed fetch failure ─────────────────────────
def test_web_page_learning(setup, monkeypatch):
    mind, _, tmp = setup
    from app.tools.universal_media_learner import UniversalMediaLearner
    monkeypatch.setattr(UniversalMediaLearner, "_extract_video_urls_from_webpage",
                        staticmethod(lambda url: {
                            "success": True, "title": "Backup Guide",
                            "video_sources": ["a.mp4"], "iframe_sources": [],
                            "ad_elements": [],
                            "page_text_snippet": "nightly snapshots rotation"}))
    rec = mind.media_learning.learn_from_media("https://example.com/backup")
    assert rec["success"] is True and rec["facts"]["title"] == "Backup Guide"
    assert rec["facts"]["video_elements"] == 1

    monkeypatch.setattr(UniversalMediaLearner, "_extract_video_urls_from_webpage",
                        staticmethod(lambda url: {"success": False, "error": "timeout"}))
    bad = mind.media_learning.learn_from_media("https://example.com/dead")
    assert bad["success"] is False and "timeout" in bad["reason"]


# ── API contract ────────────────────────────────────────────────────────────
def test_media_learning_api(setup):
    mind, _, tmp = setup
    img = _png(tmp / "api.png")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.post("/mind/learn/media", json={"target": img}).json()
    assert body["success"] is True and body["facts"]["format"] == "PNG"

    body = client.post("/mind/learn/media",
                       json={"target": str(tmp / "nope.png")}).json()
    assert body["success"] is False  # typed failure, not a 500

    body = client.post("/mind/learn/media", json={"target": ""})
    assert body.status_code == 422  # schema rejects empty target
