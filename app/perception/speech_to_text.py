import os
import wave
import math
import numpy as np
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
                cls._model = WhisperModel(model_size, device="cpu", compute_type="float32")
            except Exception as e:
                app_logger.warning(f"Failed to load faster-whisper model: {e}")
                cls._model = False
        return cls._model

    @classmethod
    def verify_speaker_voice(cls, audio_path_str: str, noise_gate_threshold: float = 0.05) -> Dict[str, Any]:
        """
        Refined noise-resilient speaker verification.
        Applies RMS energy noise-gating and Fast Fourier Transform (FFT) spectral distance matching
        against the user's reference voice profile to filter out background chatter in crowded places.
        """
        ref_path = settings.DATA_DIR / "audio" / "custom_voice_reference.wav"
        if not ref_path.exists():
            return {
                "verified": False,
                "available": False,
                "confidence": 0.0,
                "note": "No voice reference profile is configured; speaker identity is unknown.",
            }

        try:
            with wave.open(str(ref_path), 'rb') as ref_wav, wave.open(audio_path_str, 'rb') as input_wav:
                ref_frames = ref_wav.readframes(20000)
                input_frames = input_wav.readframes(20000)

                if ref_frames and input_frames:
                    ref_data = np.frombuffer(ref_frames, dtype=np.int16).astype(np.float32)
                    input_data = np.frombuffer(input_frames, dtype=np.int16).astype(np.float32)

                    # 1. RMS Energy Noise Gate Check
                    rms_input = np.sqrt(np.mean(input_data ** 2)) / 32768.0
                    if rms_input < noise_gate_threshold:
                        return {
                            "verified": False,
                            "confidence": 0.20,
                            "note": f"Audio below noise-gate threshold ({rms_input:.3f} < {noise_gate_threshold}). Ambient noise detected."
                        }

                    # 2. Spectral Centroid / Pitch Alignment
                    ref_fft = np.abs(np.fft.rfft(ref_data[:16000]))
                    input_fft = np.abs(np.fft.rfft(input_data[:16000])) if len(input_data) >= 16000 else np.abs(np.fft.rfft(input_data))

                    ref_centroid = np.sum(ref_fft * np.arange(len(ref_fft))) / (np.sum(ref_fft) + 1e-6)
                    input_centroid = np.sum(input_fft * np.arange(len(input_fft))) / (np.sum(input_fft) + 1e-6)

                    centroid_diff = abs(ref_centroid - input_centroid)
                    is_verified_speaker = centroid_diff < 1500.0
                    # This is a deterministic spectral similarity, not a
                    # statistically calibrated speaker-identification confidence.
                    spectral_similarity = max(0.0, min(1.0, 1.0 - centroid_diff / 3000.0))

                    return {
                        "verified": is_verified_speaker,
                        "available": True,
                        "confidence": round(float(spectral_similarity), 3),
                        "engine": "spectral_centroid_v1",
                        "centroid_distance": round(float(centroid_diff), 2),
                        "input_rms_energy": round(float(rms_input), 3),
                        "note": "Spectral signature matched the primary reference" if is_verified_speaker else "Spectral signature did not match the primary reference."
                    }
        except Exception as e:
            app_logger.warning(f"Speaker voice verification notice: {e}")

        return {
            "verified": False,
            "available": False,
            "confidence": 0.0,
            "note": "Speaker verification could not be performed; identity remains unknown.",
        }

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
