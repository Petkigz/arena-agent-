"""Voice capture + backend streaming for the native desktop client.

The desktop app behaves like the Android phone: it captures mic audio (PyAudio),
streams raw int16 PCM over the backend WebSocket, and the backend handles
utterance detection → STT → cognitive runtime (backend/voice/remote_audio.py).
The reply streams back as `message_token` frames, which are accumulated here.

GUI-free; degrades gracefully when PyAudio / a mic / websockets is absent.
"""

from __future__ import annotations

import json
import threading
from typing import Callable, Optional

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    PYAUDIO_AVAILABLE = False

SAMPLE_RATE = 16000
CHUNK = 1024


def accumulate_tokens(event: dict, parts: list) -> Optional[str]:
    """Pure helper: fold a message_token event into `parts`.

    Returns the completed reply string when `done` is True (and clears `parts`),
    otherwise None. Unit-tested without a WebSocket.
    """
    if not isinstance(event, dict) or event.get("type") != "message_token":
        return None
    token = event.get("token", "")
    if isinstance(token, str):
        parts.append(token)
    if event.get("done"):
        reply = "".join(parts)
        parts.clear()
        return reply
    return None


class DesktopVoiceClient:
    def __init__(self, ws_url: str = "ws://localhost:8000/ws", conversation_id: str = "desktop-voice"):
        self.ws_url = ws_url
        self.conversation_id = conversation_id
        self._ws = None
        self._capturing = False
        self._capture_thread: Optional[threading.Thread] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._reply_parts: list = []

        #: Called with the full assistant reply text.
        self.on_reply: Optional[Callable[[str], None]] = None
        #: Called with (text, is_final) for live transcripts.
        self.on_transcript: Optional[Callable[[str, bool], None]] = None
        #: Called with an error string.
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def available(self) -> bool:
        return PYAUDIO_AVAILABLE

    def start(self) -> bool:
        if not self.available:
            if self.on_error:
                self.on_error("Microphone unavailable (install PyAudio).")
            return False
        if self._capturing:
            return True

        try:
            import websockets
            self._ws = websockets.connect(self.ws_url).__enter__()
            self._send({"type": "join_conversation", "conversation_id": self.conversation_id})
        except Exception as e:
            self._ws = None
            if self.on_error:
                self.on_error(f"Could not connect voice WebSocket: {e}")
            return False

        self._capturing = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        return True

    def stop(self) -> None:
        self._capturing = False
        for t in (self._capture_thread, self._recv_thread):
            if t is not None:
                t.join(timeout=2.0)
        self._capture_thread = None
        self._recv_thread = None
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ── loops ───────────────────────────────────────────────────────────────
    def _capture_loop(self) -> None:
        pa = None
        stream = None
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                input=True, frames_per_buffer=CHUNK,
            )
        except Exception as e:
            self._capturing = False
            if self.on_error:
                self.on_error(f"Could not open microphone: {e}")
            return

        try:
            while self._capturing:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                except Exception:
                    break
                if data and self._ws is not None:
                    self._ws.send(data)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            try:
                pa.terminate()
            except Exception:
                pass

    def _recv_loop(self) -> None:
        while self._capturing and self._ws is not None:
            try:
                frame = self._ws.recv()
            except Exception:
                break
            if isinstance(frame, (bytes, bytearray)):
                continue  # audio echo / binary
            self._handle_text(frame)

    # ── message handling ────────────────────────────────────────────────────
    def _handle_text(self, text: str) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        t = data.get("type")
        if t == "voice_transcript":
            if self.on_transcript:
                self.on_transcript(data.get("text", ""), bool(data.get("is_final", False)))
        elif t == "message_token":
            reply = accumulate_tokens(data, self._reply_parts)
            if reply is not None and self.on_reply:
                self.on_reply(reply)
        elif t == "error":
            if self.on_error:
                self.on_error(data.get("message", "Voice error"))

    def _send(self, payload: dict) -> None:
        if self._ws is not None:
            self._ws.send(json.dumps(payload))
