"""Speech-to-Text using faster-whisper."""

import asyncio
import numpy as np
from typing import Optional, Callable, List, Dict
from app.utils.logger import app_logger

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None
    app_logger.warning("faster-whisper not installed. STT unavailable.")


class SpeechToTextService:
    """
    Speech-to-Text service using faster-whisper.
    
    Transcribes speech audio to text with streaming support.
    """
    
    def __init__(
        self,
        model_size: str = "base",  # tiny, base, small, medium, large
        device: str = "auto",  # auto, cpu, cuda
        compute_type: str = "int8",  # int8, float16, float32
        language: Optional[str] = None,  # None for auto-detect
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        
        self.model: Optional[WhisperModel] = None
        self.is_running = False
        self.last_error: Optional[str] = None
        
        # Callbacks
        self.on_transcript: Optional[Callable[[str, bool], None]] = None
        
    def start(self):
        """Start STT service and retain a diagnostic when it cannot load."""
        self.last_error = None
        if self.is_running:
            return

        if WhisperModel is None:
            self.last_error = "faster-whisper is not installed"
            app_logger.error(
                "Cannot start STT service: faster-whisper not installed. "
                "Install it and ensure the selected model is available locally."
            )
            return

        try:
            # Load faster-whisper model
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            
            self.is_running = True
            app_logger.info(f"STT service started: model={self.model_size}, device={self.device}")
            
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.model = None
            self.is_running = False
            app_logger.error(f"Failed to start STT service: {self.last_error}")
            raise
    
    def stop(self):
        """Stop STT service."""
        self.is_running = False
        self.model = None
        app_logger.info("STT service stopped")
    
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> Dict:
        """
        Transcribe audio to text.
        
        Returns dict with:
        - text: transcribed text
        - language: detected language
        - segments: list of segments with timestamps
        """
        if not self.is_running or self.model is None:
            reason = self.last_error or "STT is not running with a loaded Whisper model"
            raise RuntimeError(reason)
            
        try:
            # Transcribe audio
            segments, info = self.model.transcribe(
                audio,
                beam_size=5,
                language=language or self.language,
                vad_filter=True,
            )
            
            # Collect all segments
            segment_list = []
            full_text = ""
            
            for segment in segments:
                segment_list.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                })
                full_text += segment.text
            
            result = {
                "text": full_text.strip(),
                "language": info.language,
                "language_probability": info.language_probability,
                "segments": segment_list,
            }
            
            app_logger.info(
                f"Transcription complete: '{result['text'][:50]}...' "
                f"(language: {result['language']}, prob: {result['language_probability']:.2f})"
            )
            
            # Trigger callback
            if self.on_transcript and result["text"]:
                try:
                    self.on_transcript(result["text"], True)
                except Exception as e:
                    app_logger.error(f"Transcript callback error: {e}")
            
            return result
            
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            app_logger.error(f"Transcription error: {self.last_error}")
            raise
    
    async def transcribe_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> Dict:
        """Async wrapper for transcribe."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.transcribe, audio, sample_rate, language
        )
