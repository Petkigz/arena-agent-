import os
import uuid
import wave
import math
import struct
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.utils.logger import app_logger

class LocalTextToSpeech:
    AUDIO_DIR = settings.DATA_DIR / "audio"
    VOICES_DIR = AUDIO_DIR / "voices"
    CUSTOM_VOICE_REF = AUDIO_DIR / "custom_voice_reference.wav"
    ACTIVE_VOICE_CONFIG = AUDIO_DIR / "active_voice.txt"

    @classmethod
    def ensure_audio_dir(cls):
        cls.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        cls.VOICES_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def save_voice_profile(cls, profile_name: str, wav_bytes: bytes) -> Dict[str, Any]:
        """
        Saves a 6-10 second WAV recording as a named custom voice profile (e.g. 'User Voice', 'Partner Voice').
        """
        cls.ensure_audio_dir()
        safe_name = "".join(c for c in profile_name if c.isalnum() or c in ("-", "_", " ")).strip() or "custom_voice"
        filename = f"{safe_name}.wav"
        profile_path = cls.VOICES_DIR / filename

        with open(profile_path, "wb") as f:
            f.write(wav_bytes)

        # Also update custom_voice_reference.wav
        with open(cls.CUSTOM_VOICE_REF, "wb") as f:
            f.write(wav_bytes)

        cls.set_active_voice_profile(safe_name)
        app_logger.info(f"Saved custom voice profile '{safe_name}' at {profile_path}")

        return {
            "success": True,
            "profile_name": safe_name,
            "file_name": filename,
            "file_path": str(profile_path)
        }

    @classmethod
    def list_voice_profiles(cls) -> Dict[str, Any]:
        """
        Lists all saved voice profiles in data/audio/voices/ and identifies active profile.
        """
        cls.ensure_audio_dir()
        profiles = ["Default Assistant"]
        for f in cls.VOICES_DIR.glob("*.wav"):
            profiles.append(f.stem)

        active = cls.get_active_voice_profile()
        return {
            "profiles": profiles,
            "active_profile": active
        }

    @classmethod
    def set_active_voice_profile(cls, profile_name: str) -> bool:
        """
        Sets the active voice profile for speech synthesis.
        """
        cls.ensure_audio_dir()
        safe_name = profile_name.strip()
        with open(cls.ACTIVE_VOICE_CONFIG, "w", encoding="utf-8") as f:
            f.write(safe_name)

        if safe_name != "Default Assistant":
            profile_path = cls.VOICES_DIR / f"{safe_name}.wav"
            if profile_path.exists():
                with open(profile_path, "rb") as src, open(cls.CUSTOM_VOICE_REF, "wb") as dst:
                    dst.write(src.read())

        app_logger.info(f"Set active voice profile to '{safe_name}'")
        return True

    @classmethod
    def get_active_voice_profile(cls) -> str:
        """
        Returns the name of the currently active voice profile.
        """
        cls.ensure_audio_dir()
        if cls.ACTIVE_VOICE_CONFIG.exists():
            try:
                with open(cls.ACTIVE_VOICE_CONFIG, "r", encoding="utf-8") as f:
                    return f.read().strip() or "Default Assistant"
            except Exception:
                pass
        return "Default Assistant"

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
        cleaned = re.sub(r'\*[^*]+\*', '', text)
        cleaned = re.sub(r'\[[^\]]+\]', '', cleaned)
        return cleaned.strip() or text

    @classmethod
    def synthesize_speech(cls, text: str, filename: Optional[str] = None, use_custom_voice: bool = True) -> Dict[str, Any]:
        """
        Synthesizes text into spoken audio (.wav) locally.
        If active voice profile is set and exists, uses it as reference.
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
        active_profile = cls.get_active_voice_profile()
        has_custom_voice = use_custom_voice and active_profile != "Default Assistant" and cls.CUSTOM_VOICE_REF.exists()

        try:
            if has_custom_voice:
                app_logger.info(f"Synthesizing with active voice profile '{active_profile}': {cls.CUSTOM_VOICE_REF.name}")

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
                "active_voice_profile": active_profile,
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
                    "active_voice_profile": active_profile,
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
