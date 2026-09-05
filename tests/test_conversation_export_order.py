"""Chat correlation (owner report 2026-09-05): the exported conversation
showed replies beside the WRONG questions.

Two holes, both fixed here:
1. No per-conversation serialization in the router — messages arrive from
   several sockets (desktop, web, phone, voice) and the assistant reply
   was persisted at COMPLETION time, so a slow reply landed after the
   NEXT question. The router now holds one lock per conversation across
   question-append → reply-stream.
2. The client-side Markdown export can only export what that client
   hydrated (last 50 messages, hydration-time timestamps). The
   server-side export endpoint reads the FULL SQLite history in row
   order — adjacent by construction.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import backend.message_router as mr
from app.database import DatabaseManager
from app.api.owner_control_autonomy import router as owner_router


class _FakeWSManager:
    """Absorbs every broadcast; no real sockets needed."""

    async def send_to_conversation(self, *a, **k):
        return None

    async def send_to_connection(self, *a, **k):
        return None

    async def broadcast_to_all(self, *a, **k):
        return None

    async def join_conversation(self, *a, **k):
        return None

    def get_active_conversations(self):
        return []


def _runtime(first_slow: float):
    runtime = MagicMock()

    def cycle(user_text="", **kwargs):
        if "slow" in user_text:
            time.sleep(first_slow)
        return {"success": True,
                "assistant_reply": f"reply to {user_text}",
                "session_id": "sess",
                "goal_lifecycle_state": "achieved"}

    runtime.process_cognitive_cycle.side_effect = cycle
    return runtime


def test_concurrent_messages_persist_question_reply_adjacent(tmp_path):
    """The owner's exact symptom: a slow first reply must NOT land after
    the second question. Two concurrent handlers on ONE conversation; the
    first cycle is slow. Persisted order must alternate user/assistant
    with each reply answering the question DIRECTLY before it."""

    async def scenario():
        temp_db = DatabaseManager(db_path=str(tmp_path / "chat.db"))
        mr._conversation_histories.clear()
        router = mr.MessageRouter(runtime=_runtime(first_slow=0.4))
        fake_ws = _FakeWSManager()
        with patch.object(mr, "ws_manager", fake_ws), \
             patch.object(mr, "db", temp_db):
            await asyncio.gather(
                router._handle_user_message(None, {
                    "conversation_id": "conv_order",
                    "content": "slow first question"}),
                router._handle_user_message(None, {
                    "conversation_id": "conv_order",
                    "content": "fast second question"}),
            )
        return temp_db.get_conversation_messages("conv_order", limit=None)

    msgs = asyncio.run(scenario())
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "user", "assistant"], (
        f"question and reply must alternate (got {roles}) — a reply "
        f"landing after the NEXT question is the mismatched export")
    assert msgs[1]["content"] == f"reply to {msgs[0]['content']}"
    assert msgs[3]["content"] == f"reply to {msgs[2]['content']}"


def test_export_endpoint_returns_full_ordered_history(tmp_path, monkeypatch):
    """The server-side export is the authoritative channel: FULL history
    (not the 50-message hydration cap), row order, real timestamps."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    temp_db = DatabaseManager(db_path=str(tmp_path / "chat.db"))
    for i in range(30):
        temp_db.add_conversation_message("conv_exp", "user", f"question {i}")
        temp_db.add_conversation_message("conv_exp", "assistant", f"answer {i}")
    monkeypatch.setattr("app.database.db", temp_db)

    app = FastAPI()
    app.include_router(owner_router)
    client = TestClient(app)

    resp = client.get("/conversations/conv_exp/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/markdown")
    body = resp.text
    assert "60 messages" in body  # the FULL history, not the last 50
    # question and answer adjacent, in order, every pair
    assert body.index("question 0") < body.index("answer 0") < \
           body.index("question 1") < body.index("answer 1")
    assert "question 29" in body and "answer 29" in body
    # 404 for an unknown conversation
    assert client.get("/conversations/nope/export").status_code == 404
