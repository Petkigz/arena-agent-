"""Reply delivery guarantees, from the live 'stuck thinking' session.

1. The sender's socket is auto-joined to the conversation it messages —
   a client listening in room A while messaging room B must still receive
   the reply (desktop had joined desktop-chat but sent to the web room;
   the reply streamed to an empty room).
2. A reply that tokenizes to zero tokens still emits exactly one terminal
   (done=true) token, so no client can hang on "thinking" forever.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.message_router import MessageRouter


class RecordingWS:
    def __init__(self):
        self.joined = []

    async def join_conversation(self, websocket, conversation_id):
        self.joined.append(conversation_id)


def make_router(recorded_tokens):
    ws_manager = RecordingWS()
    sent = []

    async def send(conversation_id, message):
        sent.append((conversation_id, message))

    ws_manager.send_to_conversation = send
    router = MessageRouter.__new__(MessageRouter)

    async def fake_cycle(content, image_path=None, audio_path=None, attachments=None):
        return "the reply"

    router_router = MagicMock()
    object.__setattr__(router, "_check_rate_limit", lambda cid: True)
    with patch.object(MessageRouter, "_call_cognitive_runtime", fake_cycle):
        pass
    router._call_cognitive_runtime = fake_cycle
    return router, ws_manager, sent


def run_handle(content="do you have wisdom?", conversation_id="conv_web"):
    router, ws_manager, sent = make_router([])
    websocket = MagicMock()
    message = {"conversation_id": conversation_id, "content": content}

    async def call():
        # Borrow the real handler with patched collaborators.
        with patch("backend.message_router.ws_manager", ws_manager), \
             patch("backend.message_router.add_to_history"), \
             patch("backend.message_router.get_conversation_history", return_value=[]):
            handler = MessageRouter._handle_user_message.__get__(router)
            return await handler(websocket, message)

    return asyncio.run(call()), ws_manager, sent


def test_sender_is_joined_to_the_room_it_messages():
    _, ws_manager, sent = run_handle()
    assert ws_manager.joined == ["conv_web"]  # sender auto-joined


def test_reply_tokens_finish_with_done_true():
    _, _, sent = run_handle()
    tokens = [m for cid, m in sent if m["type"] == "message_token"]
    assert tokens, "expected streamed tokens"
    assert tokens[-1]["done"] is True
    # The streamed reply reaches the room that was messaged.
    assert all(cid == "conv_web" for cid, m in sent if m["type"] == "message_token")


def test_empty_reply_still_emits_terminal_token():
    router, ws_manager, sent = make_router([])

    async def empty_cycle(content, **kw):
        return ""

    router._call_cognitive_runtime = empty_cycle
    websocket = MagicMock()
    message = {"conversation_id": "conv_x", "content": "hi"}

    async def call():
        with patch("backend.message_router.ws_manager", ws_manager), \
             patch("backend.message_router.add_to_history"), \
             patch("backend.message_router.get_conversation_history", return_value=[]):
            handler = MessageRouter._handle_user_message.__get__(router)
            return await handler(websocket, message)

    asyncio.run(call())
    tokens = [m for cid, m in sent if m["type"] == "message_token"]
    assert tokens and tokens[-1]["done"] is True  # never hang the client
