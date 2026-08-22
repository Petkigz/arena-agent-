"""Voice Activity Detection using Silero VAD."""

import asyncio
import numpy as np
from typing import Optional, Callable
from app.utils.logger import app_logger

try:
    import torch
    import torchaudio
except ImportError:
    torch = None
    torchaudio = None
    app_logger.warning("PyTorch not installed. VAD unavailable.")


class VoiceActivityDetector:
    """
    Voice Activity Detector using Silero VAD.
    
    Detects speech start and end in audio stream.
    Triggers callbacks when speech starts or ends.
    """
    
    def __init__(
        self,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        speech_pad_ms: int = 30,  # Padding around speech
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100,
    ):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.speech_pad_ms = speech_pad_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        
        self.model = None
        self.is_running = False
        
        # State tracking
        self.is_speaking = False
        self.speech_start_time: Optional[float] = None
        self.silence_duration = 0.0
        
        # Audio buffer for speech segment
        self.speech_buffer: list = []
        
        # Callbacks
        self.on_speech_start: Optional[Callable[[], None]] = None
        self.on_speech_end: Optional[Callable[[np.ndarray], None]] = None
        
        self._load_model()
        
    def _load_model(self):
        """Load Silero VAD model (gracefully skipped if torch is unavailable or offline).

        V1 fix: previously raised on failure, causing VoicePipeline.start() to fail.
        Now degrades to model=None so pipeline can run without VAD (remote audio path).
        """
        if torch is None:
            app_logger.warning("Cannot load Silero VAD model: PyTorch not installed — VAD degraded to no-op")
            self.model = None
            return
        try:
            # Load Silero VAD model
            self.model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            
            # Get utility functions
            (self.get_speech_timestamps,
             self.save_audio,
             self.read_audio,
             self.VADIterator,
             self.collect_chunks) = utils
            
            app_logger.info("Silero VAD model loaded")
            
        except Exception as e:
            app_logger.warning(f"Failed to load Silero VAD model (degrading to no-op): {e}")
            self.model = None
    
    def start(self):
        """Start voice activity detection."""
        if self.is_running:
            return
            
        self.is_running = True
        self.is_speaking = False
        self.speech_buffer = []
        self.silence_duration = 0.0
        
        app_logger.info("Voice activity detector started")
    
    def stop(self):
        """Stop voice activity detection."""
        self.is_running = False
        self.is_speaking = False
        self.speech_buffer = []
        
        app_logger.info("Voice activity detector stopped")
    
    def reset(self):
        """Reset VAD state."""
        self.is_speaking = False
        self.speech_start_time = None
        self.silence_duration = 0.0
        self.speech_buffer = []
        
        app_logger.debug("VAD reset")
    
    def process_audio(self, audio_chunk: np.ndarray, current_time: float) -> bool:
        """
        Process audio chunk and detect voice activity.
        
        Returns True if speech is currently detected.
        """
        if not self.is_running or self.model is None:
            return False
            
        try:
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(audio_chunk).float()
            
            # Get speech probability
            speech_prob = self.model(audio_tensor, self.sample_rate).item()
            
            # Detect speech start
            if not self.is_speaking and speech_prob > self.threshold:
                self.is_speaking = True
                self.speech_start_time = current_time
                self.silence_duration = 0.0
                self.speech_buffer = [audio_chunk]
                
                app_logger.info(f"Speech started at {current_time:.2f}s")
                
                if self.on_speech_start:
                    try:
                        self.on_speech_start()
                    except Exception as e:
                        app_logger.error(f"Speech start callback error: {e}")
                
                return True
            
            # Accumulate audio while speaking
            if self.is_speaking:
                self.speech_buffer.append(audio_chunk)
                
                # Detect speech end (silence)
                if speech_prob < self.threshold:
                    self.silence_duration += len(audio_chunk) / self.sample_rate
                    
                    # Check if silence is long enough to end speech
                    if self.silence_duration >= (self.min_silence_duration_ms / 1000.0):
                        speech_duration = current_time - (self.speech_start_time or 0)
                        
                        # Check if speech was long enough
                        if speech_duration >= (self.min_speech_duration_ms / 1000.0):
                            # Speech ended
                            speech_audio = np.concatenate(self.speech_buffer)
                            
                            app_logger.info(
                                f"Speech ended at {current_time:.2f}s "
                                f"(duration: {speech_duration:.2f}s)"
                            )
                            
                            if self.on_speech_end:
                                try:
                                    self.on_speech_end(speech_audio)
                                except Exception as e:
                                    app_logger.error(f"Speech end callback error: {e}")
                            
                            # Reset state
                            self.is_speaking = False
                            self.speech_start_time = None
                            self.silence_duration = 0.0
                            self.speech_buffer = []
                        else:
                            # Speech too short, ignore
                            self.is_speaking = False
                            self.speech_start_time = None
                            self.silence_duration = 0.0
                            self.speech_buffer = []
                else:
                    # Still speaking, reset silence duration
                    self.silence_duration = 0.0
                
                return True
            
            return False
            
        except Exception as e:
            app_logger.error(f"VAD processing error: {e}")
            return False
    
    def get_speech_audio(self) -> Optional[np.ndarray]:
        """Get accumulated speech audio buffer."""
        if not self.speech_buffer:
            return None
        return np.concatenate(self.speech_buffer)
