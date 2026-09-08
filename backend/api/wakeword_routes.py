"""Custom wake word training and management."""

import os
import base64
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, ConfigDict
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/wakeword", tags=["wakeword"])


class WakeWordSample(BaseModel):
    """A single wake word sample."""
    id: str
    audio: str  # Base64 encoded audio
    timestamp: str
    duration: float  # seconds
    sample_rate: int
    channels: int


class WakeWordTrainingRequest(BaseModel):
    """Request to train a custom wake word."""
    wake_word: str
    samples: List[WakeWordSample]
    sensitivity: float = 0.5


class WakeWordTrainingResponse(BaseModel):
    """Response from wake word training."""
    model_config = ConfigDict(protected_namespaces=())
    success: bool
    model_id: Optional[str] = None
    model_path: Optional[str] = None
    accuracy: Optional[float] = None
    available: bool = False
    samples_validated: int = 0
    requirements: Optional[str] = None
    error: Optional[str] = None


class WakeWordModel(BaseModel):
    """A trained wake word model."""
    model_config = ConfigDict(protected_namespaces=())
    id: str
    name: str
    wake_word: str
    model_path: str
    created_at: str
    sample_count: int
    accuracy: Optional[float] = None
    is_active: bool = False


# Storage directory for wake word models
WAKEWORD_DIR = Path("./data/wakeword")
WAKEWORD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory storage for models (in production, use database)
wakeword_models: Dict[str, WakeWordModel] = {}


@router.post("/train", response_model=WakeWordTrainingResponse)
async def train_wake_word(request: WakeWordTrainingRequest):
    """Validate a training request without fabricating a trained ONNX model.

    The installed ``openwakeword`` runtime performs inference; it does not expose
    the complete custom-model training pipeline needed here. Until that pipeline
    is installed and its output is validated, this endpoint must report
    unavailable and create no model or accuracy claim.
    """
    if len(request.samples) < 5:
        return WakeWordTrainingResponse(
            success=False,
            samples_validated=len(request.samples),
            error="At least 5 samples required for training",
        )
    if not request.wake_word or len(request.wake_word.strip()) < 2:
        return WakeWordTrainingResponse(
            success=False,
            samples_validated=len(request.samples),
            error="Wake word must be at least 2 characters",
        )

    valid_samples = 0
    for sample in request.samples:
        try:
            encoded = sample.audio.split(",", 1)[-1]
            raw = base64.b64decode(encoded, validate=True)
            if raw and sample.duration > 0 and sample.sample_rate > 0 and sample.channels > 0:
                valid_samples += 1
        except Exception:
            continue
    if valid_samples != len(request.samples):
        return WakeWordTrainingResponse(
            success=False,
            samples_validated=valid_samples,
            error="One or more wake-word samples are invalid base64 audio",
        )

    # REAL training (owner live test 2026-09-08): build a local
    # sample-correlation wake model from the owner's own recordings.
    # Honest about the method: not a neural openWakeWord model — a mel
    # template matched by normalized correlation, calibrated on the
    # owner's samples. It runs fully local and actually detects.
    from backend.voice.sample_wake_model import (
        SampleAudioError,
        SamplePackWakeModel,
        pcm16_wav_to_float,
    )

    decoded: list = []
    invalid = 0
    for sample in request.samples:
        try:
            encoded = sample.audio.split(",", 1)[-1]
            raw = base64.b64decode(encoded, validate=True)
            decoded.append(pcm16_wav_to_float(raw))
        except SampleAudioError:
            invalid += 1
        except Exception:
            invalid += 1
    if len(decoded) < 5:
        return WakeWordTrainingResponse(
            success=False,
            samples_validated=len(decoded),
            error=(
                f"Only {len(decoded)} of {len(request.samples)} samples are "
                f"decodable 16-bit PCM WAV ({invalid} invalid). Record from "
                f"the trainer so samples are converted to WAV first."
            ),
        )

    try:
        trained = SamplePackWakeModel.train(request.wake_word.strip(), decoded)
    except SampleAudioError as exc:
        return WakeWordTrainingResponse(
            success=False,
            samples_validated=len(decoded),
            error=f"Training failed: {exc}",
        )

    model_id = uuid.uuid4().hex[:12]
    pack_path = WAKEWORD_DIR / f"{model_id}.npz"
    trained.save(pack_path)
    accuracy = round(min(trained.self_scores), 4) if trained.self_scores else None
    entry = WakeWordModel(
        id=model_id,
        name=f"{request.wake_word.strip()} (trained {datetime.now().strftime('%Y-%m-%d %H:%M')})",
        wake_word=request.wake_word.strip(),
        model_path=str(pack_path),
        created_at=datetime.now().isoformat(),
        sample_count=len(decoded),
        accuracy=accuracy,
    )
    wakeword_models[model_id] = entry
    try:
        from app.utils import decision_trace

        decision_trace.record(
            "wake_word_training",
            "model_trained",
            f"sample-correlation pack trained on {len(decoded)} samples",
            model_id=model_id,
            phrase=request.wake_word.strip(),
            threshold=trained.threshold,
        )
    except Exception:
        pass
    app_logger.info(
        f"Custom wake word trained: '{entry.wake_word}' ({len(decoded)} samples, "
        f"threshold={trained.threshold:.2f}) -> {pack_path.name}"
    )
    return WakeWordTrainingResponse(
        success=True,
        model_id=model_id,
        model_path=str(pack_path),
        accuracy=accuracy,
        available=True,
        samples_validated=len(decoded),
        requirements=(
            "Method: local sample-correlation (mel template), not a neural "
            "openWakeWord model. Activate it, then restart voice so the "
            "detector loads the pack."
        ),
    )


@router.get("/models", response_model=List[WakeWordModel])
async def list_wake_word_models():
    """List all trained wake word models."""
    return list(wakeword_models.values())


@router.get("/models/{model_id}", response_model=WakeWordModel)
async def get_wake_word_model(model_id: str):
    """Get a specific wake word model."""
    model = wakeword_models.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.post("/models/{model_id}/activate")
async def activate_wake_word_model(model_id: str):
    """Activate a wake word model."""
    model = wakeword_models.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    model_file = Path(model.model_path)
    if not model_file.is_file():
        raise HTTPException(status_code=409, detail="Model artifact is missing")
    try:
        if model_file.read_bytes() == b"PLACEHOLDER_MODEL":
            raise HTTPException(
                status_code=409,
                detail="Refusing to activate a legacy placeholder; provide a real validated ONNX model",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Could not validate model artifact: {exc}") from exc

    # Deactivate all other models
    for m in wakeword_models.values():
        m.is_active = False
    
    # Activate this model
    model.is_active = True

    # A trained sample pack becomes the LIVE wake word: the pipeline reads
    # the shared setting on start, so point it at custom:<model_id>.
    if model.model_path.endswith(".npz"):
        try:
            from app.settings_store import update_settings

            update_settings({
                "wake_word": f"custom:{model_id}",
                "wakeWord": f"custom:{model_id}",
            })
        except Exception as exc:
            app_logger.warning(f"Could not point the voice pipeline at the pack: {exc}")

    app_logger.info(f"Activated wake word model: {model_id}")
    
    return {"success": True, "message": f"Activated model '{model.name}'", "wake_word": f"custom:{model_id}" if model.model_path.endswith(".npz") else model_id}


@router.delete("/models/{model_id}")
async def delete_wake_word_model(model_id: str):
    """Delete a wake word model."""
    model = wakeword_models.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Delete model files
    if os.path.exists(model.model_path):
        os.remove(model.model_path)
    
    metadata_path = model.model_path + ".json"
    if os.path.exists(metadata_path):
        os.remove(metadata_path)
    
    # Remove from storage
    del wakeword_models[model_id]
    
    app_logger.info(f"Deleted wake word model: {model_id}")
    
    return {"success": True, "message": "Model deleted"}


@router.post("/samples/upload")
async def upload_wake_word_sample(
    audio: UploadFile = File(...),
    duration: float = 2.0,
    sample_rate: int = 16000,
    channels: int = 1,
):
    """Upload a wake word sample."""
    try:
        # Read audio file
        audio_data = await audio.read()
        
        # Encode to base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        # Create sample
        sample = WakeWordSample(
            id=f"sample-{uuid.uuid4().hex[:8]}",
            audio=audio_base64,
            timestamp=datetime.now().isoformat(),
            duration=duration,
            sample_rate=sample_rate,
            channels=channels,
        )
        
        app_logger.info(f"Uploaded wake word sample: {sample.id}")
        
        return {"success": True, "sample": sample}
    
    except Exception as e:
        app_logger.error(f"Failed to upload wake word sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active")
async def get_active_wake_word():
    """Get the currently active wake word model."""
    active_model = next((m for m in wakeword_models.values() if m.is_active), None)
    
    if not active_model:
        return {"success": False, "message": "No active wake word model"}
    
    return {"success": True, "model": active_model}
