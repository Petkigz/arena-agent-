import os
import uuid
import wave
import math
import struct
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.utils.logger import app_logger

try:
    import soundfile as _sf
except ImportError:
    _sf = None

from app.perception.piper_voice import (
    PIPER_AVAILABLE,
    DEFAULT_VOICE_ID,
    find_piper_models,
    resolve_voice_id,
    synthesize_piper,
)

class LocalTextToSpeech:
    AUDIO_DIR = settings.DATA_DIR / "audio"
    VOICES_DIR = AUDIO_DIR / "voices"
    CUSTOM_VOICE_REF = AUDIO_DIR / "custom_voice_reference.wav"
    ACTIVE_VOICE_CONFIG = AUDIO_DIR / "active_voice.txt"
    ACTIVE_PIPER_VOICE_CONFIG = AUDIO_DIR / "active_piper_voice.txt"

    @classmethod
    def get_active_piper_voice(cls) -> str:
        """Return the active Piper voice id (env override > saved > first available > default)."""
        env = os.environ.get("ARENA_PIPER_VOICE")
        if env:
            return env.strip()

        cls.ensure_audio_dir()
        if cls.ACTIVE_PIPER_VOICE_CONFIG.exists():
            try:
                saved = cls.ACTIVE_PIPER_VOICE_CONFIG.read_text(encoding="utf-8").strip()
                if saved:
                    return saved
            except Exception:
                pass
        return resolve_voice_id(DEFAULT_VOICE_ID)

    @classmethod
    def set_active_piper_voice(cls, voice_id: str) -> bool:
        """Persist the active Piper voice id."""
        cls.ensure_audio_dir()
        resolved = resolve_voice_id(voice_id.strip())
        if resolved != voice_id.strip():
            app_logger.warning(f"Piper voice '{voice_id}' not found; using '{resolved}'")
        try:
            cls.ACTIVE_PIPER_VOICE_CONFIG.write_text(resolved, encoding="utf-8")
        except Exception as e:
            app_logger.error(f"Could not persist active Piper voice: {e}")
            return False
        app_logger.info(f"Set active Piper voice to '{resolved}'")
        return True

    @classmethod
    def list_piper_voices(cls) -> List[Dict[str, Any]]:
        """Return discovered Piper voices with an 'active' flag."""
        voices = find_piper_models()
        active = cls.get_active_piper_voice()
        for v in voices:
            v["active"] = v["id"] == active
        return voices

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
    def _write_pcm16_wav(cls, file_path: Path, audio: Any, sample_rate: int) -> None:
        """Write float32 mono audio as a 16-bit PCM WAV (no soundfile dependency)."""
        samples = audio.astype("float32")
        pcm = (samples.clip(-1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(file_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate))
            wav_file.writeframes(pcm.tobytes())

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
    def synthesize_speech(cls, text: str, filename: Optional[str] = None, use_custom_voice: bool = True, voice: Optional[str] = None) -> Dict[str, Any]:
        """
        Synthesizes text into spoken audio (.wav) locally.

        Prefers Piper (offline, deterministic, real voices) when the model is
        available and otherwise tries the OS TTS driver (pyttsx3). If neither
        produces speech, returns unavailable rather than labeling a tone as voice.
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

        # 1) Piper (offline, real voice). Write a 16-bit PCM WAV for browser playback.
        piper_voice_id = voice or cls.get_active_piper_voice()
        if PIPER_AVAILABLE:
            try:
                result = synthesize_piper(speech_text, voice_id=piper_voice_id, speed=1.0)
                if result is not None:
                    audio, sr = result
                    if _sf is not None:
                        _sf.write(str(audio_path), audio, sr, subtype="PCM_16")
                    else:  # fallback: write via wave module
                        cls._write_pcm16_wav(audio_path, audio, sr)
                    if audio_path.exists() and audio_path.stat().st_size > 0:
                        return {
                            "success": True,
                            "text": text,
                            "spoken_text": speech_text,
                            "engine": "piper",
                            "voice": piper_voice_id,
                            "active_voice_profile": active_profile,
                            "custom_voice_cloned": False,
                            "file_path": str(audio_path),
                            "file_name": filename,
                            "audio_url": f"/audio/{filename}",
                        }
            except Exception as e:
                app_logger.warning(f"Piper synthesis failed, falling back to pyttsx3: {e}")

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
                raise RuntimeError("TTS engine produced no audio artifact")

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
            app_logger.warning(f"pyttsx3 TTS unavailable: {e}")
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass
            return {
                "success": False,
                "available": False,
                "error": f"Speech synthesis unavailable: {e}",
                "text": text,
                "audio_url": "",
                "file_path": "",
            }
