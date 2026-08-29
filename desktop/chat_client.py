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
        self._should_reconnect = True
        self._reconnect_attempts = 0

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
        #: Called with (message_id, content) for messages from other clients.
        self.on_room_message: Optional[Callable[[str, str], None]] = None
        #: Called with a conversation_id when the owner chats in ANY room
        #: (cross-device follow signal).
        self.on_activity: Optional[Callable[[str], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Connect with multi-version WS support (B12 fix: websockets>=14 changed API)."""
        self._ws = None
        try:
            # Try websockets.sync.client (websockets >=12, preferred)
            try:
                from websockets.sync.client import connect as ws_connect  # type: ignore
                self._ws = ws_connect(self.ws_url)
                self._connected = True
            except ImportError:
                # Try websocket-client library (sync, alternative)
                try:
                    import websocket  # type: ignore
                    self._ws = websocket.create_connection(self.ws_url)
                    self._connected = True
                except ImportError:
                    # Fallback: legacy websockets <14 with __enter__
                    import websockets  # type: ignore
                    self._ws = websockets.connect(self.ws_url).__enter__()
                    self._connected = True

            if self._connected:
                self._send({"type": "join_conversation", "conversation_id": self.conversation_id})
                self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
                self._recv_thread.start()
                if self.on_connected:
                    self.on_connected()
                return True
            return False
        except Exception as e:  # noqa: BLE001
            self._connected = False
            self._ws = None
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

    def join_conversation(self, conversation_id: str) -> None:
        """Switch this socket to another room (server moves a socket out of its
        previous room on join) and remember it for reconnects, so live
        cross-client broadcasts for the newly opened conversation arrive."""
        self.conversation_id = conversation_id
        self._send({"type": "join_conversation", "conversation_id": conversation_id})

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
        # Connection lost — mark offline and try to reconnect if allowed
        if self._connected:
            self._connected = False
            if self.on_disconnected:
                self.on_disconnected()
            # Auto-reconnect (best-effort, up to 10 attempts)
            if getattr(self, "_should_reconnect", True) and getattr(self, "_reconnect_attempts", 0) < 10:
                self._schedule_reconnect()

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
        elif t == "room_message":
            if self.on_room_message:
                self.on_room_message(data.get("message_id", ""), data.get("content", ""))
        elif t == "conversation_activity":
            # Owner-wide signal: another device moved the active conversation.
            if self.on_activity:
                self.on_activity(data.get("conversation_id", ""))
        elif t == "error":
            if self.on_error:
                self.on_error(data.get("message", "Chat error"))

    def close(self) -> None:
        self._connected = False
        self._should_reconnect = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None

    def _schedule_reconnect(self) -> None:
        """Auto-reconnect with exponential backoff (P2: desktop parity with web)."""
        if not getattr(self, "_should_reconnect", True):
            return
        import time
        delay = min(30, 1 * (2 ** getattr(self, "_reconnect_attempts", 0)))
        self._reconnect_attempts = getattr(self, "_reconnect_attempts", 0) + 1
        time.sleep(delay)
        if self._should_reconnect:
            self.connect()

def pick_shared_conversation(client, settings) -> str:
    """The owner's most recently active conversation (None when unreachable).

    Used by the desktop app to open where the owner last left off on ANY
    device. Falls back to "" when unreachable (caller uses a private room)."""
    try:
        data = client.list_conversations(limit=20)
        conversations = data.get("conversations") or []
        if not conversations:
            return ""
        latest = conversations[0].get("id") or ""
        if latest:
            settings.set("conversation_id", latest)
        return latest
    except Exception:
        return ""


def should_follow_newest(conversations, current_id, user_picked, composer_has_text) -> bool:
    """Decide whether a UI should follow the owner's newest conversation.

    Follow when the newest room differs from the current one, the user has
    not manually picked a room this session, and nothing is being typed
    (never yank a room out from under an in-progress message)."""
    if user_picked or composer_has_text or not conversations:
        return False
    newest = conversations[0][0] if isinstance(conversations[0], (list, tuple)) else conversations[0].get("id")
    return bool(newest) and newest != current_id
