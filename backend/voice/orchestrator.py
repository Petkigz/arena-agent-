"""Voice pipeline orchestrator - coordinates audio capture, wake word, VAD, STT, and TTS."""

import asyncio
import time
import numpy as np
from typing import Optional, Callable, Set
from enum import Enum
from app.utils.logger import app_logger

from backend.voice.audio_capture import AudioCaptureService
from backend.voice.wake_word import WakeWordDetector
from backend.voice.vad import VoiceActivityDetector
from backend.voice.stt import SpeechToTextService
from backend.voice.tts import TextToSpeechService


class VoiceState(str, Enum):
    """Voice pipeline states."""
    IDLE = "idle"
    LISTENING = "listening"       # Wake word detected, waiting for speech
    RECORDING = "recording"       # Speech detected, recording
    PROCESSING = "processing"     # Transcribing speech
    THINKING = "thinking"         # Waiting for cognitive response
    SPEAKING = "speaking"         # Playing TTS audio


class VoicePipelineStartupError(RuntimeError):
    """A required voice component could not start.

    Voice is an explicit capability.  The pipeline must not report itself as
    running when one of its required pieces silently returned without doing
    anything.  Keeping the component, cause, and remediation separate lets the
    WebSocket/API surface tell the owner what failed instead of hiding it behind
    an empty transcript or a dead microphone.
    """

    def __init__(self, component: str, reason: str, remediation: str):
        self.component = component
        self.reason = reason
        self.remediation = remediation
        super().__init__(
            f"Voice component '{component}' failed to start: {reason}. "
            f"{remediation}"
        )

    def as_dict(self) -> dict:
        return {
            "component": self.component,
            "reason": self.reason,
            "remediation": self.remediation,
        }


class VoicePipeline:
    """
    Orchestrates the voice pipeline with barge-in support:
    1. Audio capture (always running)
    2. Wake word detection (always listening in IDLE)
    3. VAD (when wake word detected)
    4. STT (when speech ends)
    5. TTS (when response ready)

    Barge-in: If wake word detected while SPEAKING, stop TTS and start listening.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        wake_word: str = "hey_jarvis",
        wake_word_sensitivity: float = 0.5,
        vad_threshold: float = 0.5,
        stt_model: str = "base",
        tts_voice: str = "en_US-lessac-medium",
        tts_speed: float = 1.0,
        noise_suppression: bool = True,
        on_wake_word: Optional[Callable[[], None]] = None,
        on_transcript: Optional[Callable[[str, bool], None]] = None,
        on_state_change: Optional[Callable[[VoiceState, VoiceState], None]] = None,
        on_audio_ready: Optional[Callable[[bytes], None]] = None,
        on_error: Optional[Callable[[VoicePipelineStartupError], object]] = None,
    ):
        self.sample_rate = sample_rate

        # Initialize components (lazy - will be created on start)
        self.audio_capture: Optional[AudioCaptureService] = None
        self.wake_word: Optional[WakeWordDetector] = None
        self.vad: Optional[VoiceActivityDetector] = None
        self.stt: Optional[SpeechToTextService] = None
        self.tts: Optional[TextToSpeechService] = None

        # Settings
        self._wake_word_name = wake_word
        self._wake_word_sensitivity = wake_word_sensitivity
        self._vad_threshold = vad_threshold
        self._stt_model = stt_model
        self._tts_voice = tts_voice
        self._tts_speed = tts_speed
        self.noise_suppression = bool(noise_suppression)

        # State
        self.state = VoiceState.IDLE
        self.is_running = False
        self.current_time = 0.0

        # Task tracking for proper error handling
        self._tasks: Set[asyncio.Task] = set()

        # External callbacks
        self._on_wake_word = on_wake_word
        self._on_transcript = on_transcript
        self._on_state_change = on_state_change
        self._on_audio_ready = on_audio_ready
        self._on_error = on_error

    @property
    def on_state_change(self):
        """Get the state change callback."""
        return self._on_state_change

    @on_state_change.setter
    def on_state_change(self, callback: Optional[Callable[[VoiceState, VoiceState], None]]):
        """Set the state change callback."""
        self._on_state_change = callback

    @staticmethod
    def _component_error(component: object, name: str, remediation: str) -> VoicePipelineStartupError:
        reason = getattr(component, "last_error", None) or (
            "start() returned without marking the component as running"
        )
        return VoicePipelineStartupError(name, str(reason), remediation)

    def _require_model(self, component: object, name: str, remediation: str) -> None:
        if getattr(component, "model", None) is None:
            raise self._component_error(component, name, remediation)

    def _start_required(
        self,
        component: object,
        name: str,
        remediation: str,
        model_attr: Optional[str] = None,
    ) -> None:
        try:
            component.start()
        except VoicePipelineStartupError:
            raise
        except Exception as exc:
            raise VoicePipelineStartupError(
                name,
                f"{type(exc).__name__}: {exc}",
                remediation,
            ) from exc
        if not bool(getattr(component, "is_running", False)):
            raise self._component_error(component, name, remediation)
        if model_attr is not None and getattr(component, model_attr, None) is None:
            raise self._component_error(component, name, remediation)

    async def start(self):
        """Start every required component or report the exact failed component.

        A partially available voice stack is not a working voice stack.  This
        method deliberately fails closed instead of starting a silent pipeline
        with a missing microphone, wake-word model, STT model, or TTS model.
        """
        if self.is_running:
            return

        app_logger.info("Starting voice pipeline")

        try:
            # Create components before touching the microphone.  VAD loads its
            # model during construction, so its failure can be reported before
            # any OS audio resource is acquired.
            self.audio_capture = AudioCaptureService(sample_rate=self.sample_rate)
            self.wake_word = WakeWordDetector(
                wake_word=self._wake_word_name,
                sensitivity=self._wake_word_sensitivity,
                sample_rate=self.sample_rate,
            )
            self.vad = VoiceActivityDetector(threshold=self._vad_threshold)
            self.stt = SpeechToTextService(model_size=self._stt_model)
            self.tts = TextToSpeechService(voice=self._tts_voice, speed=self._tts_speed)

            # Setup internal callbacks
            self.audio_capture.on_audio_chunk = self._on_audio_chunk
            self.wake_word.on_wake_word_detected = self._handle_wake_word
            self.vad.on_speech_start = self._handle_speech_start
            self.vad.on_speech_end = self._handle_speech_end

            self._require_model(
                self.vad,
                "vad",
                "Install the voice dependencies and ensure the Silero VAD model "
                "is available locally before retrying.",
            )
            self._start_required(
                self.wake_word,
                "wake_word",
                "Install openwakeword and its model files, then retry voice start.",
                model_attr="model",
            )
            self._start_required(
                self.stt,
                "stt",
                "Install faster-whisper and ensure the selected Whisper model can "
                "be loaded locally before retrying.",
                model_attr="model",
            )
            self._start_required(
                self.tts,
                "tts",
                "Install Piper and the selected .onnx voice model, then retry voice start.",
                model_attr="model",
            )
            # Start the microphone last so a dependency/model failure cannot
            # leave an active audio stream behind.
            self._start_required(
                self.audio_capture,
                "audio_capture",
                "Install PyAudio and verify that an input device is available, "
                "then retry voice start.",
            )

            self.is_running = True
            self._set_state(VoiceState.IDLE)
            app_logger.info("Voice pipeline started successfully")

        except VoicePipelineStartupError as exc:
            app_logger.error(str(exc))
            await self.stop()
            raise
        except Exception as exc:
            error = VoicePipelineStartupError(
                "pipeline",
                f"{type(exc).__name__}: {exc}",
                "Inspect the chained startup error and correct it before retrying.",
            )
            app_logger.error(str(error))
            await self.stop()
            raise error from exc

    async def stop(self):
        """Stop all pipeline components and cancel pending tasks.

        Cleanup must also run after a *partial* startup.  ``is_running`` is set
        only after every component succeeds, so using it as the sole guard leaks
        whichever resources started before a later component failed.
        """
        components_exist = any(
            component is not None
            for component in (
                self.audio_capture,
                self.wake_word,
                self.vad,
                self.stt,
                self.tts,
            )
        )
        if not self.is_running and not components_exist and not self._tasks:
            return

        app_logger.info("Stopping voice pipeline")
        self.is_running = False

        # Cancel all pending tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        # Stop every constructed component, even if startup failed part-way.
        for attr_name in ("audio_capture", "wake_word", "vad", "stt", "tts"):
            component = getattr(self, attr_name)
            if component is None:
                continue
            try:
                component.stop()
            except Exception as exc:
                app_logger.error(
                    "Failed to stop voice component %s: %s",
                    attr_name,
                    exc,
                    exc_info=True,
                )
            finally:
                setattr(self, attr_name, None)

        self._set_state(VoiceState.IDLE)
        app_logger.info("Voice pipeline stopped")

    async def speak(self, text: str):
        """Synthesize and stream speech audio."""
        if not self.is_running or not self.tts:
            app_logger.warning("Cannot speak: pipeline not running")
            return

        self._set_state(VoiceState.SPEAKING)

        task = asyncio.create_task(self._synthesize_and_stream(text))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def update_wake_word(self, model_name: str):
        """Update wake word model."""
        self._wake_word_name = model_name
        if self.wake_word:
            self.wake_word.stop()
            self.wake_word = WakeWordDetector(
                wake_word=model_name,
                sensitivity=self._wake_word_sensitivity,
                sample_rate=self.sample_rate,
            )
            self.wake_word.on_wake_word_detected = self._handle_wake_word
            self.wake_word.start()

    # --- Internal handlers ---

    def _on_audio_chunk(self, audio_chunk: np.ndarray):
        """Process incoming audio chunk based on current state."""
        if not self.is_running:
            return

        if self.state == VoiceState.IDLE:
            # Feed to wake word detector
            if self.wake_word:
                self.wake_word.process_audio(audio_chunk)

        elif self.state in (VoiceState.LISTENING, VoiceState.RECORDING):
            # Feed to VAD
            self.current_time += len(audio_chunk) / self.sample_rate
            if self.vad:
                self.vad.process_audio(audio_chunk, self.current_time)

        elif self.state == VoiceState.SPEAKING:
            # BARGE-IN: Listen for wake word even while speaking
            if self.wake_word:
                detected = self.wake_word.process_audio(audio_chunk)
                if detected:
                    app_logger.info("Barge-in detected during speech")
                    # Stop current TTS by resetting state
                    self._set_state(VoiceState.LISTENING)
                    if self.vad:
                        self.vad.start()
                    self.current_time = 0.0

    def _handle_wake_word(self, wake_word: str):
        """Handle wake word detection."""
        app_logger.info(f"Wake word detected: {wake_word}")

        self._set_state(VoiceState.LISTENING)

        if self.vad:
            self.vad.start()
        self.current_time = 0.0

        if self._on_wake_word:
            try:
                self._on_wake_word()
            except Exception as e:
                app_logger.error(f"Wake word callback error: {e}")

    def _handle_speech_start(self):
        """Handle speech start."""
        app_logger.info("Speech started")
        self._set_state(VoiceState.RECORDING)

    async def _notify_error(self, error: VoicePipelineStartupError) -> None:
        """Notify the service/UI about a runtime component failure."""
        if not self._on_error:
            return
        try:
            result = self._on_error(error)
            if asyncio.iscoroutine(result):
                await result
        except Exception as callback_error:
            app_logger.error(f"Voice error callback failed: {callback_error}", exc_info=True)

    def _handle_speech_end(self, audio: np.ndarray):
        """Handle speech end - transcribe."""
        app_logger.info(f"Speech ended, transcribing {len(audio)} samples")
        self._set_state(VoiceState.PROCESSING)

        task = asyncio.create_task(self._transcribe_audio(audio))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _transcribe_audio(self, audio: np.ndarray):
        """Transcribe audio asynchronously."""
        try:
            if not self.stt:
                raise VoicePipelineStartupError(
                    "stt",
                    "The STT component is not attached to the running pipeline",
                    "Restart voice so the required STT component is initialized "
                    "before retrying input.",
                )

            result = await self.stt.transcribe_async(audio, sample_rate=self.sample_rate)
            text = result.get("text", "").strip()

            if text:
                app_logger.info(f"Transcription: '{text}'")

                if self._on_transcript:
                    await self._on_transcript(text, True)

                self._set_state(VoiceState.THINKING)
            else:
                app_logger.warning("Transcription returned empty text")
                self._set_state(VoiceState.IDLE)

        except asyncio.CancelledError:
            app_logger.info("Transcription cancelled")
            raise
        except Exception as exc:
            error = VoicePipelineStartupError(
                "stt",
                f"{type(exc).__name__}: {exc}",
                "Inspect the Whisper model/runtime error and correct it before "
                "retrying voice input.",
            )
            app_logger.error("Transcription failed: %s", error)
            await self._notify_error(error)
            self._set_state(VoiceState.IDLE)

    async def _synthesize_and_stream(self, text: str):
        """Synthesize TTS and stream audio via callback."""
        try:
            if not self.tts:
                raise VoicePipelineStartupError(
                    "tts",
                    "The TTS component is not attached to the running pipeline",
                    "Restart voice so the required TTS component is initialized "
                    "before retrying output.",
                )

            audio = await self.tts.synthesize_async(text)

            if audio is None:
                raise VoicePipelineStartupError(
                    "tts",
                    getattr(self.tts, "last_error", None) or "TTS returned no audio",
                    "Inspect the Piper model/runtime error and correct it before "
                    "retrying voice output.",
                )

            # Convert float32 audio to int16 PCM bytes for streaming
            audio_int16 = (audio * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()

            if self._on_audio_ready:
                await self._on_audio_ready(audio_bytes)

        except asyncio.CancelledError:
            app_logger.info("TTS synthesis cancelled")
            raise
        except VoicePipelineStartupError as exc:
            app_logger.error("TTS synthesis failed: %s", exc)
            await self._notify_error(exc)
        except Exception as exc:
            error = VoicePipelineStartupError(
                "tts",
                f"{type(exc).__name__}: {exc}",
                "Inspect the Piper model/runtime error and correct it before "
                "retrying voice output.",
            )
            app_logger.error("TTS synthesis failed: %s", error)
            await self._notify_error(error)
        finally:
            if self.state == VoiceState.SPEAKING:
                self._set_state(VoiceState.IDLE)

    def _set_state(self, new_state: VoiceState):
        """Update voice state and notify callbacks."""
        if self.state == new_state:
            return

        old_state = self.state
        self.state = new_state
        app_logger.info(f"Voice state: {old_state.value} -> {new_state.value}")

        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except Exception as e:
                app_logger.error(f"State change callback error: {e}")


# Backward compatibility alias
VoiceOrchestrator = VoicePipeline
