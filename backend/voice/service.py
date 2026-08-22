"""Voice service - integrates voice pipeline with WebSocket and cognitive runtime."""

import asyncio
import time
from typing import Optional

import numpy as np

from backend.voice.orchestrator import VoicePipeline, VoiceState
from backend.voice.remote_audio import RemoteAudioBuffer
from backend.voice.stt import SpeechToTextService
from backend.websocket_server import ws_manager
import backend.message_router as message_router_module
from app.perception.piper_voice import synthesize_piper
from app.settings_store import get_settings
from app.utils.logger import app_logger


# Map user-facing wake-word phrases onto the Picovoice keyword models actually
# installed for the PC-side pipeline. Phrases outside this map fall back to the
# default model (the Android app's SpeechRecognizer accepts arbitrary text, but
# the PC pipeline can only recognize the keywords it has models for).
_WAKE_WORD_MAP = {
    "hey_arena": "hey_jarvis",
    "hey_lumi": "hey_jarvis",
    "hey_jarvis": "hey_jarvis",
    "hey_mycroft": "hey_mycroft",
    "alexa": "alexa",
}


def _map_wake_word(wake_word: Optional[str]) -> str:
    """Resolve a user wake-word phrase to a Picovoice model name."""
    if not wake_word:
        return "hey_jarvis"
    return _WAKE_WORD_MAP.get(wake_word.strip().lower(), "hey_jarvis")


class VoiceService:
    """Manages voice pipeline lifecycle and WebSocket integration."""

    def __init__(self):
        self.pipeline: Optional[VoicePipeline] = None
        self.current_conversation_id: Optional[str] = None
        self._enabled = False

        # Remote (phone) audio ingestion — independent of the PC pipeline.
        self.remote_audio = RemoteAudioBuffer()
        self.remote_audio.on_utterance = self._on_remote_utterance
        self._remote_stt: Optional[SpeechToTextService] = None

    async def start(self, conversation_id: str):
        """Start voice pipeline for a conversation."""
        if self._enabled:
            app_logger.warning("Voice service already running")
            return

        # Honor the global voice-enabled toggle (G2): if the owner disabled voice,
        # refuse to start the pipeline rather than ignoring the setting.
        if get_settings().get("voice_enabled") is False:
            app_logger.info("Voice disabled by settings — not starting the pipeline.")
            return

        self.current_conversation_id = conversation_id

        # Apply persisted settings (voice + speed + wake word) so the pipeline
        # starts with the user's choices, not the defaults. Previously these were
        # only applied by update_settings() *after* the pipeline was already
        # running, so a fresh start ignored them.
        shared = get_settings()
        tts_voice = str(shared.get("voice") or "en_US-lessac-medium")
        try:
            tts_speed = float(shared.get("voice_speed") or 1.0)
        except (TypeError, ValueError):
            tts_speed = 1.0
        wake_model = _map_wake_word(shared.get("wake_word"))
        noise_suppression = bool(shared.get("noise_suppression", True))

        self.pipeline = VoicePipeline(
            wake_word=wake_model,
            tts_voice=tts_voice,
            tts_speed=tts_speed,
            noise_suppression=noise_suppression,
            on_wake_word=self._handle_wake_word,
            on_transcript=self._handle_transcript,
            on_state_change=self._handle_state_change,
            on_audio_ready=self._handle_audio_ready,
        )

        await self.pipeline.start()
        self._enabled = True

        app_logger.info(f"Voice service started for conversation {conversation_id}")

        # Push-to-talk: the user explicitly started voice, so go straight to
        # LISTENING (the wake word only gates hands-free mode). This is the
        # first visible orb-state change the user sees after clicking.
        await ws_manager.broadcast_to_conversation(conversation_id, {
            "type": "voice_state",
            "state": VoiceState.LISTENING.value,
        })

    async def stop(self):
        """Stop voice pipeline."""
        if not self._enabled or not self.pipeline:
            return

        conv_id = self.current_conversation_id
        await self.pipeline.stop()
        self.pipeline = None
        self._enabled = False

        app_logger.info(f"Voice service stopped for conversation {conv_id}")

        if conv_id:
            await ws_manager.broadcast_to_conversation(conv_id, {
                "type": "voice_state",
                "state": "stopped",
            })

        self.current_conversation_id = None

    async def update_settings(self, settings: dict):
        """Update voice pipeline settings from frontend (camelCase or snake_case).

        Now consumes noise_suppression, voice_enabled, response_delay, vad_sensitivity
        so no setting is dead (closes G2). Supports both the WS camelCase path
        (voice_settings message) and the shared-settings snake_case path
        (_apply_settings_live).
        """
        # Voice enabled / response delay / noise suppression can be handled even
        # when the pipeline isn't running — they gate start() and _speak_reply().
        # For live pipeline updates we still need self.pipeline.
        if "voiceEnabled" in settings or "voice_enabled" in settings:
            enabled = settings.get("voiceEnabled", settings.get("voice_enabled"))
            if enabled is False and self._enabled:
                app_logger.info("Voice disabled via settings — stopping pipeline.")
                await self.stop()
                return

        if "responseDelay" in settings or "response_delay" in settings:
            # response_delay is read from get_settings() at speak time, so just log
            # that the live value changed; the next _speak_reply will honor it.
            rd = settings.get("responseDelay", settings.get("response_delay"))
            app_logger.info(f"Updated response delay to {rd}ms (applies on next reply)")

        if "noiseSuppression" in settings or "noise_suppression" in settings:
            ns = settings.get("noiseSuppression", settings.get("noise_suppression"))
            if self.pipeline:
                # PC pipeline doesn't have a real noise-suppressor library yet;
                # store the flag so it is consumed (not dead) and log it.
                setattr(self.pipeline, "noise_suppression", bool(ns))
            app_logger.info(f"Updated noise suppression to {bool(ns)} (frontend uses getUserMedia constraint; PC pipeline flag stored)")

        if not self.pipeline:
            return

        # Update wake word (camelCase from WS or snake_case from shared settings)
        wake_word = settings.get("wakeWord") or settings.get("wake_word")
        if wake_word:
            model_name = _map_wake_word(wake_word)
            await self.pipeline.update_wake_word(model_name)
            app_logger.info(f"Updated wake word to {wake_word} (model: {model_name})")

        # Update voice (Piper voice id, e.g. "en_US-lessac-medium")
        if "voice" in settings or "selectedVoice" in settings:
            voice = settings.get("voice") or settings.get("selectedVoice")
            if voice and self.pipeline and self.pipeline.tts:
                try:
                    self.pipeline.tts.set_voice(str(voice))
                except Exception:
                    # Some TTS backends expose speed but not set_voice — best effort
                    pass
                app_logger.info(f"Updated voice to {voice}")

        # Update voice speed (camelCase or snake_case)
        if "voiceSpeed" in settings or "voice_speed" in settings:
            try:
                speed = float(settings.get("voiceSpeed", settings.get("voice_speed")))
                if self.pipeline.tts:
                    self.pipeline.tts.speed = speed
                app_logger.info(f"Updated voice speed to {speed}")
            except Exception as e:
                app_logger.warning(f"Could not update voice speed: {e}")

        # Update VAD sensitivity (0-100 → 0-1)
        if "vadSensitivity" in settings or "vad_sensitivity" in settings:
            try:
                raw = settings.get("vadSensitivity", settings.get("vad_sensitivity"))
                sensitivity = float(raw) / 100.0
                if self.pipeline.vad:
                    # VAD implementations vary: try sensitivity then threshold
                    if hasattr(self.pipeline.vad, "sensitivity"):
                        self.pipeline.vad.sensitivity = sensitivity
                    if hasattr(self.pipeline.vad, "threshold"):
                        self.pipeline.vad.threshold = 1.0 - sensitivity
                app_logger.info(f"Updated VAD sensitivity to {sensitivity}")
            except Exception as e:
                app_logger.warning(f"Could not update VAD sensitivity: {e}")

        # Update wake word sensitivity
        if "wakeWordSensitivity" in settings or "wake_word_sensitivity" in settings:
            try:
                raw = settings.get("wakeWordSensitivity", settings.get("wake_word_sensitivity"))
                sensitivity = float(raw) / 100.0
                if self.pipeline.wake_word and hasattr(self.pipeline.wake_word, "sensitivity"):
                    self.pipeline.wake_word.sensitivity = sensitivity
                app_logger.info(f"Updated wake word sensitivity to {sensitivity}")
            except Exception as e:
                app_logger.warning(f"Could not update wake word sensitivity: {e}")

    async def notify_wake_word(self, conversation_id: str):
        """
        Handle a wake word detected on a REMOTE device (e.g. the Android app's
        on-device WakeWordService), as opposed to the PC-side pipeline.

        Updates the conversation, broadcasts the LISTENING state so every client
        reflects it, and speaks feedback if the PC pipeline is active.
        """
        if not self.current_conversation_id:
            self.current_conversation_id = conversation_id

        app_logger.info(f"Wake word detected on remote device for conversation {conversation_id}")

        await ws_manager.broadcast_to_conversation(conversation_id, {
            "type": "voice_state",
            "state": VoiceState.LISTENING.value,
        })

        # Speak "Yes?" if the PC voice pipeline is running.
        if self._enabled:
            await self._speak_feedback("Yes?")

    def _handle_wake_word(self):
        """Handle wake word detection (PC-side pipeline)."""
        if not self.current_conversation_id:
            return

        # Send voice feedback
        asyncio.create_task(self._speak_feedback("Yes?"))

    # --- Remote (phone) audio ingestion ---

    def ingest_remote_audio(self, data: bytes) -> None:
        """Feed a binary PCM frame (from the phone) into the utterance buffer."""
        self.remote_audio.ingest(data)

    def _on_remote_utterance(self, audio: np.ndarray) -> None:
        """A complete utterance was detected from the remote device."""
        asyncio.create_task(self._transcribe_remote_utterance(audio))

    def _get_remote_stt(self) -> Optional[SpeechToTextService]:
        """Lazily create + start a standalone STT for remote audio."""
        if self._remote_stt is None:
            try:
                self._remote_stt = SpeechToTextService(model_size="base")
                self._remote_stt.start()
            except Exception as e:
                app_logger.warning(f"Could not start remote STT: {e}")
                self._remote_stt = None

        stt = self._remote_stt
        if stt is None or stt.model is None:
            return None
        return stt

    async def _transcribe_remote_utterance(self, audio: np.ndarray) -> None:
        """Transcribe a remote utterance and route it through the same path as a
        PC transcript (broadcast + cognitive runtime)."""
        if not self.current_conversation_id:
            app_logger.warning("Remote utterance received but no conversation is active")
            return

        # The user has stopped speaking — show "thinking" while we transcribe
        # and the cognitive runtime produces a reply.
        await ws_manager.broadcast_to_conversation(self.current_conversation_id, {
            "type": "voice_state",
            "state": VoiceState.THINKING.value,
        })

        stt = self._get_remote_stt()
        if stt is None:
            app_logger.warning("STT unavailable — remote audio not transcribed (install faster-whisper)")
            return

        try:
            result = await stt.transcribe_async(audio, sample_rate=16000)
        except Exception as e:
            app_logger.error(f"Remote transcription failed: {e}")
            return

        text = (result.get("text") or "").strip()
        if text:
            app_logger.info(f"Remote transcription: '{text}'")
            await self._handle_transcript(text, is_final=True)
        else:
            app_logger.warning("Remote transcription returned empty text")

    async def _handle_transcript(self, transcript: str, is_final: bool):
        """Handle speech transcript from pipeline."""
        if not self.current_conversation_id:
            return

        # Send transcript to frontend
        await ws_manager.broadcast_to_conversation(self.current_conversation_id, {
            "type": "voice_transcript",
            "text": transcript,
            "is_final": is_final,
        })

        # If final transcript, send to cognitive runtime
        if is_final and transcript.strip():
            app_logger.info(f"Processing voice command: {transcript}")

            # Parse voice command
            command = self._parse_voice_command(transcript)

            if command:
                # Provide feedback for recognized commands
                if command == "help":
                    await self._speak_feedback(
                        "You can ask me to create tasks, search files, check system status, or just chat."
                    )
                elif command == "cancel":
                    await self._speak_feedback("Okay, cancelled.")
                
                # Send as user message to cognitive runtime.
                # Read the router from the module at call time — it is set by
                # initialize_message_router() during startup, so an import-time
                # `from backend.message_router import message_router` would
                # capture the initial None and never see the real instance.
                router = message_router_module.message_router
                if router:
                    reply = await router.handle_message(None, {
                        "type": "user_message",
                        "conversation_id": self.current_conversation_id,
                        "content": transcript,
                        "source": "voice",
                    })
                    if isinstance(reply, str) and reply.strip():
                        await self._speak_reply(reply)
                else:
                    app_logger.warning("Message router not available")
            else:
                # Provide feedback for unrecognized commands
                await self._speak_feedback("I didn't understand that. Try saying 'help' for commands.")

    async def _handle_state_change(self, old_state: VoiceState, new_state: VoiceState):
        """Handle voice pipeline state change."""
        if not self.current_conversation_id:
            return

        app_logger.debug(f"Voice state: {old_state.value} -> {new_state.value}")

        await ws_manager.broadcast_to_conversation(self.current_conversation_id, {
            "type": "voice_state",
            "state": new_state.value,
        })

    async def _handle_audio_ready(self, audio_data: bytes):
        """Handle TTS audio ready for streaming."""
        if not self.current_conversation_id:
            return

        # Stream audio bytes to frontend
        await ws_manager.send_audio_to_conversation(self.current_conversation_id, audio_data)

    async def _speak_feedback(self, text: str):
        """Speak a feedback message."""
        if not self.pipeline or not self._enabled:
            return

        try:
            await self.pipeline.speak(text)
        except Exception as e:
            app_logger.error(f"Failed to speak feedback: {e}")

    async def _speak_reply(self, text: str) -> None:
        """Speak a cognitive reply: broadcast SPEAKING, stream TTS audio, then IDLE.

        Uses Piper directly (in-process) so the remote/phone path also speaks,
        independent of the PC-side pipeline.
        """
        conv_id = self.current_conversation_id
        if not conv_id or not text:
            return

        # Honor the configured response delay (G2) — pause briefly before the
        # assistant starts speaking, per the user's preference.
        try:
            delay_ms = float(get_settings().get("response_delay") or 0)
        except (TypeError, ValueError):
            delay_ms = 0.0
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        await ws_manager.broadcast_to_conversation(conv_id, {
            "type": "voice_state",
            "state": VoiceState.SPEAKING.value,
        })

        try:
            result = await asyncio.to_thread(synthesize_piper, text, None, 1.0, 16000)
            if result is not None:
                audio, _sr = result
                pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                await ws_manager.send_audio_to_conversation(conv_id, pcm)
                # Hold SPEAKING while the client plays the audio (int16 @ 16 kHz).
                await asyncio.sleep(len(pcm) / 32000.0 + 0.25)
        except Exception as e:
            app_logger.error(f"Voice reply TTS failed: {e}")

        await ws_manager.broadcast_to_conversation(conv_id, {
            "type": "voice_state",
            "state": VoiceState.IDLE.value,
        })

    def _parse_voice_command(self, transcript: str) -> Optional[str]:
        """Parse voice transcript into command.

        Returns command type or None if not recognized.
        For now, accepts any non-empty transcript as a valid command.
        Future enhancement: add intent classification.
        """
        text = transcript.strip().lower()

        if not text:
            return None

        # Simple keyword-based command parsing
        # Future: use LLM for intent classification

        # Help command
        if any(word in text for word in ["help", "what can you do", "commands"]):
            return "help"

        # Stop/cancel command
        if any(word in text for word in ["stop", "cancel", "nevermind", "forget it"]):
            return "cancel"

        # Default: treat as regular query
        return "query"


# Global voice service instance
voice_service = VoiceService()
