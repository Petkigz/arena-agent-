"""Device management and pairing."""

import uuid
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/devices", tags=["devices"])


class Device(BaseModel):
    """A paired device."""
    id: str
    name: str
    type: str  # "phone", "tablet", "pc"
    platform: str  # "android", "ios", "windows", "linux", "macos"
    paired_at: str
    last_seen: Optional[str] = None
    is_online: bool = False


class PairingRequest(BaseModel):
    """Request to pair a device."""
    device_name: str
    device_type: str
    platform: str
    pairing_code: Optional[str] = None


class PairingResponse(BaseModel):
    """Response from pairing request."""
    success: bool
    device_id: Optional[str] = None
    pairing_code: Optional[str] = None
    error: Optional[str] = None


# In-memory storage for devices (in production, use database)
paired_devices: Dict[str, Device] = {}


@router.get("/", response_model=List[Device])
async def list_devices():
    """List all paired devices."""
    return list(paired_devices.values())


@router.post("/pair", response_model=PairingResponse)
async def pair_device(request: PairingRequest):
    """Pair a new device."""
    try:
        # Generate device ID and pairing code
        device_id = f"dev-{uuid.uuid4().hex[:8]}"
        pairing_code = str(uuid.uuid4().int)[:6]  # 6-digit code
        
        # Create device
        device = Device(
            id=device_id,
            name=request.device_name,
            type=request.device_type,
            platform=request.platform,
            paired_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat(),
            is_online=True,
        )
        
        paired_devices[device_id] = device
        
        app_logger.info(f"Paired device: {device_id} ({request.device_name})")
        
        return PairingResponse(
            success=True,
            device_id=device_id,
            pairing_code=pairing_code
        )
    
    except Exception as e:
        app_logger.error(f"Failed to pair device: {e}")
        return PairingResponse(success=False, error=str(e))


@router.post("/pair/code/{pairing_code}")
async def pair_with_code(pairing_code: str, device_name: str, device_type: str, platform: str):
    """Pair device using a pairing code."""
    # In production, this would validate the code and complete pairing
    return await pair_device(PairingRequest(
        device_name=device_name,
        device_type=device_type,
        platform=platform,
        pairing_code=pairing_code,
    ))


@router.delete("/{device_id}")
async def unpair_device(device_id: str):
    """Unpair a device."""
    if device_id not in paired_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    del paired_devices[device_id]
    app_logger.info(f"Unpaired device: {device_id}")
    
    return {"success": True, "message": "Device unpaired"}


@router.post("/{device_id}/ping")
async def ping_device(device_id: str):
    """Ping a device to check if it's online."""
    device = paired_devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Update last seen
    device.last_seen = datetime.now().isoformat()
    device.is_online = True
    
    return {"success": True, "is_online": True}
