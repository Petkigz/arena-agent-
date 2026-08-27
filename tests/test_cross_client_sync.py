"""Cross-client sync: desktop joins the owner's active web conversation.

Plus two live-session fixes: log FILES were the real cp1252 crash source
(FileHandler defaults to Windows locale encoding), and learning-progress
auto-initializes the outcomes table on fresh installs.
"""
import logging
from pathlib import Path


def test_log_files_are_utf8_and_tolerate_any_character(tmp_path):
    from app.utils.logger import setup_logger
    logger = setup_logger("utf8_test", "utf8_test.log")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert file_handlers, "expected a file handler"
    for handler in file_handlers:
        assert (handler.encoding or "").lower() == "utf-8"
    logger.info("arrow → and ünïcode ✓")  # must never raise
    for handler in file_handlers:
        handler.flush()


def test_learning_progress_auto_inits_missing_table(tmp_path):
    from app.cognition.learning_progress import LearningProgressTracker
    db = tmp_path / "fresh_outcomes.db"  # table does not exist yet
    tracker = LearningProgressTracker(str(db))
    # No warning-crash: returns empty rows and CREATES the table.
    per_action = tracker._load_rows()
    assert per_action == {}
    import sqlite3
    with sqlite3.connect(str(db)) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "action_outcomes" in tables  # initialized for future evidence


def test_conversations_rest_endpoint(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import db

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    sample = [{"id": "conv_1", "title": "Chat", "lastMessage": "hi", "updatedAt": "t"}]
    monkeypatch.setattr(db, "get_conversation_previews", lambda limit=50: sample)
    client = TestClient(app)
    response = client.get("/conversations", headers={"X-API-Key": "owner-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["conversations"][0]["id"] == "conv_1"


def test_desktop_picks_most_recent_conversation(monkeypatch, tmp_path):
    from desktop.chat_client import pick_shared_conversation
    from types import SimpleNamespace

    fake_client = SimpleNamespace(list_conversations=lambda limit=50: {
        "conversations": [
            {"id": "conv_web_latest", "title": "Web chat", "lastMessage": "x", "updatedAt": "t"},
            {"id": "desktop-chat", "title": "Old", "lastMessage": "y", "updatedAt": "t0"},
        ]})
    fake_settings = {"conversation_id": None}

    class FakeSettings:
        def get(self, key, default=None):
            return fake_settings.get(key, default)

        def set(self, key, value):
            fake_settings[key] = value

    window = SimpleNamespace(client=fake_client, settings=FakeSettings())
    picked = pick_shared_conversation(fake_client, FakeSettings())
    assert picked == "conv_web_latest"          # newest room wins
    assert fake_settings["conversation_id"] == "conv_web_latest"

    # Saved preference wins over recency.
    fake_settings["conversation_id"] = "desktop-chat"
    again = pick_shared_conversation(fake_client, FakeSettings())
    assert again == "desktop-chat"

    # Server unreachable → empty (falls back to the private room).
    broken = SimpleNamespace(client=SimpleNamespace(
        list_conversations=lambda limit=50: (_ for _ in ()).throw(ConnectionError("down"))))
    assert pick_shared_conversation(broken, FakeSettings()) == ""
