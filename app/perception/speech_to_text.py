import os
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger

class LocalSpeechToText:
    _model = None

    @classmethod
    def get_model(cls, model_size: str = "base"):
        """
        Lazy-loads the local faster-whisper model into CPU/GPU RAM.
        """
        if cls._model is None:
            try:
                from faster_whisper import WhisperModel
                app_logger.info(f"Loading local Faster-Whisper model ('{model_size}')...")
                # Use CPU/float32 or CUDA if available
                cls._model = WhisperModel(model_size, device="cpu", compute_type="float32")
            except Exception as e:
                app_logger.warning(f"Failed to load faster-whisper model: {e}")
                cls._model = False
        return cls._model

    @classmethod
    def transcribe_file(cls, audio_path_str: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribes a local audio file (.wav, .mp3, .webm, .m4a, .ogg) into text.
        """
        audio_path = Path(audio_path_str)
        if not audio_path.is_absolute():
            audio_path = settings.BASE_DIR / audio_path

        if not audio_path.exists():
            return {
                "success": False,
                "error": f"Audio file not found: '{audio_path}'",
                "text": "",
                "segments": []
            }

        model = cls.get_model()
        if not model:
            # Simulated fallback if Whisper dependencies or CTranslate2 are unavailable
            return {
                "success": False,
                "error": "Faster-Whisper model is not available in environment.",
                "text": "",
                "segments": []
            }

        try:
            segments_generator, info = model.transcribe(str(audio_path), language=language, beam_size=5)
            segments = []
            text_parts = []

            for seg in segments_generator:
                segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip()
                })
                text_parts.append(seg.text.strip())

            full_text = " ".join(text_parts)

            return {
                "success": True,
                "text": full_text,
                "language": getattr(info, 'language', 'en'),
                "probability": getattr(info, 'language_probability', 1.0),
                "segments": segments,
                "file_path": str(audio_path)
            }
        except Exception as e:
            app_logger.error(f"Error transcribing audio file '{audio_path}': {e}")
            return {
                "success": False,
                "error": f"Transcription error: {str(e)}",
                "text": "",
                "segments": []
            }
