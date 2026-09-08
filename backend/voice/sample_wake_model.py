"""Custom wake-word model that ACTUALLY trains from the owner's samples.

The previous trainer honestly refused ("no verified trainer configured"),
which the owner experienced as a broken promise. This module is a real,
local, dependency-light trainer: it builds a log-mel template from the
owner's recordings and detects the phrase by normalized cross-correlation of
mel spectrograms. It is not a neural model — and it says so — but it is a
genuine detector trained on the owner's voice, persisted to disk, and used
by the live wake-word loop.

Design notes:
- numpy-only (numpy + stdlib `wave`); no torch required to train.
- Positive-only calibration: threshold = 0.8 × worst self-match of the
  training samples (a conservative floor is applied). Asking twice is
  better than never hearing the owner.
- Refractory period after a detection so one utterance is one event.
"""

from __future__ import annotations

import io
import json
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np


_SAMPLE_RATE = 16000
_N_MELS = 40
_N_FFT = 512
_HOP = 256
_FLOOR = 0.45
_REFRACTORY_S = 2.0


class SampleAudioError(ValueError):
    """A wake-word sample could not be decoded as PCM WAV."""


def pcm16_wav_to_float(data: bytes) -> np.ndarray:
    """Decode WAV bytes (PCM 16/32-bit or float32, any channel count) to
    mono float32 at the file's own rate. Resampling to 16k happens upstream
    (the browser sends 16k mono); here we only normalize format."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            frames = wav.readframes(wav.getnframes())
    except Exception as exc:
        raise SampleAudioError(f"Not a readable WAV file: {exc}") from exc
    if width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        as_int = np.frombuffer(frames, dtype=np.int32).astype(np.float32)
        audio = as_int / 2147483648.0
    else:
        raise SampleAudioError(
            f"Unsupported WAV sample width {width * 8} bits (send 16-bit PCM)"
        )
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if audio.size == 0:
        raise SampleAudioError("WAV file contains no audio frames")
    return audio.astype(np.float32)


def _mel_filters(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    """Triangular mel filterbank (standard HTK-styleslaney-ish, numpy only)."""
    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)

    def mel_to_hz(m):
        return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)

    low = hz_to_mel(0.0)
    high = hz_to_mel(sr / 2.0)
    points = mel_to_hz(np.linspace(low, high, n_mels + 2))
    bins = np.floor((n_fft + 1) * points / sr).astype(int)
    filters = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = bins[i], bins[i + 1], bins[i + 2]
        if center <= left:
            center = left + 1
        if right <= center:
            right = center + 1
        right = min(right, n_fft // 2)
        filters[i, left:center] = np.linspace(0.0, 1.0, center - left, dtype=np.float32)
        filters[i, center:right] = np.linspace(1.0, 0.0, right - center, dtype=np.float32)
    return filters


_FILTERS = _mel_filters(_SAMPLE_RATE, _N_FFT, _N_MELS)


def log_mel(audio: np.ndarray, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """Log-mel spectrogram (n_mels × frames), float32."""
    if audio.ndim != 1 or audio.size < _N_FFT:
        return np.zeros((_N_MELS, 1), dtype=np.float32)
    frames = len(audio) - _N_FFT
    idx = np.arange(_N_FFT)[None, :] + _HOP * np.arange(max(1, frames // _HOP))[:, None]
    idx = np.clip(idx, 0, len(audio) - 1)
    windowed = audio[idx] * np.hanning(_N_FFT).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(windowed, axis=1)) ** 2
    mel = (spectrum @ _FILTERS.T).T  # n_mels × frames
    return np.log10(mel + 1e-6).astype(np.float32)


@dataclass
class SamplePackWakeModel:
    """A trained template-matching wake-word model for one custom phrase."""

    phrase: str
    template: np.ndarray  # mean log-mel across training samples (n_mels × T)
    threshold: float
    sample_rate: int = _SAMPLE_RATE
    sample_count: int = 0
    self_scores: List[float] = field(default_factory=list)
    method: str = "sample_correlation_v1"
    _last_detect_ts: float = 0.0

    # ── training ──
    @classmethod
    def train(cls, phrase: str, samples: List[np.ndarray],
              sample_rate: int = _SAMPLE_RATE) -> "SamplePackWakeModel":
        if len(samples) < 5:
            raise SampleAudioError("At least 5 samples are required to train")
        mels = []
        scores: List[float] = []
        for audio in samples:
            if audio.size >= _N_FFT:
                mels.append(log_mel(audio, sample_rate))
        if len(mels) < 5:
            raise SampleAudioError("Samples too short to train on (need ≥ 32ms each)")
        # Time-normalize each sample's mel to the median length so the
        # template is an average of comparable shapes.
        target = int(np.median([m.shape[1] for m in mels]))
        resized = [_resize(m, target) for m in mels]
        template = np.mean(resized, axis=0)
        model = cls(phrase=phrase, template=template, threshold=_FLOOR,
                    sample_rate=sample_rate, sample_count=len(samples))
        # Calibrate on the training positives: worst self-match defines the
        # ceiling; a margin below it becomes the threshold (floor applied).
        for mel in resized:
            scores.append(model._best_correlation(mel))
        if scores:
            model.self_scores = [round(float(s), 4) for s in scores]
            model.threshold = float(max(_FLOOR, min(scores) * 0.8))
        return model

    # ── detection ──
    def process(self, chunk: np.ndarray, now: Optional[float] = None) -> bool:
        """One live audio chunk -> wake word detected? (with refractory)."""
        import time as _time

        mel = log_mel(chunk, self.sample_rate)
        if mel.shape[1] < 3:
            return False
        score = self._best_correlation(mel)
        ts = now if now is not None else _time.time()
        if score >= self.threshold and ts - self._last_detect_ts > _REFRACTORY_S:
            self._last_detect_ts = ts
            return True
        return False

    def _best_correlation(self, mel: np.ndarray) -> float:
        """Max normalized correlation of the template against any window."""
        template = self.template
        if template.size == 0 or mel.size == 0:
            return 0.0
        t_flat = template.reshape(-1)
        t_norm = np.linalg.norm(t_flat)
        if t_norm == 0:
            return 0.0
        win = template.shape[1]
        if mel.shape[1] < win:
            mel = _resize(mel, win)
        best = 0.0
        n_windows = max(1, mel.shape[1] - win + 1)
        step = max(1, win // 4)
        for start in range(0, n_windows, step):
            window = mel[:, start:start + win]
            if window.shape[1] < win:
                window = _resize(mel, win)
            w_flat = window.reshape(-1)
            w_norm = np.linalg.norm(w_flat)
            if w_norm == 0:
                continue
            cos = float(np.dot(t_flat, w_flat) / (t_norm * w_norm))
            best = max(best, cos)
        return best

    # ── persistence ──
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path.with_suffix(".npz"),
            template=self.template,
            meta=json.dumps({
                "phrase": self.phrase,
                "threshold": self.threshold,
                "sample_rate": self.sample_rate,
                "sample_count": self.sample_count,
                "self_scores": self.self_scores,
                "method": self.method,
            }),
        )

    @classmethod
    def load(cls, path: Path) -> "SamplePackWakeModel":
        path = Path(path)
        packed = np.load(path.with_suffix(".npz"), allow_pickle=False)
        meta = json.loads(str(packed["meta"]))
        model = cls(
            phrase=meta["phrase"],
            template=np.asarray(packed["template"], dtype=np.float32),
            threshold=float(meta["threshold"]),
            sample_rate=int(meta.get("sample_rate", _SAMPLE_RATE)),
            sample_count=int(meta.get("sample_count", 0)),
            self_scores=list(meta.get("self_scores", [])),
            method=str(meta.get("method", cls.method if hasattr(cls, "method") else "sample_correlation_v1")),
        )
        model.method = str(meta.get("method", "sample_correlation_v1"))
        return model


def _resize(mel: np.ndarray, target_frames: int) -> np.ndarray:
    """Linear time-resize of a mel spectrogram (n_mels × target)."""
    if mel.shape[1] == target_frames:
        return mel
    old_idx = np.linspace(0.0, mel.shape[1] - 1, target_frames)
    lo = np.floor(old_idx).astype(int)
    hi = np.clip(lo + 1, 0, mel.shape[1] - 1)
    frac = (old_idx - lo).astype(np.float32)[None, :]
    return (mel[:, lo] * (1.0 - frac) + mel[:, hi] * frac).astype(np.float32)
