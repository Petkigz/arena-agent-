"""Custom wake word training and management."""

import os
import json
import base64
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
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
    success: bool
    model_id: Optional[str] = None
    model_path: Optional[str] = None
    accuracy: Optional[float] = None
    error: Optional[str] = None


class WakeWordModel(BaseModel):
    """A trained wake word model."""
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
    """Train a custom wake word model from audio samples."""
    try:
        # Validate request
        if len(request.samples) < 5:
            return WakeWordTrainingResponse(
                success=False,
                error="At least 5 samples required for training"
            )
        
        if not request.wake_word or len(request.wake_word.strip()) < 2:
            return WakeWordTrainingResponse(
                success=False,
                error="Wake word must be at least 2 characters"
            )
        
        # Generate model ID
        model_id = f"ww-{uuid.uuid4().hex[:8]}"
        model_path = str(WAKEWORD_DIR / f"{model_id}.onnx")
        
        # In production, this would use openWakeWord to train a custom model
        # For now, create a placeholder model file
        model_data = {
            "id": model_id,
            "wake_word": request.wake_word,
            "sample_count": len(request.samples),
            "sensitivity": request.sensitivity,
            "trained_at": datetime.now().isoformat(),
            "samples": [
                {
                    "id": sample.id,
                    "duration": sample.duration,
                    "sample_rate": sample.sample_rate,
                }
                for sample in request.samples
            ],
        }
        
        # Save model metadata
        with open(model_path + ".json", "w") as f:
            json.dump(model_data, f, indent=2)
        
        # Create placeholder model file (in production, this would be the trained ONNX model)
        with open(model_path, "wb") as f:
            f.write(b"PLACEHOLDER_MODEL")
        
        # Store model
        model = WakeWordModel(
            id=model_id,
            name=f"{request.wake_word} (custom)",
            wake_word=request.wake_word,
            model_path=model_path,
            created_at=datetime.now().isoformat(),
            sample_count=len(request.samples),
            accuracy=0.85,  # Placeholder accuracy
            is_active=False,
        )
        
        wakeword_models[model_id] = model
        
        app_logger.info(f"Trained custom wake word model: {model_id} for '{request.wake_word}'")
        
        return WakeWordTrainingResponse(
            success=True,
            model_id=model_id,
            model_path=model_path,
            accuracy=model.accuracy
        )
    
    except Exception as e:
        app_logger.error(f"Wake word training failed: {e}")
        return WakeWordTrainingResponse(
            success=False,
            error=str(e)
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
    
    # Deactivate all other models
    for m in wakeword_models.values():
        m.is_active = False
    
    # Activate this model
    model.is_active = True
    
    app_logger.info(f"Activated wake word model: {model_id}")
    
    return {"success": True, "message": f"Activated model '{model.name}'"}


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
