"""Voice capture + backend streaming for the native desktop client.

The desktop app behaves like the Android phone: it captures mic audio (PyAudio),
streams raw int16 PCM over the backend WebSocket, and the backend handles
utterance detection → STT → cognitive runtime (backend/voice/remote_audio.py).
The reply streams back as `message_token` frames, which are accumulated here.

GUI-free; degrades gracefully when PyAudio / a mic / websockets is absent.
"""

from __future__ import annotations

import array
import json
import math
import queue
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
        #: Called with a 0..1 microphone amplitude (drives the reactive orb).
        self.on_level: Optional[Callable[[float], None]] = None
        #: Called with the backend voice pipeline state (listening/thinking/speaking/idle).
        self.on_voice_state: Optional[Callable[[str], None]] = None
        #: Called with a raw int16 PCM chunk (16 kHz mono) of the streamed Piper reply.
        self.on_audio: Optional[Callable[[bytes], None]] = None
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

        self._ws = None
        try:
            # B12 fix: multi-version WS support (sync client for websockets>=14)
            try:
                from websockets.sync.client import connect as ws_connect  # type: ignore
                self._ws = ws_connect(self.ws_url)
            except ImportError:
                try:
                    import websocket  # type: ignore
                    self._ws = websocket.create_connection(self.ws_url)
                except ImportError:
                    import websockets  # type: ignore
                    self._ws = websockets.connect(self.ws_url).__enter__()

            self._send({"type": "join_conversation", "conversation_id": self.conversation_id})
            # Tell the backend to start the voice pipeline so the streamed PCM
            # (remote_audio path) is actually processed (sets current_conversation_id).
            self._send({"type": "voice_start", "conversation_id": self.conversation_id})
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
        if self._ws is not None:
            try:
                self._send({"type": "voice_stop", "conversation_id": self.conversation_id})
            except Exception:
                pass
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
                if self.on_level:
                    self.on_level(self._rms_level(data))
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
                # Streamed Piper reply audio (raw int16 PCM @ 16 kHz). Route it
                # to the audio callback; the desktop player consumes it so it
                # plays the SAME audio the web/phone hear.
                if self.on_audio:
                    self.on_audio(bytes(frame))
                continue
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
        elif t == "voice_state":
            if self.on_voice_state:
                self.on_voice_state(str(data.get("state", "")))
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

    @staticmethod
    def _rms_level(data: bytes) -> float:
        """Normalized 0..1 microphone amplitude from int16 PCM bytes."""
        try:
            if not data:
                return 0.0
            samples = array.array("h", data)
            n = len(samples)
            if n == 0:
                return 0.0
            sumsq = 0.0
            for s in samples:
                f = s / 32768.0
                sumsq += f * f
            rms = math.sqrt(sumsq / n)
            return max(0.0, min(1.0, (rms - 0.02) / 0.3))
        except Exception:
            return 0.0


class DesktopAudioPlayer:
    """Plays the backend's streamed reply audio (raw int16 PCM, 16 kHz mono).

    The backend synthesizes the voice reply with Piper and streams it as binary
    PCM frames over the voice WebSocket. This player consumes those frames via
    PyAudio so the desktop app plays the SAME audio the web/phone hear — there
    is no separate local TTS (which previously caused double speech).

    GUI-free and dependency-light (degrades silently to no-op when PyAudio is
    absent), so it is unit-testable without a display or a sound card.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._queue: "queue.Queue[bytes]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def available(self) -> bool:
        return PYAUDIO_AVAILABLE

    @property
    def playing(self) -> bool:
        """True while the playback loop is running (best-effort; not sample-accurate)."""
        return self._running

    def start(self) -> None:
        """Start the playback loop (no-op if already running or PyAudio absent)."""
        if self._running or not self.available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._thread.start()

    def push(self, pcm: bytes) -> None:
        """Enqueue a PCM chunk for playback (thread-safe; no-op if stopped)."""
        if self._running and pcm:
            self._queue.put(pcm)

    def stop(self) -> None:
        """Stop playback and release the audio device."""
        if not self._running:
            return
        self._running = False
        # Wake the loop if it is blocked on get().
        try:
            self._queue.put_nowait(b"")
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _play_loop(self) -> None:
        pa = None
        stream = None
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                output=True, frames_per_buffer=CHUNK,
            )
        except Exception:
            # No audio device / PyAudio issue — degrade to silent playback.
            self._running = False
            return

        try:
            while self._running:
                chunk = self._queue.get()
                if not chunk:
                    continue
                try:
                    stream.write(chunk)
                except Exception:
                    break
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa is not None:
                try:
                    pa.terminate()
                except Exception:
                    pass
