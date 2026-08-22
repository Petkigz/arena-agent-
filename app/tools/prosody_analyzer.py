"""Voice prosody analyzer — deterministic, local, degradable.

P2 AGI: Social cognition from real signals (not rule-based).
Human intelligence infers emotion from voice prosody (pitch, energy, rate).
Previously social_cognition recognized emotion only when explicitly told.
Now it analyzes real audio to infer emotion intensity and triggers.

Uses only numpy (no heavy deps), so it runs on i9 CPU.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from app.utils.logger import app_logger


class ProsodyAnalyzerTool:
    """Analyze voice prosody from PCM audio to infer emotion cues."""

    @staticmethod
    def _rms(samples: np.ndarray) -> float:
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples.astype(float) ** 2)))

    @staticmethod
    def _zero_crossing_rate(samples: np.ndarray) -> float:
        if samples.size < 2:
            return 0.0
        # Count sign changes
        signs = np.sign(samples)
        # Zero is considered positive for ZCR
        signs[signs == 0] = 1
        return float(np.mean(np.abs(np.diff(signs)) / 2))

    @staticmethod
    def _pitch_estimate(samples: np.ndarray, sample_rate: int = 16000) -> float:
        """Very simple pitch estimate via autocorrelation peak (0 if unvoiced)."""
        if samples.size < sample_rate // 10:  # need at least 100ms
            return 0.0
        try:
            # Normalize
            x = samples.astype(float)
            x = x - np.mean(x)
            # Autocorrelation
            corr = np.correlate(x, x, mode='full')
            corr = corr[len(corr)//2:]
            # Find peak in plausible pitch range (50-400 Hz)
            min_period = int(sample_rate / 400)
            max_period = int(sample_rate / 50)
            if max_period >= len(corr):
                max_period = len(corr) - 1
            if min_period >= max_period:
                return 0.0
            # Ignore zero lag
            search = corr[min_period:max_period]
            if search.size == 0:
                return 0.0
            peak = np.argmax(search) + min_period
            if corr[peak] < 0.3 * corr[0]:  # unvoiced if peak weak
                return 0.0
            return float(sample_rate / peak)
        except Exception:
            return 0.0

    @classmethod
    def analyze_prosody(cls, audio: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """Analyze prosody from numpy PCM audio (float -1..1 or int16).

        Returns typed dict with success, features, inferred emotion.
        """
        try:
            if audio is None or audio.size == 0:
                return {"success": False, "error": "Empty audio", "features": {}, "emotion": "neutral"}

            # Normalize to float -1..1 if int16
            if audio.dtype == np.int16:
                samples = audio.astype(float) / 32768.0
            elif np.issubdtype(audio.dtype, np.integer):
                # Assume int16 range
                samples = audio.astype(float) / 32768.0
            else:
                samples = audio.astype(float)
                # Clip
                samples = np.clip(samples, -1.0, 1.0)

            rms = cls._rms(samples)
            zcr = cls._zero_crossing_rate(samples)
            pitch = cls._pitch_estimate(samples, sample_rate)
            duration = len(samples) / sample_rate

            # Speaking rate proxy: energy bursts per second (very rough)
            # Count RMS peaks above threshold
            # Use simple energy-based segmentation
            energy = np.abs(samples)
            # Moving average
            window = int(sample_rate * 0.02)  # 20ms
            if window > 0 and len(energy) > window:
                # Simple: count times energy crosses mean
                mean_energy = np.mean(energy)
                crossings = np.sum(np.diff((energy > mean_energy).astype(int)) != 0)
                speaking_rate = crossings / duration if duration > 0 else 0
            else:
                speaking_rate = 0.0

            features = {
                "rms": rms,
                "rms_db": 20 * math.log10(rms + 1e-10),
                "zero_crossing_rate": zcr,
                "pitch_hz": pitch,
                "duration_s": duration,
                "speaking_rate_proxy": speaking_rate,
            }

            # Infer emotion from prosody (heuristic, not ML — but from real signals)
            # High RMS + high pitch + fast rate → joy/excitement or anger
            # Low RMS + low pitch + slow rate → sadness
            # High ZCR + variable pitch → fear/surprise
            # Moderate → neutral
            emotion = "neutral"
            intensity = 0.3
            triggers: List[str] = []

            if rms > 0.15 and pitch > 180 and speaking_rate > 5:
                # High energy, high pitch, fast → could be joy or anger
                # Use ZCR to disambiguate: high ZCR → anger/frustration, lower → joy
                if zcr > 0.15:
                    emotion = "anger"
                    intensity = min(1.0, rms * 3)
                    triggers.append(f"high energy (rms={rms:.2f}) + high pitch ({pitch:.0f}Hz) + high ZCR ({zcr:.2f}) → frustration")
                else:
                    emotion = "joy"
                    intensity = min(1.0, rms * 2.5)
                    triggers.append(f"high energy (rms={rms:.2f}) + high pitch ({pitch:.0f}Hz) → excitement")
            elif rms < 0.05 and pitch > 0 and pitch < 120 and duration > 1.0:
                emotion = "sadness"
                intensity = 0.5 + (0.1 - rms) * 2
                triggers.append(f"low energy (rms={rms:.2f}) + low pitch ({pitch:.0f}Hz) + slow → sadness")
            elif zcr > 0.2 and pitch > 200:
                emotion = "fear"
                intensity = min(1.0, zcr * 2)
                triggers.append(f"high ZCR ({zcr:.2f}) + high pitch ({pitch:.0f}Hz) → fear/surprise")
            elif pitch > 250 and speaking_rate > 6:
                emotion = "surprise"
                intensity = 0.6
                triggers.append(f"very high pitch ({pitch:.0f}Hz) + fast rate → surprise")
            elif rms > 0.1 and duration < 0.8:
                emotion = "anger"
                intensity = 0.5
                triggers.append(f"short burst high energy → anger/frustration")

            return {
                "success": True,
                "features": features,
                "emotion": emotion,
                "intensity": float(max(0.0, min(1.0, intensity))),
                "triggers": triggers,
            }
        except Exception as e:
            app_logger.warning(f"Prosody analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "features": {},
                "emotion": "neutral",
                "intensity": 0.3,
                "triggers": [],
            }

    @classmethod
    def analyze_file(cls, file_path: str, sample_rate: int = 16000) -> Dict[str, Any]:
        """Analyze prosody from an audio file (wav/mp3 via soundfile/torchaudio fallback)."""
        try:
            from pathlib import Path
            p = Path(file_path)
            if not p.exists():
                return {"success": False, "error": f"File not found: {file_path}", "features": {}}

            # Try soundfile
            try:
                import soundfile as sf
                data, sr = sf.read(str(p))
                if data.ndim > 1:
                    data = data.mean(axis=1)  # mono
                return cls.analyze_prosody(data, sample_rate=sr)
            except ImportError:
                pass

            # Try torchaudio
            try:
                import torch
                import torchaudio
                waveform, sr = torchaudio.load(str(p))
                data = waveform.mean(dim=0).numpy() if waveform.ndim > 1 else waveform.numpy()
                return cls.analyze_prosody(data, sample_rate=sr)
            except ImportError:
                pass

            # Fallback: try to read as raw PCM? Not reliable
            return {"success": False, "error": "No audio backend (install soundfile)", "features": {}}

        except Exception as e:
            return {"success": False, "error": str(e), "features": {}}
