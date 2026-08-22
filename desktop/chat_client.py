"""WebSocket chat client for the native desktop app (GUI-free).

Mirrors the web frontend's chat protocol so the desktop app gets the same
ChatGPT-style conversations as the browser and Android: list / create / history
/ streamed replies. Kept dependency-light and Qt-free for unit testing.
"""

from __future__ import annotations

import json
import threading
from typing import Callable, List, Optional, Tuple


class DesktopChatClient:
    def __init__(self, ws_url: str = "ws://localhost:8000/ws", conversation_id: str = "desktop-chat"):
        self.ws_url = ws_url
        self.conversation_id = conversation_id
        self._ws = None
        self._connected = False
        self._recv_thread: Optional[threading.Thread] = None
        self._reply_parts: List[str] = []

        #: Called with no args when the socket opens.
        self.on_connected: Optional[Callable[[], None]] = None
        #: Called with no args when the socket closes.
        self.on_disconnected: Optional[Callable[[], None]] = None
        #: Called with (token, done) as reply tokens stream.
        self.on_token: Optional[Callable[[str, bool], None]] = None
        #: Called with a list of (id, title) conversation previews.
        self.on_conversation_list: Optional[Callable[[List[Tuple[str, str]]], None]] = None
        #: Called with (conversation_id, [(role, content), ...]).
        self.on_history: Optional[Callable[[str, List[Tuple[str, str]]], None]] = None
        #: Called with (conversation_id, title) when a conversation is created.
        self.on_created: Optional[Callable[[str, str], None]] = None
        #: Called with an error message string.
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        try:
            import websockets
            self._ws = websockets.connect(self.ws_url).__enter__()
            self._connected = True
            self._send({"type": "join_conversation", "conversation_id": self.conversation_id})
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            if self.on_connected:
                self.on_connected()
            return True
        except Exception as e:  # noqa: BLE001
            self._connected = False
            if self.on_error:
                self.on_error(f"Could not connect chat: {e}")
            return False

    # ── outgoing ─────────────────────────────────────────────────────────────
    def send_user_message(self, conversation_id: str, content: str) -> None:
        self._send({
            "type": "user_message",
            "conversation_id": conversation_id,
            "content": content,
        })

    def create_conversation(self, title: str = "New Conversation") -> None:
        self._send({"type": "create_conversation", "title": title})

    def list_conversations(self) -> None:
        self._send({"type": "list_conversations"})

    def get_history(self, conversation_id: str) -> None:
        self._send({"type": "get_history", "conversation_id": conversation_id})

    def _send(self, payload: dict) -> None:
        if self._ws is not None:
            try:
                self._ws.send(json.dumps(payload))
            except Exception:  # noqa: BLE001
                pass

    # ── incoming ─────────────────────────────────────────────────────────────
    def _recv_loop(self) -> None:
        while self._connected and self._ws is not None:
            try:
                frame = self._ws.recv()
            except Exception:  # noqa: BLE001
                break
            if isinstance(frame, (bytes, bytearray)):
                continue  # binary audio echo — not chat text
            self._handle_text(frame)
        if self._connected:
            self._connected = False
            if self.on_disconnected:
                self.on_disconnected()

    def _handle_text(self, text: str) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return

        t = data.get("type")
        if t == "conversation_list":
            out: List[Tuple[str, str]] = []
            for c in data.get("conversations") or []:
                cid = c.get("id") or c.get("conversation_id") or ""
                title = c.get("title") or "New Conversation"
                if cid:
                    out.append((cid, title))
            if self.on_conversation_list:
                self.on_conversation_list(out)
        elif t == "conversation_history":
            cid = data.get("conversation_id", "")
            history: List[Tuple[str, str]] = []
            for m in data.get("messages") or []:
                history.append((m.get("role", "assistant"), m.get("content", "")))
            if self.on_history:
                self.on_history(cid, history)
        elif t == "conversation_created":
            if self.on_created:
                self.on_created(data.get("conversation_id", ""), data.get("title", "New Conversation"))
        elif t == "message_token":
            token = data.get("token", "")
            done = bool(data.get("done", False))
            if isinstance(token, str):
                self._reply_parts.append(token)
            if self.on_token:
                self.on_token(token, done)
            if done:
                self._reply_parts = []
        elif t == "error":
            if self.on_error:
                self.on_error(data.get("message", "Chat error"))

    def close(self) -> None:
        self._connected = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
