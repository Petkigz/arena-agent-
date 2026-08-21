"""Messaging tests — validation, unconfigured degradation, and mocked sends."""

from unittest.mock import MagicMock

from app.tools.messaging import Messaging


def test_telegram_requires_message():
    assert Messaging.send_telegram("")["success"] is False


def test_whatsapp_requires_message():
    assert Messaging.send_whatsapp("")["success"] is False


def test_telegram_unconfigured(monkeypatch):
    monkeypatch.delenv("ARENA_TELEGRAM_BOT_TOKEN", raising=False)
    res = Messaging.send_telegram("hi")
    assert res["success"] is False
    assert "not configured" in res["error"]


def test_whatsapp_unconfigured(monkeypatch):
    for k in ("ARENA_TWILIO_ACCOUNT_SID", "ARENA_TWILIO_AUTH_TOKEN", "ARENA_TWILIO_FROM"):
        monkeypatch.delenv(k, raising=False)
    res = Messaging.send_whatsapp("hi")
    assert res["success"] is False
    assert "not configured" in res["error"]


def test_telegram_requires_chat_id(monkeypatch):
    monkeypatch.setenv("ARENA_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.delenv("ARENA_TELEGRAM_CHAT_ID", raising=False)
    res = Messaging.send_telegram("hi")
    assert res["success"] is False
    assert "chat_id" in res["error"]


def test_telegram_send_success(monkeypatch):
    monkeypatch.setenv("ARENA_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("ARENA_TELEGRAM_CHAT_ID", "123")

    fake = MagicMock()
    fake.return_value.status_code = 200
    fake.return_value.headers = {"content-type": "application/json"}
    fake.return_value.json.return_value = {"ok": True}
    monkeypatch.setattr("app.tools.messaging.httpx.post", fake)

    res = Messaging.send_telegram("hello")
    assert res["success"] is True
    assert res["channel"] == "telegram"
    assert res["chat_id"] == "123"


def test_whatsapp_send_success(monkeypatch):
    monkeypatch.setenv("ARENA_TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setenv("ARENA_TWILIO_AUTH_TOKEN", "auth")
    monkeypatch.setenv("ARENA_TWILIO_FROM", "whatsapp:+10000000000")

    fake = MagicMock()
    fake.return_value.status_code = 201
    monkeypatch.setattr("app.tools.messaging.httpx.post", fake)

    res = Messaging.send_whatsapp("hello", to="whatsapp:+14155552671")
    assert res["success"] is True
    assert res["channel"] == "whatsapp"
