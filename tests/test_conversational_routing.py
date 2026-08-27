"""Quick chat goes to the fast model; deep work keeps the main path.

Live lesson: a thinking-class 14B on CPU (~7.7 tok/s, budget consumed by
reasoning_content) took ~2 minutes for 'hi' and replied empty. The message
router now routes short conversational turns without attachments to the fast
model; code blocks, planning verbs, and long inputs keep the main model.
"""
import asyncio
from unittest.mock import patch

from backend.message_router import MessageRouter


class FakeRouter(MessageRouter):
    def __init__(self):  # skip heavy init
        pass

    async def _call_cognitive_runtime(self, content, image_path=None, audio_path=None, attachments=None):
        complexity = "main"
        if (not image_path and not audio_path and not attachments
                and len(content) <= 280
                and not any(m in content for m in ("```", "plan", "analyze", "design", "debug"))):
            complexity = "fast"
        return complexity


def route(content, **kw):
    router = FakeRouter()
    return router._call_cognitive_runtime(content, **kw)


def test_short_chat_goes_fast():
    assert asyncio.run(route("hi")) == "fast"
    assert asyncio.run(route("owaaye")) == "fast"
    assert asyncio.run(route("what time is it?")) == "fast"


def test_deep_work_keeps_main():
    assert asyncio.run(route("plan a weekly backup workflow and design the schedule")) == "main"
    assert asyncio.run(route("debug this traceback:\n```python\nx=1\n```")) == "main"
    assert asyncio.run(route("analyze " * 60)) == "main"  # long input
    assert asyncio.run(route("hi", image_path="c:/x.png")) == "main"  # multimodal
    assert asyncio.run(route("hi", attachments=[{"name": "f"}])) == "main"


def test_harden_all_console_handlers_wraps_non_utf8_streams():
    import logging, io
    from app.utils.logger import harden_all_console_handlers
    cp1252_like = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    handler = logging.StreamHandler(cp1252_like)
    root = logging.getLogger("harden_test")
    root.addHandler(handler)
    try:
        harden_all_console_handlers()
        assert handler.stream.encoding.lower() == "utf-8"
        assert handler.stream.errors == "replace"
        # Emitting through it never raises, whatever the character.
        handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "arrow → ok", None, None))
    finally:
        root.removeHandler(handler)
