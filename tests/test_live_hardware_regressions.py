"""Regressions found by the FIRST live session on the owner's Windows PC.

1. runtime_wiring: one bare `self` survived the extraction -> the
   perception->grounding loop crashed with NameError on every cycle.
2. cognitive_traces: old DBs lacked later columns -> persistence warning
   and dropped telemetry on every trace.
3. Console logging crashed with UnicodeEncodeError (cp1252 vs '->') under
   uvicorn --reload on Windows.
4. Restart reverted model ids to tier defaults -> HTTP 400s against LM
   Studio until the profile was PUT again.
"""
import logging
import sqlite3


def test_runtime_wiring_has_no_stray_self():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "app" / "cognition" / "runtime_wiring.py").read_text(encoding="utf-8")
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or "self-knowledge" in stripped:
            continue
        assert " self" not in stripped.replace("self-knowledge", "") or "rt" in line, (
            f"stray 'self' at line {lineno}: {line}")


def test_trace_migration_adds_every_missing_column(tmp_path):
    from app.cognition.trace import CognitiveTrace
    db = tmp_path / "old.db"
    # An OLD-schema database: only the original columns.
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE cognitive_traces (
            trace_id TEXT PRIMARY KEY, session_id TEXT, user_input TEXT,
            assistant_reply TEXT, actions_json TEXT, model_used TEXT,
            latency_ms REAL, vram_pressure REAL, ram_pressure REAL,
            created_at TEXT)""")
        conn.commit()
    from app.config import settings
    import app.cognition.trace as trace_module
    original = settings.DB_PATH
    settings.DB_PATH = db
    try:
        trace = CognitiveTrace(session_id="s", user_input="hi", assistant_reply="ok")
        trace.latency_ms = 1.0
        trace.model_used = "m"
        trace.belief_confidence = 0.9
        trace.persist() if hasattr(trace, "persist") else trace._persist_trace_to_db()
    finally:
        settings.DB_PATH = original
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(cognitive_traces)")}
        row = conn.execute("SELECT belief_confidence FROM cognitive_traces").fetchone()
    assert {"belief_confidence", "gate_decision", "prediction_surprisal",
            "reflection_lesson", "goal_verified"} <= cols
    assert row == (0.9,)


def test_console_logging_never_crashes_on_unicode():
    """The app logger's console stream must tolerate any character."""
    from app.utils.logger import app_logger
    handler_streams = [h.stream for h in app_logger.handlers if isinstance(h, logging.StreamHandler)]
    assert handler_streams, "expected a console stream handler"
    stream = handler_streams[0]
    # Emit through the real handler path; success = no exception raised.
    app_logger.info("arrow → check %s", "ok")
    encoding = getattr(stream, "errors", None) or getattr(
        getattr(stream, "buffer", object()), "errors", None)
    assert encoding in ("replace", "strict", "backslashreplace") or encoding is None
    if getattr(stream, "encoding", "") and stream.encoding.lower() not in ("utf-8", "utf8"):
        assert getattr(stream, "errors", "") == "replace", (
            f"non-utf8 stream {stream.encoding!r} must use errors='replace'")


def test_persisted_profile_applies_at_startup(tmp_path, monkeypatch):
    import app.cognition.inference_profile as ip
    from app.cognition.inference_profile import InferenceProfile
    store = ip.InferenceProfileStore(tmp_path / "profile.json")
    store.update({"main_model": "qwen/qwen3-14b", "fast_model": "qwen2.5-3b-instruct"})
    monkeypatch.setattr(ip, "inference_profile_store", store)
    from app.config import settings
    monkeypatch.setattr(settings, "MAIN_MODEL", "qwen2.5-9b-instruct", raising=False)
    applied = ip.apply_persisted_profile()
    assert applied is not None and applied.main_model == "qwen/qwen3-14b"
    assert settings.MAIN_MODEL == "qwen/qwen3-14b"  # restart no longer reverts
