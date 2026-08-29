"""Regression guard: three live UX complaints from the owner machine.

1. 'I can't chat in the other chats' — 'do i have a song called kaba on my
   pc' was routed to the mobile_phone domain because the bare substring
   check `"call" in text_lower` matched the word 'called'. Every such query
   DEFERRED with a terse non-answer, so those conversations looked dead.
   Fixed with word-boundary keyword matching (plurals still match).
2. 'The task is still going on but I can't track it in any way' — goals that
   ended in waiting_for_evidence were invisible: the reply didn't say the
   goal was parked, and no endpoint listed open goals. Fixed with an honest
   status note in the reply, goal_lifecycle_state persisted on traces, and
   GET /cognition/open-goals.
3. 'Audio reply seems not available' — the WS voice path used Piper ONLY;
   machines without a Piper voice model got silent replies. Fixed with a
   piper → pyttsx3 (OS TTS driver) fallback that streams 16 kHz PCM.

Plus: file-existence questions ('do i have a song called kaba') now route to
a real filesystem search and answer from evidence instead of deferring.
"""

import asyncio
import sqlite3
import wave
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.observation_router import plan_observation, render_observation_evidence
from app.cognition.trace import CognitiveTrace
from app.config import settings
from app.server import app
from backend.message_router import MessageRouter


# ── 1. Word-boundary keyword routing ─────────────────────────────────────────

def test_called_no_longer_routes_to_mobile_phone():
    """The exact live text: 'called' must not match the 'call' keyword."""
    g = SemanticGoalInterpreter.interpret_goal("do i have a song called kaba on my pc")
    assert g.target_domain != "mobile_phone", (
        "'called' must never trigger the phone/call keyword — this exact "
        "misroute made the other chats appear dead (every query deferred)."
    )


def test_plurals_still_match_keywords():
    g = SemanticGoalInterpreter.interpret_goal("search my pc for documents")
    assert g.target_domain == "filesystem"
    g2 = SemanticGoalInterpreter.interpret_goal("find my songs")
    assert g2.target_domain == "filesystem"


def test_legitimate_call_keyword_still_routes_to_phone():
    g = SemanticGoalInterpreter.interpret_goal("call mom")
    assert g.target_domain == "mobile_phone"


# ── 2. File-existence questions answer from filesystem evidence ─────────────

def test_file_existence_question_gets_search_plan():
    plan = plan_observation("do i have a song called kaba on my pc")
    assert plan is not None
    assert plan.action_type == "search_files"
    assert plan.payload["query"] == "kaba"
    assert plan.payload["root_dir"]  # searches the user's home, not just the repo


def test_file_existence_empty_results_is_evidence_of_absence():
    plan = plan_observation("is there a file named report.docx")
    assert plan is not None
    evidence = render_observation_evidence([], plan)
    assert "NO matches found" in evidence
    assert "not found" in evidence


def test_file_existence_renders_matches():
    plan = plan_observation("have i got a picture called sunset")
    evidence = render_observation_evidence(
        [{"file_path": "C:/Users/x/Pictures/sunset.jpg"}], plan
    )
    assert "sunset.jpg" in evidence


def test_generic_file_questions_do_not_get_search_plans():
    """'do i have any documents' (no name) must not trigger a bogus search."""
    assert plan_observation("do i have any documents") is None


# ── 3. waiting_for_evidence is honest and trackable ──────────────────────────

def test_waiting_for_evidence_reply_gets_status_note():
    runtime = MagicMock()
    runtime.process_cognitive_cycle.return_value = {
        "success": True,
        "assistant_reply": "I looked into it but couldn't confirm.",
        "goal_lifecycle_state": "waiting_for_evidence",
    }
    router = MessageRouter(runtime=runtime)
    reply = asyncio.run(router._call_cognitive_runtime("check my windows defender"))
    assert "waiting_for_evidence" in reply
    assert "no background task is running" in reply


def test_achieved_replies_are_not_annotated():
    runtime = MagicMock()
    runtime.process_cognitive_cycle.return_value = {
        "success": True,
        "assistant_reply": "Here is your answer.",
        "goal_lifecycle_state": "achieved",
    }
    router = MessageRouter(runtime=runtime)
    reply = asyncio.run(router._call_cognitive_runtime("hello"))
    assert reply == "Here is your answer."


def test_trace_persists_goal_lifecycle_state():
    trace = CognitiveTrace(user_input="open-goals regression probe")
    trace.finalize(
        reply="parked",
        actions=[],
        latency=1.0,
        goal_verified=False,
        goal_lifecycle_state="waiting_for_evidence",
    )
    try:
        conn = sqlite3.connect(str(settings.DB_PATH))
        row = conn.execute(
            "SELECT goal_lifecycle_state FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()
        assert row == ("waiting_for_evidence",)
    finally:
        conn.execute("DELETE FROM cognitive_traces WHERE trace_id=?", (trace.trace_id,))
        conn.commit()
        conn.close()


def test_open_goals_endpoint_lists_parked_goals():
    client = TestClient(app)
    r = client.get("/cognition/open-goals")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["open_goals"], list)
    assert "no background task" in body["note"]
    for goal in body["open_goals"]:
        assert goal["state"] == "waiting_for_evidence"


# ── 4. Voice reply TTS fallback (piper → OS driver) ──────────────────────────

def _write_test_wav(path, sample_rate=22050, seconds=0.5):
    n_frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        import struct
        frames = b"".join(struct.pack("<h", 1000) for _ in range(n_frames))
        w.writeframes(frames)


def test_tts_fallback_converts_wav_to_pcm16k(tmp_path):
    """Without a Piper model, spoken replies must fall back to the OS TTS
    driver and still stream 16 kHz int16 PCM to the voice clients."""
    from backend.voice.service import VoiceService

    wav = tmp_path / "reply.wav"
    _write_test_wav(wav, sample_rate=22050, seconds=0.5)

    fake_result = {"success": True, "file_path": str(wav)}
    with patch("app.perception.text_to_speech.LocalTextToSpeech.synthesize_speech",
               return_value=fake_result):
        pcm = VoiceService._synthesize_wav_to_pcm16k("hello there")
    assert isinstance(pcm, bytes) and len(pcm) > 0
    # 22050 Hz → ~8000 samples at 16 kHz, 2 bytes each.
    n_samples = len(pcm) // 2
    assert 7000 <= n_samples <= 9000


def test_tts_fallback_returns_none_when_no_engine(tmp_path):
    from backend.voice.service import VoiceService
    with patch("app.perception.text_to_speech.LocalTextToSpeech.synthesize_speech",
               return_value={"success": False, "error": "no engine", "audio_url": ""}):
        pcm = VoiceService._synthesize_wav_to_pcm16k("hello there")
    assert pcm is None
