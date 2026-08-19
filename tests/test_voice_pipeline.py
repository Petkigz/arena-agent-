"""Tests for voice pipeline components."""

import pytest
import asyncio
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from backend.voice.orchestrator import VoicePipeline, VoiceState
from backend.voice.service import VoiceService
from backend.voice.wake_word import WakeWordDetector
from backend.voice.vad import VoiceActivityDetector


class TestVoiceState:
    """Test VoiceState enum."""

    def test_state_values(self):
        """Verify all voice states are defined."""
        assert VoiceState.IDLE == "idle"
        assert VoiceState.LISTENING == "listening"
        assert VoiceState.RECORDING == "recording"
        assert VoiceState.PROCESSING == "processing"
        assert VoiceState.THINKING == "thinking"
        assert VoiceState.SPEAKING == "speaking"


class TestVoicePipeline:
    """Test VoicePipeline orchestrator."""

    @pytest.fixture
    def pipeline(self):
        """Create a voice pipeline instance."""
        return VoicePipeline(
            wake_word="hey_jarvis",
            wake_word_sensitivity=0.5,
            vad_threshold=0.5,
        )

    def test_initial_state(self, pipeline):
        """Pipeline starts in IDLE state."""
        assert pipeline.state == VoiceState.IDLE
        assert not pipeline.is_running

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, pipeline):
        """Test pipeline start and stop."""
        with patch('backend.voice.audio_capture.AudioCaptureService') as mock_audio, \
             patch('backend.voice.wake_word.WakeWordDetector') as mock_wake, \
             patch('backend.voice.vad.VoiceActivityDetector') as mock_vad, \
             patch('backend.voice.stt.SpeechToTextService') as mock_stt, \
             patch('backend.voice.tts.TextToSpeechService') as mock_tts:

            # Mock all components
            mock_audio.return_value.start = Mock()
            mock_audio.return_value.stop = Mock()
            mock_wake.return_value.start = Mock()
            mock_wake.return_value.stop = Mock()
            mock_vad.return_value.start = Mock()
            mock_vad.return_value.stop = Mock()
            mock_stt.return_value.start = Mock()
            mock_stt.return_value.stop = Mock()
            mock_tts.return_value.start = Mock()
            mock_tts.return_value.stop = Mock()

            await pipeline.start()
            assert pipeline.is_running
            assert pipeline.state == VoiceState.IDLE

            await pipeline.stop()
            assert not pipeline.is_running

    def test_state_transition(self, pipeline):
        """Test state transition callback."""
        callback = Mock()
        pipeline.on_state_change = callback

        pipeline._set_state(VoiceState.LISTENING)

        assert pipeline.state == VoiceState.LISTENING
        callback.assert_called_once_with(VoiceState.IDLE, VoiceState.LISTENING)

    def test_no_duplicate_state_callback(self, pipeline):
        """State callback not triggered if state unchanged."""
        callback = Mock()
        pipeline.on_state_change = callback

        pipeline._set_state(VoiceState.IDLE)
        callback.assert_not_called()


class TestWakeWordDetector:
    """Test WakeWordDetector."""

    def test_initialization(self):
        """Test wake word detector initialization."""
        detector = WakeWordDetector(
            wake_word="hey_jarvis",
            sensitivity=0.5,
            sample_rate=16000,
        )
        assert detector.wake_word == "hey_jarvis"
        assert detector.sensitivity == 0.5
        assert detector.sample_rate == 16000
        assert not detector.is_running

    def test_wake_word_mapping(self):
        """Test wake word name to model mapping."""
        detector = WakeWordDetector(wake_word="hey_arena")
        # Should map to hey_jarvis model since hey_arena doesn't exist
        assert detector.wake_word == "hey_jarvis"


class TestVoiceActivityDetector:
    """Test VoiceActivityDetector."""

    def test_initialization(self):
        """Test VAD initialization."""
        vad = VoiceActivityDetector(threshold=0.5, sample_rate=16000)
        assert vad.threshold == 0.5
        assert vad.sample_rate == 16000
        assert not vad.is_running
        assert vad.speech_buffer == []

    def test_speech_detection(self):
        """Test speech start/end detection."""
        vad = VoiceActivityDetector(threshold=0.5)
        vad.is_running = True

        # Simulate audio chunk with speech
        audio = np.random.randn(1600).astype(np.float32)

        # Mock the VAD model
        vad.model = Mock()
        vad.model.return_value.item.return_value = 0.8  # High probability

        result = vad.process_audio(audio, 0.0)

        assert result is True
        assert vad.is_speaking
        assert len(vad.speech_buffer) > 0


class TestVoiceService:
    """Test VoiceService."""

    @pytest.fixture
    def service(self):
        """Create a voice service instance."""
        return VoiceService()

    def test_initial_state(self, service):
        """Service starts disabled."""
        assert not service._enabled
        assert service.current_conversation_id is None
        assert service.pipeline is None

    @pytest.mark.asyncio
    async def test_start_stop(self, service):
        """Test service start and stop."""
        with patch('backend.voice.service.VoicePipeline') as mock_pipeline:
            mock_instance = AsyncMock()
            mock_pipeline.return_value = mock_instance

            await service.start("conv_123")

            assert service._enabled
            assert service.current_conversation_id == "conv_123"
            assert service.pipeline is not None
            mock_instance.start.assert_called_once()

            await service.stop()

            assert not service._enabled
            assert service.current_conversation_id is None
            mock_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_settings(self, service):
        """Test settings update."""
        with patch('backend.voice.service.VoicePipeline') as mock_pipeline:
            mock_instance = MagicMock()
            mock_pipeline.return_value = mock_instance
            service.pipeline = mock_instance
            service._enabled = True

            settings = {
                "wakeWord": "hey_arena",
                "voiceSpeed": 1.2,
                "vadSensitivity": 70,
            }

            await service.update_settings(settings)

            # Verify wake word update
            mock_instance.update_wake_word.assert_called_once()

    def test_parse_voice_command(self, service):
        """Test voice command parsing."""
        # Help command
        assert service._parse_voice_command("help") == "help"
        assert service._parse_voice_command("what can you do") == "help"

        # Cancel command
        assert service._parse_voice_command("stop") == "cancel"
        assert service._parse_voice_command("nevermind") == "cancel"

        # Regular query
        assert service._parse_voice_command("create a task") == "query"

        # Empty input
        assert service._parse_voice_command("") is None
        assert service._parse_voice_command("   ") is None


class TestBargeIn:
    """Test barge-in functionality."""

    @pytest.mark.asyncio
    async def test_barge_in_during_speaking(self):
        """Test wake word detection during TTS playback."""
        pipeline = VoicePipeline()
        pipeline.is_running = True
        pipeline.state = VoiceState.SPEAKING

        # Mock components
        pipeline.wake_word = Mock()
        pipeline.wake_word.process_audio = Mock(return_value=True)
        pipeline.vad = Mock()
        pipeline.vad.start = Mock()

        # Simulate audio chunk
        audio = np.random.randn(1600).astype(np.float32)

        pipeline._on_audio_chunk(audio)

        # Should detect wake word and transition to LISTENING
        pipeline.wake_word.process_audio.assert_called_once()
        assert pipeline.state == VoiceState.LISTENING
        pipeline.vad.start.assert_called_once()


class TestAudioConversion:
    """Test audio format conversion."""

    def test_float_to_int16_conversion(self):
        """Test float32 to int16 PCM conversion."""
        # Create test audio
        audio_float = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)

        # Convert to int16
        audio_int16 = (audio_float * 32767).astype(np.int16)

        # Verify conversion
        assert audio_int16.dtype == np.int16
        assert audio_int16[0] == 0
        assert audio_int16[1] == 16383  # 0.5 * 32767
        assert audio_int16[2] == -16383
        assert audio_int16[3] == 32767
        assert audio_int16[4] == -32767


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
