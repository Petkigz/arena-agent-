"""Live screenshot streaming and analysis."""

import asyncio
import base64
import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from app.config import settings
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/screenshots", tags=["screenshots"])


class ScreenshotMetadata(BaseModel):
    """Metadata for a screenshot."""
    id: str
    timestamp: str
    width: int
    height: int
    format: str = "png"
    annotations: List[Dict[str, Any]] = Field(default_factory=list)
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
                image_payload = data.get("image")
                if not isinstance(image_payload, str) or not image_payload:
                    await websocket.send_json({"type": "error", "message": "Screenshot image is required"})
                    continue
                # Base64 expands bytes by ~4/3; cap encoded input before storing it
                # in the process-wide screenshot cache.
                if len(image_payload) > 20 * 1024 * 1024:
                    await websocket.send_json({"type": "error", "message": "Screenshot exceeds size limit"})
                    continue
                # Process and broadcast screenshot
                screenshot_data = {
                    "id": data.get("id", f"ss-{datetime.now().timestamp()}"),
                    "timestamp": datetime.now().isoformat(),
                    "image": image_payload,  # Base64 encoded image
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
    """Analyze stored screenshot bytes with the real OCR/vision tools."""
    screenshot = screenshot_store.get(request.screenshot_id)
    if not screenshot:
        return ScreenshotAnalysisResponse(
            success=False,
            screenshot_id=request.screenshot_id,
            error="Screenshot not found",
        )

    analysis_type = request.analysis_type.strip().lower()
    if analysis_type not in {"vision", "ocr", "both"}:
        return ScreenshotAnalysisResponse(
            success=False,
            screenshot_id=request.screenshot_id,
            error="analysis_type must be one of: vision, ocr, both",
        )

    temp_path: Optional[Path] = None
    try:
        encoded = screenshot.get("image")
        if not isinstance(encoded, str) or not encoded.strip():
            raise ValueError("Screenshot has no image data")
        encoded = encoded.split(",", 1)[-1]
        image_data = base64.b64decode(encoded, validate=True)
        if not image_data:
            raise ValueError("Screenshot image is empty")
        if len(image_data) > 15 * 1024 * 1024:
            raise ValueError("Screenshot image exceeds 15 MB")

        # Decode and normalize with Pillow before any tool receives a path. This
        # rejects arbitrary bytes and prevents user-controlled filenames.
        from PIL import Image
        with Image.open(io.BytesIO(image_data)) as image:
            image.load()
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 40_000_000:
                raise ValueError("Screenshot dimensions are invalid or too large")
            screenshots_dir = settings.DATA_DIR / "screenshots" / "analysis"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            temp_path = screenshots_dir / f"ss_{uuid.uuid4().hex}.png"
            image.convert("RGB").save(temp_path, format="PNG")

        components: Dict[str, Any] = {}
        errors: List[str] = []

        if analysis_type in {"ocr", "both"}:
            from app.tools.ocr_reader import OCRReaderTool
            ocr_result = await asyncio.to_thread(
                OCRReaderTool.extract_text_from_image, str(temp_path)
            )
            ocr_success = bool(ocr_result.get("success"))
            components["ocr"] = {
                "success": ocr_success,
                "text": ocr_result.get("extracted_text", ""),
                "error": ocr_result.get("error"),
            }
            if not ocr_success:
                errors.append(f"OCR: {ocr_result.get('error', 'analysis failed')}")

        if analysis_type in {"vision", "both"}:
            from app.tools.vision_analyzer import VisionAnalyzerTool
            vision_result = await asyncio.to_thread(
                VisionAnalyzerTool.analyze_screen_image,
                str(temp_path),
                request.prompt_focus,
                "main",
                False,
                True,
            )
            vision_success = bool(vision_result.get("success"))
            components["vision"] = {
                "success": vision_success,
                "analysis": vision_result.get("ai_analysis", ""),
                "detections": vision_result.get("detections", []),
                "groundings_created": vision_result.get("groundings_created", []),
                "engine": vision_result.get("engine") or vision_result.get("detection_engine"),
                "error": vision_result.get("error"),
            }
            if not vision_success:
                errors.append(f"Vision: {vision_result.get('error', 'analysis failed')}")

        complete = not errors and all(
            component.get("success") is True for component in components.values()
        )
        analysis = {
            "type": analysis_type,
            "prompt_focus": request.prompt_focus,
            "timestamp": datetime.now().isoformat(),
            "image": {"width": width, "height": height, "normalized_format": "png"},
            "components": components,
            "complete": complete,
        }
        screenshot["analysis"] = analysis
        return ScreenshotAnalysisResponse(
            success=complete,
            screenshot_id=request.screenshot_id,
            analysis=analysis,
            error="; ".join(errors) if errors else None,
        )
    except Exception as e:
        app_logger.error(f"Screenshot analysis failed: {e}")
        return ScreenshotAnalysisResponse(
            success=False,
            screenshot_id=request.screenshot_id,
            error=str(e),
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception as exc:
                app_logger.warning(f"Could not remove screenshot analysis temp file: {exc}")


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
