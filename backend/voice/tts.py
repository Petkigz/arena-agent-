"""Text-to-Speech using Piper (in-process via the ``piper-tts`` package).

The previous implementation shelled out to the ``piper`` CLI binary, which
required ``piper.exe`` to be on ``PATH`` — a frequent silent failure point.
This version uses :func:`app.perception.piper_voice.synthesize_piper`, which
loads the model in-process and resamples to the 16 kHz rate the WebSocket
stream (and the web frontend's ``useVoice`` playback) expects.
"""

import asyncio
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from app.perception.piper_voice import (
    PIPER_AVAILABLE,
    find_model_for_voice,
    get_last_piper_error,
    load_piper_voice,
    synthesize_piper,
)
from app.utils.logger import app_logger

# The raw PCM stream over the WebSocket is played back by the frontend at 16 kHz.
STREAM_SAMPLE_RATE = 16000


class TextToSpeechService:
    """
    Text-to-Speech service using Piper.
    """

    def __init__(
        self,
        voice: str = "en_US-lessac-medium",
        speed: float = 1.0,
        piper_path: str = "piper",  # retained for API compatibility; unused (in-process now)
    ):
        self.voice = voice
        self.speed = speed
        self.piper_path = piper_path

        self.is_running = False
        self.model_path: Optional[Path] = None
        self.model: Optional[object] = None
        self.last_error: Optional[str] = None

        # Callbacks
        self.on_audio_ready: Optional[Callable[[np.ndarray], None]] = None

        self._find_model()

    def _find_model(self):
        """Find the Piper voice model via the shared discovery helper."""
        self.last_error = None
        model = find_model_for_voice(self.voice)
        if model:
            self.model_path = Path(model["path"])
            app_logger.info(f"Found Piper model: {self.model_path}")
        else:
            self.model_path = None
            self.last_error = (
                f"Piper voice model '{self.voice}' was not found "
                "(.onnx and .onnx.json are required)"
            )
            app_logger.error(
                f"{self.last_error}. "
                "Install the selected model before starting local voice."
            )

    def start(self):
        """Start TTS service."""
        if self.is_running:
            return

        if not PIPER_AVAILABLE:
            self.last_error = "The piper-tts Python package is not available"
            app_logger.error(
                f"TTS service cannot start: {self.last_error}. "
                "Install piper-tts before starting local voice."
            )
            return

        if not self.model_path:
            self.last_error = self.last_error or "Piper voice model is not available"
            app_logger.error(f"TTS service cannot start: {self.last_error}")
            return

        self.last_error = None
        self.model = load_piper_voice(self.model_path)
        if self.model is None:
            self.last_error = get_last_piper_error() or (
                f"Piper could not load voice model '{self.model_path}'"
            )
            app_logger.error(f"TTS service cannot start: {self.last_error}")
            return

        self.is_running = True
        app_logger.info(f"TTS service started: voice={self.voice}, speed={self.speed}")

    def stop(self):
        """Stop TTS service."""
        self.is_running = False
        self.model = None
        app_logger.info("TTS service stopped")

    def synthesize(self, text: str) -> Optional[np.ndarray]:
        """
        Synthesize speech from text.

        Returns audio as numpy array (float32, normalized to [-1, 1]) resampled
        to 16 kHz to match the WebSocket stream / frontend playback.
        """
        if not self.is_running or not self.model_path:
            return None

        result = synthesize_piper(
            text,
            voice_id=self.voice,
            speed=self.speed,
            target_sample_rate=STREAM_SAMPLE_RATE,
        )
        if result is None:
            self.last_error = get_last_piper_error() or "Piper returned no audio"
            return None

        audio, _sr = result

        if self.on_audio_ready:
            try:
                self.on_audio_ready(audio)
            except Exception as e:
                app_logger.error(f"TTS audio callback error: {e}")

        return audio

    async def synthesize_async(self, text: str) -> Optional[np.ndarray]:
        """Async wrapper for synthesize."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.synthesize, text)

    def set_voice(self, voice: str):
        """Change TTS voice."""
        self.voice = voice
        self._find_model()
        app_logger.info(f"TTS voice changed to: {voice}")

    def set_speed(self, speed: float):
        """Change TTS speed."""
        self.speed = max(0.5, min(2.0, speed))  # Clamp to [0.5, 2.0]
        app_logger.info(f"TTS speed changed to: {speed}")
