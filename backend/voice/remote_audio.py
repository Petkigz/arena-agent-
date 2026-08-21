"""Remote (phone) audio ingestion — browser-free and dependency-light.

The Android app streams raw int16 PCM (16 kHz, mono, little-endian) over the
WebSocket as binary frames. This module:

1. Converts the incoming bytes to float32 numpy.
2. Detects the end of an utterance with a lightweight energy-based (RMS) silence
   detector — no PyTorch/Silero required, so it works even before heavy deps are
   installed.
3. Emits the complete utterance via an `on_utterance` callback, which the
   VoiceService wires to STT → transcript → cognitive runtime.

This is deliberately independent of the PC-side VoicePipeline (which captures
audio from the local microphone). Binary frames on /ws always originate from a
remote device (the phone).
"""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np

from app.utils.logger import app_logger


class RemoteAudioBuffer:
    """Accumulates streamed PCM and detects utterance boundaries by energy."""

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_threshold: float = 0.01,   # RMS (float [-1,1]) below which = silence
        min_utterance_ms: int = 250,       # ignore shorter than this
        max_silence_ms: int = 700,         # this much silence ends an utterance
        max_utterance_ms: int = 15_000,    # hard cap, force-finalize
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.min_utterance_ms = min_utterance_ms
        self.max_silence_ms = max_silence_ms
        self.max_utterance_ms = max_utterance_ms

        self._speaking = False
        self._silence_duration = 0.0
        self._speech_frames: List[np.ndarray] = []

        #: Callable[[np.ndarray], None] — invoked with the full float32 utterance.
        self.on_utterance: Optional[Callable[[np.ndarray], None]] = None

    def ingest(self, data: bytes) -> None:
        """Ingest a binary PCM frame from the WebSocket."""
        if not data:
            return
        audio = self._bytes_to_float32(data)
        self._process(audio)

    def reset(self) -> None:
        """Discard any in-progress utterance."""
        self._speaking = False
        self._silence_duration = 0.0
        self._speech_frames = []

    @staticmethod
    def _bytes_to_float32(data: bytes) -> np.ndarray:
        # Android sends little-endian int16 PCM.
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        return arr / 32768.0

    def _process(self, audio: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if len(audio) else 0.0

        if rms >= self.silence_threshold:
            # Speech present.
            if not self._speaking:
                self._speaking = True
                self._speech_frames = [audio]
            else:
                self._speech_frames.append(audio)
            self._silence_duration = 0.0

            # Hard cap: finalize if the utterance is getting too long.
            total_ms = sum(len(f) for f in self._speech_frames) / self.sample_rate * 1000.0
            if total_ms >= self.max_utterance_ms:
                self._finalize()
        else:
            # Silence present.
            if self._speaking:
                # Do NOT append trailing silence to the utterance — it is only the
                # end-of-speech trigger, and including it would inflate the
                # duration check (a short word + long silence would wrongly pass).
                self._silence_duration += len(audio) / self.sample_rate
                if self._silence_duration * 1000.0 >= self.max_silence_ms:
                    self._finalize()
            # Not speaking: ignore leading silence.

    def _finalize(self) -> None:
        utterance = np.concatenate(self._speech_frames) if self._speech_frames else np.array([])
        self._speaking = False
        self._silence_duration = 0.0
        self._speech_frames = []

        duration_ms = len(utterance) / self.sample_rate * 1000.0 if len(utterance) else 0.0
        if duration_ms < self.min_utterance_ms:
            app_logger.debug(f"Remote utterance too short ({duration_ms:.0f}ms), ignored")
            return

        app_logger.info(f"Remote utterance finalized ({duration_ms:.0f}ms, {len(utterance)} samples)")
        if self.on_utterance:
            try:
                self.on_utterance(utterance)
            except Exception as e:
                app_logger.error(f"on_utterance callback error: {e}")
