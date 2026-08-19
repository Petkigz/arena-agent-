"""Speaker identification and voice enrollment."""

import uuid
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/speakers", tags=["speakers"])


class Speaker(BaseModel):
    """An enrolled speaker."""
    id: str
    name: str
    enrolled_at: str
    sample_count: int
    embedding_path: Optional[str] = None
    is_active: bool = True


class EnrollmentRequest(BaseModel):
    """Request to enroll a speaker."""
    name: str
    samples: List[str]  # Base64 encoded audio samples


class IdentificationResult(BaseModel):
    """Result of speaker identification."""
    success: bool
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    confidence: Optional[float] = None
    error: Optional[str] = None


# In-memory storage for speakers (in production, use database)
enrolled_speakers: Dict[str, Speaker] = {}


@router.get("/", response_model=List[Speaker])
async def list_speakers():
    """List all enrolled speakers."""
    return list(enrolled_speakers.values())


@router.post("/enroll", response_model=Speaker)
async def enroll_speaker(request: EnrollmentRequest):
    """Enroll a new speaker."""
    try:
        if len(request.samples) < 3:
            raise HTTPException(status_code=400, detail="At least 3 samples required")
        
        speaker_id = f"spk-{uuid.uuid4().hex[:8]}"
        
        # In production, this would use Resemblyzer to create speaker embedding
        # For now, create placeholder
        speaker = Speaker(
            id=speaker_id,
            name=request.name,
            enrolled_at=datetime.now().isoformat(),
            sample_count=len(request.samples),
            embedding_path=f"./data/speakers/{speaker_id}.npy",
            is_active=True,
        )
        
        enrolled_speakers[speaker_id] = speaker
        
        app_logger.info(f"Enrolled speaker: {speaker_id} ({request.name})")
        
        return speaker
    
    except Exception as e:
        app_logger.error(f"Failed to enroll speaker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identify", response_model=IdentificationResult)
async def identify_speaker(audio: UploadFile = File(...)):
    """Identify a speaker from audio."""
    try:
        # In production, this would use Resemblyzer to identify speaker
        # For now, return placeholder
        if not enrolled_speakers:
            return IdentificationResult(
                success=False,
                error="No speakers enrolled"
            )
        
        # Return first speaker as placeholder
        speaker = list(enrolled_speakers.values())[0]
        
        return IdentificationResult(
            success=True,
            speaker_id=speaker.id,
            speaker_name=speaker.name,
            confidence=0.85,
        )
    
    except Exception as e:
        app_logger.error(f"Failed to identify speaker: {e}")
        return IdentificationResult(success=False, error=str(e))


@router.delete("/{speaker_id}")
async def delete_speaker(speaker_id: str):
    """Delete an enrolled speaker."""
    if speaker_id not in enrolled_speakers:
        raise HTTPException(status_code=404, detail="Speaker not found")
    
    del enrolled_speakers[speaker_id]
    app_logger.info(f"Deleted speaker: {speaker_id}")
    
    return {"success": True, "message": "Speaker deleted"}


@router.post("/{speaker_id}/toggle")
async def toggle_speaker(speaker_id: str):
    """Toggle speaker active status."""
    speaker = enrolled_speakers.get(speaker_id)
    if not speaker:
        raise HTTPException(status_code=404, detail="Speaker not found")
    
    speaker.is_active = not speaker.is_active
    
    return {"success": True, "is_active": speaker.is_active}
