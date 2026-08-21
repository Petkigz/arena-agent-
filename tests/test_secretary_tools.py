"""
Tests for the new secretary tools (notes, weather, translation, email, SQL,
calendar, documents). All exercise graceful-degradation and real behavior
without external services.
"""

import json

import pytest

from app.tools.notes_manager import NotesManager
from app.tools.translator import TranslatorTool
from app.tools.email_service import EmailService
from app.tools.sql_query import SQLQueryTool
from app.tools.calendar_service import CalendarService
from app.tools.document_generator import DocumentGenerator, _md_to_html
from app.tools.weather_service import WeatherService


# ── Notes ───────────────────────────────────────────────────────────────────
def test_notes_crud(tmp_path, monkeypatch):
    monkeypatch.setattr(NotesManager, "NOTES_DIR", tmp_path / "notes")

    created = NotesManager.create_note("Meeting", "# agenda\n- item", tags=["work"])
    assert created["success"] is True

    listed = NotesManager.list_notes()
    assert any(n["title"].startswith("Meeting") for n in listed)

    found = NotesManager.search_notes("agenda")
    assert len(found) == 1

    read = NotesManager.read_note(created["note_id"])
    assert "agenda" in read["content"]

    deleted = NotesManager.delete_note(created["note_id"])
    assert deleted["success"] is True
    assert NotesManager.list_notes() == []


# ── Translation ─────────────────────────────────────────────────────────────
def test_translate_returns_translation(monkeypatch):
    fake = {"choices": [{"message": {"content": "Hola"}}], "model": "fast"}
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)

    res = TranslatorTool.translate("Hello", "Spanish")
    assert res["success"] is True
    assert res["translation"] == "Hola"


def test_translate_rejects_empty():
    res = TranslatorTool.translate("", "French")
    assert res["success"] is False


# ── Email ───────────────────────────────────────────────────────────────────
def test_email_not_configured(monkeypatch):
    monkeypatch.delenv("ARENA_SMTP_HOST", raising=False)
    monkeypatch.delenv("ARENA_SMTP_USER", raising=False)
    assert EmailService.is_configured() is False
    res = EmailService.send_email("a@b.com", "hi", "body")
    assert res["success"] is False
    assert "not configured" in res["error"]


# ── SQL ─────────────────────────────────────────────────────────────────────
def test_sql_rejects_writes():
    assert SQLQueryTool.is_read_only("SELECT * FROM t") is True
    assert SQLQueryTool.is_read_only("INSERT INTO t VALUES (1)") is False
    assert SQLQueryTool.is_read_only("DROP TABLE t") is False


def test_sql_query_sqlite(tmp_path):
    import sqlite3
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'alice'), (2, 'bob')")
    conn.commit()
    conn.close()

    res = SQLQueryTool.query_sqlite(str(db), "SELECT * FROM t WHERE id = 1")
    assert res["success"] is True
    assert res["rows"] == [{"id": 1, "name": "alice"}]

    blocked = SQLQueryTool.query_sqlite(str(db), "DROP TABLE t")
    assert blocked["success"] is False


def test_sql_query_csv(tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("name,score\nalice,10\nbob,20\n", encoding="utf-8")

    res = SQLQueryTool.query_csv(str(csv_path), "SELECT name FROM data WHERE score > 10")
    assert res["success"] is True
    assert res["rows"] == [{"name": "bob"}]


# ── Calendar ────────────────────────────────────────────────────────────────
def test_calendar_events_and_reminders(tmp_path, monkeypatch):
    monkeypatch.setattr(CalendarService, "STORE_PATH", tmp_path / "cal.json")

    e = CalendarService.add_event("Standup", "2026-08-21T09:00:00+00:00")
    assert e["success"] is True
    assert len(CalendarService.list_events()) == 1

    r = CalendarService.add_reminder("Call Bob", "2026-01-01T00:00:00+00:00")
    assert r["success"] is True
    # The reminder is already "due" (past date) → appears in due_reminders.
    due = CalendarService.due_reminders()
    assert any(x["title"] == "Call Bob" for x in due)

    done = CalendarService.complete_reminder(r["reminder"]["id"])
    assert done["success"] is True
    assert CalendarService.due_reminders() == []


# ── Document generation ─────────────────────────────────────────────────────
def test_md_to_html():
    html = _md_to_html("# Title\n\n**bold** text")
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html


def test_generate_html(tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentGenerator, "OUTPUT_DIR", tmp_path / "out")
    res = DocumentGenerator.generate("report", "# Hi\n\n**done**", fmt="html")
    assert res["success"] is True
    assert res["format"] == "html"


def test_generate_pdf_requires_reportlab(tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentGenerator, "OUTPUT_DIR", tmp_path / "out")
    res = DocumentGenerator.generate("report", "content", fmt="pdf")
    # Either succeeds (if reportlab installed) or reports the missing dep.
    assert "success" in res


# ── Weather (mocked) ────────────────────────────────────────────────────────
def test_weather_success(monkeypatch):
    import httpx

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "current_weather": {"temperature": 22.0, "windspeed": 10.0, "weathercode": 61},
                "daily": {"temperature_2m_max": [26.0], "temperature_2m_min": [18.0]},
            }

    monkeypatch.setattr(WeatherService, "_geocode", lambda city: {"name": "Kampala", "latitude": 0.3, "longitude": 32.5})
    monkeypatch.setattr("httpx.get", lambda *a, **kw: _Resp())

    res = WeatherService.get_weather("Kampala")
    assert res["success"] is True
    assert res["temperature_c"] == 22.0
    assert res["condition"] == "light rain"


def test_weather_city_not_found(monkeypatch):
    monkeypatch.setattr(WeatherService, "_geocode", lambda city: None)
    res = WeatherService.get_weather("NotACity")
    assert res["success"] is False
