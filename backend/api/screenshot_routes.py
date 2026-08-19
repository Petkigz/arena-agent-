"""Live screenshot streaming and analysis."""

import asyncio
import base64
import io
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/screenshots", tags=["screenshots"])


class ScreenshotMetadata(BaseModel):
    """Metadata for a screenshot."""
    id: str
    timestamp: str
    width: int
    height: int
    format: str = "png"
    annotations: List[Dict[str, Any]] = []
    analysis: Optional[Dict[str, Any]] = None


class ScreenshotAnalysisRequest(BaseModel):
    """Request to analyze a screenshot."""
    screenshot_id: str
    prompt_focus: Optional[str] = None
    analysis_type: str = "vision"  # vision, ocr, or both


class ScreenshotAnalysisResponse(BaseModel):
    """Response from screenshot analysis."""
    success: bool
    screenshot_id: str
    analysis: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# In-memory storage for screenshots (in production, use database)
screenshot_store: Dict[str, Dict[str, Any]] = {}


class ScreenshotStreamManager:
    """Manages screenshot streaming connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.latest_screenshots: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, conversation_id: str, websocket: WebSocket):
        """Connect a WebSocket for screenshot streaming."""
        await websocket.accept()
        
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        
        self.active_connections[conversation_id].append(websocket)
        app_logger.info(f"Screenshot stream connected for conversation {conversation_id}")
    
    def disconnect(self, conversation_id: str, websocket: WebSocket):
        """Disconnect a WebSocket."""
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].remove(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
        
        app_logger.info(f"Screenshot stream disconnected for conversation {conversation_id}")
    
    async def broadcast_screenshot(self, conversation_id: str, screenshot_data: Dict[str, Any]):
        """Broadcast a screenshot to all connected clients."""
        if conversation_id not in self.active_connections:
            return
        
        # Store latest screenshot
        self.latest_screenshots[conversation_id] = screenshot_data
        
        # Broadcast to all connected clients
        disconnected = []
        for websocket in self.active_connections[conversation_id]:
            try:
                await websocket.send_json({
                    "type": "screenshot",
                    "data": screenshot_data,
                })
            except Exception as e:
                app_logger.error(f"Failed to send screenshot: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            self.disconnect(conversation_id, websocket)
    
    def get_latest_screenshot(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest screenshot for a conversation."""
        return self.latest_screenshots.get(conversation_id)


# Global screenshot stream manager
screenshot_manager = ScreenshotStreamManager()


@router.websocket("/ws/{conversation_id}")
async def screenshot_websocket(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for screenshot streaming."""
    await screenshot_manager.connect(conversation_id, websocket)
    
    try:
        while True:
            # Receive screenshot data from client
            data = await websocket.receive_json()
            
            if data.get("type") == "screenshot":
                # Process and broadcast screenshot
                screenshot_data = {
                    "id": data.get("id", f"ss-{datetime.now().timestamp()}"),
                    "timestamp": datetime.now().isoformat(),
                    "image": data.get("image"),  # Base64 encoded image
                    "width": data.get("width"),
                    "height": data.get("height"),
                    "format": data.get("format", "png"),
                    "annotations": data.get("annotations", []),
                }
                
                # Store screenshot
                screenshot_store[screenshot_data["id"]] = screenshot_data
                
                # Broadcast to all connected clients
                await screenshot_manager.broadcast_screenshot(conversation_id, screenshot_data)
                
                app_logger.info(f"Screenshot {screenshot_data['id']} broadcasted to conversation {conversation_id}")
    
    except WebSocketDisconnect:
        screenshot_manager.disconnect(conversation_id, websocket)
    except Exception as e:
        app_logger.error(f"Screenshot WebSocket error: {e}")
        screenshot_manager.disconnect(conversation_id, websocket)


@router.post("/analyze", response_model=ScreenshotAnalysisResponse)
async def analyze_screenshot(request: ScreenshotAnalysisRequest):
    """Analyze a screenshot using vision/OCR."""
    screenshot = screenshot_store.get(request.screenshot_id)
    
    if not screenshot:
        return ScreenshotAnalysisResponse(
            success=False,
            screenshot_id=request.screenshot_id,
            error="Screenshot not found"
        )
    
    try:
        # Decode base64 image
        image_data = base64.b64decode(screenshot["image"])
        
        # In production, this would call the VisionAnalyzerTool or OCRReaderTool
        # For now, return a placeholder analysis
        analysis = {
            "type": request.analysis_type,
            "content": f"Analysis of screenshot {request.screenshot_id}",
            "prompt_focus": request.prompt_focus,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Store analysis
        screenshot["analysis"] = analysis
        
        return ScreenshotAnalysisResponse(
            success=True,
            screenshot_id=request.screenshot_id,
            analysis=analysis
        )
    
    except Exception as e:
        app_logger.error(f"Screenshot analysis failed: {e}")
        return ScreenshotAnalysisResponse(
            success=False,
            screenshot_id=request.screenshot_id,
            error=str(e)
        )


@router.get("/latest/{conversation_id}")
async def get_latest_screenshot(conversation_id: str):
    """Get the latest screenshot for a conversation."""
    screenshot = screenshot_manager.get_latest_screenshot(conversation_id)
    
    if not screenshot:
        return {"success": False, "error": "No screenshots available"}
    
    return {"success": True, "screenshot": screenshot}


@router.get("/{screenshot_id}")
async def get_screenshot(screenshot_id: str):
    """Get a specific screenshot by ID."""
    screenshot = screenshot_store.get(screenshot_id)
    
    if not screenshot:
        return {"success": False, "error": "Screenshot not found"}
    
    return {"success": True, "screenshot": screenshot}


@router.delete("/{screenshot_id}")
async def delete_screenshot(screenshot_id: str):
    """Delete a screenshot."""
    if screenshot_id not in screenshot_store:
        return {"success": False, "error": "Screenshot not found"}
    
    del screenshot_store[screenshot_id]
    return {"success": True, "message": "Screenshot deleted"}
