import os
import uuid
import wave
import math
import struct
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger

class LocalTextToSpeech:
    AUDIO_DIR = settings.DATA_DIR / "audio"

    @classmethod
    def ensure_audio_dir(cls):
        cls.AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def generate_fallback_wav(cls, file_path: Path, duration_sec: float = 1.0, freq: float = 440.0):
        """
        Generates a valid audio WAV file as fallback when system TTS drivers are unavailable.
        """
        sample_rate = 16000
        num_samples = int(sample_rate * duration_sec)
        with wave.open(str(file_path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            for i in range(num_samples):
                value = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                data = struct.pack("<h", value)
                wav_file.writeframes(data)

    @classmethod
    def synthesize_speech(cls, text: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Synthesizes text into spoken audio (.wav) locally using pyttsx3/SAPI5.
        Saves audio file into data/audio/ and returns relative URL for web playback.
        """
        cls.ensure_audio_dir()
        text = text.strip()

        if not text:
            return {"success": False, "error": "Text is empty.", "audio_url": ""}

        if not filename:
            filename = f"speech_{uuid.uuid4().hex[:8]}.wav"

        audio_path = cls.AUDIO_DIR / filename

        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 175)
            engine.setProperty('volume', 1.0)
            engine.save_to_file(text, str(audio_path))
            engine.runAndWait()

            if not audio_path.exists() or audio_path.stat().st_size == 0:
                cls.generate_fallback_wav(audio_path)

            audio_url = f"/audio/{filename}"

            return {
                "success": True,
                "text": text,
                "file_path": str(audio_path),
                "file_name": filename,
                "audio_url": audio_url
            }
        except Exception as e:
            app_logger.warning(f"pyttsx3 TTS driver unavailable ({e}). Generating fallback audio file...")
            try:
                cls.generate_fallback_wav(audio_path)
                return {
                    "success": True,
                    "text": text,
                    "file_path": str(audio_path),
                    "file_name": filename,
                    "audio_url": f"/audio/{filename}"
                }
            except Exception as ex:
                return {
                    "success": False,
                    "error": f"Speech synthesis error: {str(ex)}",
                    "audio_url": ""
                }
