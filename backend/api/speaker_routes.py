"""Speaker identification and voice enrollment."""

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
    available: bool = False
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    confidence: Optional[float] = None
    engine: Optional[str] = None
    error: Optional[str] = None


# In-memory storage for speakers (in production, use database)
enrolled_speakers: Dict[str, Speaker] = {}


@router.get("/", response_model=List[Speaker])
async def list_speakers():
    """List all enrolled speakers."""
    return list(enrolled_speakers.values())


@router.post("/enroll")
async def enroll_speaker(request: EnrollmentRequest):
    """Reject enrollment until a real embedding engine is configured.

    Metadata without a generated embedding is not enrollment. Returning HTTP 501
    is safer than creating a nonexistent ``.npy`` path and later claiming a match.
    """
    if len(request.samples) < 3:
        raise HTTPException(status_code=400, detail="At least 3 samples required")
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Speaker name is required")
    app_logger.warning(
        f"Speaker enrollment requested for '{request.name}' but no verified embedding engine is configured"
    )
    raise HTTPException(
        status_code=501,
        detail=(
            "Speaker enrollment is unavailable: no verified speaker-embedding engine is configured. "
            "No speaker record or embedding was created."
        ),
    )


@router.post("/identify", response_model=IdentificationResult)
async def identify_speaker(audio: UploadFile = File(...)):
    """Report identification unavailable rather than selecting a fake match."""
    # Read a bounded amount so malformed/oversized uploads do not become a
    # memory sink, but do not claim that merely receiving bytes identifies anyone.
    audio_bytes = await audio.read(10 * 1024 * 1024 + 1)
    if not audio_bytes:
        return IdentificationResult(success=False, available=False, error="Audio sample is empty")
    if len(audio_bytes) > 10 * 1024 * 1024:
        return IdentificationResult(success=False, available=False, error="Audio sample exceeds 10 MB")
    if not enrolled_speakers:
        return IdentificationResult(success=False, available=False, error="No speakers enrolled")
    return IdentificationResult(
        success=False,
        available=False,
        error=(
            "Speaker identification is unavailable: enrolled metadata has no verified embeddings. "
            "No identity or confidence was inferred."
        ),
    )


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
