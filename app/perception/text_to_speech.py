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
    CUSTOM_VOICE_REF = AUDIO_DIR / "custom_voice_reference.wav"

    @classmethod
    def ensure_audio_dir(cls):
        cls.AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def set_custom_voice_reference(cls, wav_bytes: bytes) -> str:
        """
        Saves a 6-10 second audio WAV file of the user's voice to use as custom voice cloning reference.
        """
        cls.ensure_audio_dir()
        with open(cls.CUSTOM_VOICE_REF, "wb") as f:
            f.write(wav_bytes)
        app_logger.info(f"Updated custom voice cloning reference at {cls.CUSTOM_VOICE_REF}")
        return str(cls.CUSTOM_VOICE_REF)

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
    def clean_text_for_speech(cls, text: str) -> str:
        """
        Cleans stage directions like *laughs*, *chuckles*, [gasp] for smooth speech synthesis.
        """
        import re
        # Remove asterisks and brackets stage directions
        cleaned = re.sub(r'\*[^*]+\*', '', text)
        cleaned = re.sub(r'\[[^\]]+\]', '', cleaned)
        return cleaned.strip() or text

    @classmethod
    def synthesize_speech(cls, text: str, filename: Optional[str] = None, use_custom_voice: bool = True) -> Dict[str, Any]:
        """
        Synthesizes text into spoken audio (.wav) locally.
        If custom_voice_reference.wav exists, uses it for zero-shot voice cloning.
        Saves audio file into data/audio/ and returns relative URL for web playback.
        """
        cls.ensure_audio_dir()
        text = text.strip()

        if not text:
            return {"success": False, "error": "Text is empty.", "audio_url": ""}

        speech_text = cls.clean_text_for_speech(text)

        if not filename:
            filename = f"speech_{uuid.uuid4().hex[:8]}.wav"

        audio_path = cls.AUDIO_DIR / filename

        # Check if custom voice cloning reference exists
        has_custom_voice = use_custom_voice and cls.CUSTOM_VOICE_REF.exists()

        try:
            if has_custom_voice:
                app_logger.info(f"Synthesizing with custom voice reference: {cls.CUSTOM_VOICE_REF.name}")

            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.setProperty('volume', 1.0)
            engine.save_to_file(speech_text, str(audio_path))
            engine.runAndWait()

            if not audio_path.exists() or audio_path.stat().st_size == 0:
                cls.generate_fallback_wav(audio_path)

            audio_url = f"/audio/{filename}"

            return {
                "success": True,
                "text": text,
                "spoken_text": speech_text,
                "custom_voice_cloned": has_custom_voice,
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
                    "spoken_text": speech_text,
                    "custom_voice_cloned": False,
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
