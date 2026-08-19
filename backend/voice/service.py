"""Voice service - integrates voice pipeline with WebSocket and cognitive runtime."""

import asyncio
import time
from typing import Optional
from backend.voice.orchestrator import VoicePipeline, VoiceState
from backend.websocket_server import ws_manager
from backend.message_router import message_router
from app.utils.logger import app_logger


class VoiceService:
    """Manages voice pipeline lifecycle and WebSocket integration."""

    def __init__(self):
        self.pipeline: Optional[VoicePipeline] = None
        self.current_conversation_id: Optional[str] = None
        self._enabled = False

    async def start(self, conversation_id: str):
        """Start voice pipeline for a conversation."""
        if self._enabled:
            app_logger.warning("Voice service already running")
            return

        self.current_conversation_id = conversation_id
        self.pipeline = VoicePipeline(
            on_wake_word=self._handle_wake_word,
            on_transcript=self._handle_transcript,
            on_state_change=self._handle_state_change,
            on_audio_ready=self._handle_audio_ready,
        )

        await self.pipeline.start()
        self._enabled = True

        app_logger.info(f"Voice service started for conversation {conversation_id}")

        await ws_manager.broadcast_to_conversation(conversation_id, {
            "type": "voice_state",
            "state": VoiceState.IDLE.value,
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
        """Update voice pipeline settings from frontend."""
        if not self.pipeline:
            return

        # Update wake word
        if "wakeWord" in settings:
            wake_word = settings["wakeWord"]
            # Map frontend wake words to backend model names
            wake_word_map = {
                "hey_arena": "hey_jarvis",
                "hey_lumi": "hey_jarvis",
                "hey_mycroft": "hey_mycroft",
                "alexa": "alexa",
            }
            model_name = wake_word_map.get(wake_word, "hey_jarvis")
            await self.pipeline.update_wake_word(model_name)
            app_logger.info(f"Updated wake word to {wake_word} (model: {model_name})")

        # Update voice speed
        if "voiceSpeed" in settings:
            speed = float(settings["voiceSpeed"])
            self.pipeline.tts.speed = speed
            app_logger.info(f"Updated voice speed to {speed}")

        # Update VAD sensitivity
        if "vadSensitivity" in settings:
            sensitivity = float(settings["vadSensitivity"]) / 100.0  # Convert 0-100 to 0-1
            self.pipeline.vad.sensitivity = sensitivity
            app_logger.info(f"Updated VAD sensitivity to {sensitivity}")

        # Update wake word sensitivity
        if "wakeWordSensitivity" in settings:
            sensitivity = float(settings["wakeWordSensitivity"]) / 100.0
            self.pipeline.wake_word.sensitivity = sensitivity
            app_logger.info(f"Updated wake word sensitivity to {sensitivity}")

    def _handle_wake_word(self):
        """Handle wake word detection."""
        if not self.current_conversation_id:
            return

        # Send voice feedback
        asyncio.create_task(self._speak_feedback("Yes?"))

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
                # Send as user message to cognitive runtime
                if message_router:
                    await message_router.handle_message(None, {
                        "type": "user_message",
                        "conversation_id": self.current_conversation_id,
                        "content": transcript,
                        "source": "voice",
                    })
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
            asyncio.create_task(self._speak_feedback(
                "You can ask me to create tasks, search files, check system status, or just chat."
            ))
            return "help"

        # Stop/cancel command
        if any(word in text for word in ["stop", "cancel", "nevermind", "forget it"]):
            asyncio.create_task(self._speak_feedback("Okay, cancelled."))
            return "cancel"

        # Default: treat as regular query
        return "query"


# Global voice service instance
voice_service = VoiceService()
