"""FastAPI application with WebSocket support, CORS, and authentication."""

import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from app.utils.logger import app_logger
from app.cognition.runtime import CognitiveRuntime
from backend.websocket_server import ws_manager
import backend.message_router as message_router_module
from backend.voice.service import voice_service
from backend.api.phase6_routes import router as phase6_router
from backend.api.screenshot_routes import router as screenshot_router
from backend.api.wakeword_routes import router as wakeword_router
from backend.api.language_routes import router as language_router
from backend.api.device_routes import router as device_router
from backend.api.theme_routes import router as theme_router
from backend.api.speaker_routes import router as speaker_router
from pathlib import Path


# ============================================================================
# Configuration
# ============================================================================

# CORS: Restrict origins via environment variable (comma-separated)
# Default: localhost dev servers only
CORS_ORIGINS = os.getenv(
    "ARENA_CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:8080,http://127.0.0.1:5173"
).split(",")

# API Key authentication (optional — set ARENA_API_KEY env var to enable)
API_KEY = os.getenv("ARENA_API_KEY", "")
API_KEY_ENABLED = bool(API_KEY)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(request: Request, api_key: str = Depends(api_key_header)):
    """Verify API key if authentication is enabled."""
    if not API_KEY_ENABLED:
        return  # Auth disabled, allow all
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


# ============================================================================
# App Initialization
# ============================================================================

# Initialize cognitive runtime
runtime = CognitiveRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    app_logger.info("Starting Arena backend...")
    message_router_module.initialize_message_router(runtime)

    # Wire voice service into message router
    if message_router_module.message_router:
        message_router_module.message_router.set_voice_service(voice_service)
        app_logger.info("Voice service wired into message router")

    app_logger.info(f"Arena backend started (CORS: {CORS_ORIGINS}, Auth: {'enabled' if API_KEY_ENABLED else 'disabled'})")

    yield

    # Shutdown
    app_logger.info("Shutting down Arena backend...")
    try:
        await voice_service.stop()
        app_logger.info("Voice service stopped during shutdown")
    except Exception as e:
        app_logger.error(f"Error stopping voice service during shutdown: {e}")


app = FastAPI(
    title="Arena Backend",
    description="Cognitive runtime backend with WebSocket, LLM integration, and voice support",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware — restricted to configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes (with optional API key auth)
app.include_router(phase6_router)
app.include_router(screenshot_router)
app.include_router(wakeword_router)
app.include_router(language_router)
app.include_router(device_router)
app.include_router(theme_router)
app.include_router(speaker_router)


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    # Optional API key verification via query parameter
    if API_KEY_ENABLED:
        ws_api_key = websocket.query_params.get("api_key", "")
        if ws_api_key != API_KEY:
            await websocket.close(code=4003, reason="Invalid API key")
            return

    await ws_manager.connect(websocket)

    try:
        while True:
            try:
                message = await websocket.receive()
            except Exception:
                break

            if "text" in message:
                import json
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    app_logger.warning("Invalid JSON received")
                    continue

                if message_router_module.message_router:
                    await message_router_module.message_router.handle_message(websocket, data)
                else:
                    app_logger.error("Message router not initialized")
                    await websocket.send_json({
                        "type": "error",
                        "message": "Server not ready"
                    })

            elif "bytes" in message:
                audio_bytes = message["bytes"]
                if voice_service and voice_service.pipeline and voice_service.pipeline.audio_capture:
                    pass  # Audio comes via local mic in PC mode
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
    """WebSocket endpoint for Android voice streaming."""
    await websocket_endpoint(websocket)


# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {
        "status": "healthy",
        "service": "arena-backend",
        "version": "2.0.0",
        "active_conversations": len(ws_manager.get_active_conversations()),
        "voice_service_enabled": voice_service is not None,
        "auth_enabled": API_KEY_ENABLED,
    }


@app.get("/conversations")
async def list_conversations():
    """List active conversations."""
    return {
        "conversations": ws_manager.get_active_conversations()
    }


# ============================================================================
# Serve Frontend (Production Mode)
# ============================================================================

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        """Serve the frontend SPA — all routes return index.html."""
        # Check if the requested file exists in dist
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))

        # For all other routes, serve index.html (SPA routing)
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))

        # Fallback: API-style JSON response
        return JSONResponse({
            "status": "online",
            "app_name": "Arena - Local AI Assistant",
            "message": "Frontend not built. Run 'cd frontend && npm run build' to build it.",
            "api_docs": "/docs"
        })
else:
    @app.get("/")
    async def root():
        """Root endpoint when frontend is not built."""
        return {
            "status": "online",
            "app_name": "Arena - Local AI Assistant",
            "version": "2.0.0",
            "message": "Backend running. Frontend not built yet.",
            "build_frontend": "cd frontend && npm run build",
            "api_docs": "/docs",
            "health": "/health"
        }
