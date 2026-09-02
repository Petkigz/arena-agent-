"""Shared Piper text-to-speech integration.

Piper is invoked **in-process** via the ``piper-tts`` Python package, not via the
``piper`` CLI binary.  This removes the requirement for ``piper.exe`` to be on
``PATH`` (the old code shelled out to ``subprocess.run(["piper", ...])``).

Voice models are discovered by scanning well-known locations for ``*.onnx``
files (each with an optional sibling ``*.onnx.json`` config):

1. ``ARENA_PIPER_MODEL_DIR`` (highest priority; may be an ``os.pathsep`` list)
2. ``~/piper_models``
3. ``~/.local/share/piper``
4. The ``piper-tts`` package directory itself (covers a model dropped inside
   ``site-packages/piper``)
5. ``<repo>/piper_models``

The scan is recursive, so a model nested in its own subfolder (e.g.
``piper_models/en_US-lessac-medium/en_US-lessac-medium.onnx``) is still found.

This module is deliberately dependency-defensive: it degrades to ``None`` with a
log line (never raises) if ``piper-tts`` or ``soundfile`` are missing, so
callers can fall back to ``pyttsx3`` / a beep.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.utils.logger import app_logger

try:  # piper-tts Python package (in-process, no CLI needed)
    from piper import PiperVoice  # type: ignore
    PIPER_AVAILABLE = True
except Exception:  # pragma: no cover - exercised on machines without piper-tts
    PiperVoice = None  # type: ignore
    PIPER_AVAILABLE = False

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except Exception:  # pragma: no cover
    sf = None  # type: ignore
    SOUNDFILE_AVAILABLE = False


DEFAULT_VOICE_ID = "en_US-lessac-medium"

# Voice filenames look like: <lang>_<region>-<name>-<quality>.onnx
# e.g. en_US-lessac-medium.onnx, sw_KE-lanfrica-medium.onnx
_VOICE_RE = re.compile(
    r"^(?P<lang>[a-z]{2,3})(?:_(?P<region>[A-Z]{2}))?-(?P<name>[A-Za-z0-9]+)-(?P<quality>low|medium|high|x_low)$"
)

# Loaded PiperVoice instances, keyed by resolved model path (loading is expensive).
_voice_cache: Dict[str, object] = {}
_models_cache: Optional[List[Dict]] = None


def _candidate_dirs() -> List[Path]:
    """Return the directories to scan for ``*.onnx`` models, in priority order."""
    dirs: List[Path] = []

    override = os.environ.get("ARENA_PIPER_MODEL_DIR")
    if override:
        for part in override.split(os.pathsep):
            part = part.strip()
            if part:
                dirs.append(Path(part).expanduser())

    home = Path.home()
    dirs.append(home / "piper_models")
    dirs.append(home / ".local" / "share" / "piper")

    # The piper-tts package directory (where the user may have placed models).
    try:
        import piper as _piper_mod  # type: ignore
        pkg_file = getattr(_piper_mod, "__file__", None)
        if pkg_file:
            dirs.append(Path(pkg_file).resolve().parent)
    except Exception:
        pass

    # Repo-local convenience dir.
    dirs.append(Path(__file__).resolve().parent.parent.parent / "piper_models")

    return dirs


def _describe_model(onnx_path: Path) -> Optional[Dict]:
    """Turn an ``*.onnx`` path into a structured voice descriptor, or None."""
    try:
        if onnx_path.suffix.lower() != ".onnx":
            return None

        voice_id = onnx_path.stem
        config_path = Path(str(onnx_path) + ".json")  # <voice>.onnx.json

        m = _VOICE_RE.match(voice_id)
        if m:
            lang = m.group("lang")
            region = m.group("region")
            name = m.group("name")
            quality = m.group("quality")
        else:
            lang, region, name, quality = "en", None, voice_id, "medium"

        region_suffix = f"_{region}" if region else ""
        display = f"{name.capitalize()} ({lang}{region_suffix}, {quality})"

        return {
            "id": voice_id,
            "name": display,
            "language": lang,
            "region": region,
            "quality": quality,
            "path": str(onnx_path),
            "has_config": config_path.is_file(),
        }
    except Exception as e:  # pragma: no cover - defensive
        app_logger.debug(f"Could not describe Piper model {onnx_path}: {e}")
        return None


def find_piper_models(force_refresh: bool = False) -> List[Dict]:
    """Return a sorted list of discovered Piper voice descriptors."""
    global _models_cache
    if _models_cache is not None and not force_refresh:
        return list(_models_cache)

    found: Dict[str, Dict] = {}
    seen_dirs = set()

    for base in _candidate_dirs():
        if not base.is_dir():
            continue
        try:
            base_res = base.resolve()
        except Exception:
            base_res = base
        if base_res in seen_dirs:
            continue
        seen_dirs.add(base_res)

        try:
            for onnx_path in base.rglob("*.onnx"):
                info = _describe_model(onnx_path)
                if info:
                    # First directory wins (priority order); keep the first hit.
                    found.setdefault(info["id"], info)
        except Exception as e:  # pragma: no cover - defensive
            app_logger.debug(f"Error scanning {base} for Piper models: {e}")

    _models_cache = sorted(found.values(), key=lambda m: (m["language"], m["id"]))
    return list(_models_cache)


def find_model_for_voice(voice_id: Optional[str]) -> Optional[Dict]:
    """Resolve a voice id (or a direct .onnx path) to a model descriptor."""
    if not voice_id:
        return None

    # A direct path is accepted for convenience.
    p = Path(voice_id).expanduser()
    if p.is_file() and p.suffix.lower() == ".onnx":
        return _describe_model(p)

    for info in find_piper_models():
        if info["id"] == voice_id:
            return info
    return None


def resolve_voice_id(voice_id: Optional[str]) -> str:
    """Return a usable voice id, falling back to the default when unknown."""
    if voice_id and find_model_for_voice(voice_id):
        return voice_id
    if find_model_for_voice(DEFAULT_VOICE_ID):
        return DEFAULT_VOICE_ID
    models = find_piper_models()
    if models:
        return models[0]["id"]
    return voice_id or DEFAULT_VOICE_ID


def _get_voice(model_path: Path) -> Optional[object]:
    """Load (and cache) a PiperVoice for a given .onnx path."""
    if not PIPER_AVAILABLE:
        app_logger.warning("piper-tts Python package is not importable; TTS unavailable")
        return None

    key = str(model_path)
    if key in _voice_cache:
        return _voice_cache[key]

    try:
        voice = PiperVoice.load(str(model_path))
        _voice_cache[key] = voice
        app_logger.info(f"Loaded Piper voice: {model_path}")
        return voice
    except Exception as e:
        app_logger.error(f"Failed to load Piper voice {model_path}: {e}")
        return None


def _decode_wav(buf: object, source: str) -> Optional[Tuple[np.ndarray, int]]:
    """Decode WAV bytes via soundfile -> (float32 mono, sample_rate)."""
    if not SOUNDFILE_AVAILABLE:
        app_logger.warning("soundfile not importable; cannot decode Piper output")
        return None
    try:
        data = buf if isinstance(buf, (bytes, bytearray)) else getattr(buf, "read", None)
        if callable(data):
            audio, sr = sf.read(data, dtype="float32")
        else:
            audio, sr = sf.read(bytes(data), dtype="float32")
        if audio.ndim > 1:
            audio = audio[:, 0]
        return np.asarray(audio, dtype=np.float32), int(sr)
    except Exception as e:
        app_logger.debug(f"Piper WAV decode failed ({source}): {e}")
        return None


def _synthesize_raw(voice: object, text: str, length_scale: float) -> Optional[Tuple[np.ndarray, int]]:
    """Synthesize, tolerating both the legacy rhasspy/piper and piper1-gpl APIs."""
    import io

    # 1) Legacy: synthesize_wav(text) -> WAV bytes.
    try:
        result = voice.synthesize_wav(text)  # type: ignore[attr-defined]
        if isinstance(result, (bytes, bytearray)) and result:
            decoded = _decode_wav(result, "legacy bytes")
            if decoded:
                return decoded
    except TypeError:
        pass
    except Exception as e:  # pragma: no cover - defensive
        app_logger.debug(f"Piper synthesize_wav(bytes) failed: {e}")

    # 2) piper1-gpl: synthesize_wav(text, file_obj) writes WAV into the object.
    try:
        buf = io.BytesIO()
        voice.synthesize_wav(text, buf)  # type: ignore[attr-defined]
        buf.seek(0)
        if buf.getbuffer().nbytes > 0:
            decoded = _decode_wav(buf, "file obj")
            if decoded:
                return decoded
    except Exception as e:  # pragma: no cover - defensive
        app_logger.debug(f"Piper synthesize_wav(file) failed: {e}")

    # 3) Raw fallback: synthesize(text) -> int16 samples (list) or AudioChunk iterator.
    try:
        try:
            result = voice.synthesize(text, length_scale=length_scale)  # type: ignore[attr-defined]
        except TypeError:
            # Compat (owner run 2026-09-02): some piper builds accept no
            # length_scale kwarg ('PiperVoice.synthesize() got an
            # unexpected keyword argument'). Synthesize at the voice's
            # default rate instead of failing into the pyttsx3 fallback —
            # the owner heard the wrong voice for exactly this reason.
            app_logger.debug(
                "Piper synthesize() rejects length_scale; synthesizing at "
                "the voice default rate")
            result = voice.synthesize(text)  # type: ignore[attr-defined]
        sr = 22050
        if isinstance(result, (list, tuple, np.ndarray)):
            samples = np.asarray(result, dtype=np.int16)
            cfg = getattr(voice, "config", None)
            sr = int(getattr(cfg, "sample_rate", 22050) or 22050)
        else:
            chunks: List[bytes] = []
            for chunk in result:
                data = getattr(chunk, "audio_int16_bytes", None)
                if data is None:
                    data = getattr(chunk, "audio", None)
                if data is None:
                    continue
                if isinstance(data, (bytes, bytearray)):
                    chunks.append(bytes(data))
                else:
                    chunks.append(np.asarray(data, dtype=np.int16).tobytes())
                sr = int(getattr(chunk, "sample_rate", sr) or sr)
            samples = np.frombuffer(b"".join(chunks), dtype=np.int16)

        if samples.size == 0:
            return None
        return samples.astype(np.float32) / 32768.0, sr
    except Exception as e:
        app_logger.error(f"Piper synthesize() failed: {e}")
        return None


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample a 1-D float signal with a scipy polyphase (if present) or linear interp."""
    if audio is None or audio.size == 0 or src_rate <= 0 or dst_rate <= 0 or src_rate == dst_rate:
        return audio
    try:
        from math import gcd

        from scipy.signal import resample_poly  # type: ignore

        g = gcd(int(src_rate), int(dst_rate))
        return resample_poly(audio, int(dst_rate) // g, int(src_rate) // g).astype(np.float32)
    except Exception:
        pass
    duration = audio.size / float(src_rate)
    n_out = int(round(duration * dst_rate))
    x_old = np.linspace(0.0, duration, num=audio.size, endpoint=False)
    x_new = np.linspace(0.0, duration, num=max(n_out, 1), endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def synthesize_piper(
    text: str,
    voice_id: Optional[str] = None,
    speed: float = 1.0,
    target_sample_rate: Optional[int] = None,
) -> Optional[Tuple[np.ndarray, int]]:
    """Synthesize ``text`` to ``(float32 mono samples, sample_rate)``.

    Returns ``None`` (with a log line) when Piper or the model is unavailable,
    so callers can fall back gracefully.  If ``target_sample_rate`` is given,
    the audio is resampled to that rate (e.g. 16000 for the raw WS stream).
    """
    if not PIPER_AVAILABLE:
        app_logger.warning("piper-tts not available; skipping Piper synthesis")
        return None

    text = (text or "").strip()
    if not text:
        return None

    model = find_model_for_voice(voice_id or resolve_voice_id(None))
    if model is None:
        app_logger.warning(
            f"No Piper voice model found for '{voice_id}'. "
            f"Drop a .onnx (and .onnx.json) into ~/piper_models or set ARENA_PIPER_MODEL_DIR."
        )
        return None
    if not model.get("has_config"):
        app_logger.warning(
            f"Piper model '{model['id']}' is missing its .onnx.json config; synthesis may fail."
        )

    voice = _get_voice(Path(model["path"]))
    if voice is None:
        return None

    length_scale = 1.0 / max(0.5, min(2.0, float(speed)))

    result = _synthesize_raw(voice, text, length_scale)
    if result is None:
        app_logger.error(f"Piper synthesis returned no audio for voice '{model['id']}'")
        return None

    audio, sr = result
    if target_sample_rate and sr != target_sample_rate:
        audio = resample(audio, sr, target_sample_rate)
        sr = target_sample_rate

    app_logger.info(f"Piper TTS: {len(text)} chars -> {len(audio)} samples @ {sr} Hz")
    return audio, sr
