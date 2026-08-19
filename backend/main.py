"""FastAPI application with WebSocket support."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.utils.logger import app_logger
from app.cognition.runtime import CognitiveRuntime
from backend.websocket_server import ws_manager
from backend.message_router import initialize_message_router, message_router
from backend.voice.service import voice_service
from backend.api.phase6_routes import router as phase6_router
from backend.api.screenshot_routes import router as screenshot_router
from backend.api.wakeword_routes import router as wakeword_router
from backend.api.language_routes import router as language_router
from backend.api.device_routes import router as device_router
from backend.api.theme_routes import router as theme_router
from backend.api.speaker_routes import router as speaker_router


# Initialize cognitive runtime
runtime = CognitiveRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    app_logger.info("Starting Arena backend...")
    initialize_message_router(runtime)

    # Wire voice service into message router
    if message_router:
        message_router.set_voice_service(voice_service)
        app_logger.info("Voice service wired into message router")

    app_logger.info("Arena backend started successfully")

    yield

    # Shutdown - clean up voice service
    app_logger.info("Shutting down Arena backend...")
    try:
        await voice_service.stop()
        app_logger.info("Voice service stopped during shutdown")
    except Exception as e:
        app_logger.error(f"Error stopping voice service during shutdown: {e}")


# Create FastAPI app
app = FastAPI(
    title="Arena Backend",
    description="Cognitive runtime backend with WebSocket support",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(phase6_router)
app.include_router(screenshot_router)
app.include_router(wakeword_router)
app.include_router(language_router)
app.include_router(device_router)
app.include_router(theme_router)
app.include_router(speaker_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    await ws_manager.connect(websocket)

    try:
        while True:
            # Receive message from client (JSON or binary audio)
            try:
                message = await websocket.receive()
            except Exception:
                break

            if "text" in message:
                # JSON text message
                import json
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    app_logger.warning("Invalid JSON received")
                    continue

                # Route message to appropriate handler
                if message_router:
                    await message_router.handle_message(websocket, data)
                else:
                    app_logger.error("Message router not initialized")
                    await websocket.send_json({
                        "type": "error",
                        "message": "Server not ready"
                    })

            elif "bytes" in message:
                # Binary audio data - forward to voice service
                audio_bytes = message["bytes"]
                if voice_service and voice_service.pipeline and voice_service.pipeline.audio_capture:
                    # Feed binary audio to the voice pipeline
                    # The audio capture service will handle converting to the right format
                    pass  # Audio comes via the local mic, not over WS in PC mode
                else:
                    app_logger.debug(f"Received {len(audio_bytes)} audio bytes (no pipeline active)")

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
        app_logger.info("WebSocket client disconnected")
    except Exception as e:
        app_logger.error(f"WebSocket error: {e}", exc_info=True)
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Android voice streaming.

    Android app streams audio here. Same handler as /ws but allows
    the Android client to connect to a dedicated voice endpoint.
    """
    await websocket_endpoint(websocket)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "arena-backend",
        "version": "2.0.0",
        "active_conversations": len(ws_manager.get_active_conversations()),
        "voice_service_enabled": voice_service is not None,
    }


@app.get("/conversations")
async def list_conversations():
    """List active conversations."""
    return {
        "conversations": ws_manager.get_active_conversations()
    }
