"""Unified Arena server — the single authoritative entry point.

Combines everything that was previously split across two FastAPI apps:

- `app/main.py`  (127 core REST routes: /chat, /tasks, /models, /tools/*, …)
- `backend/main.py` (WebSocket chat, /api/* routers, /health, SPA serving, voice, scheduler)

Run:  PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.utils.logger import app_logger

# ── Core REST routes (127) — previously served only by `uvicorn app.main:app` ──
from app.main import router as core_router

# ── WebSocket / voice / API wiring — previously served only by `uvicorn backend.main:app` ──
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


# ============================================================================
# Configuration
# ============================================================================

CORS_ORIGINS = os.getenv(
    "ARENA_CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:8080,http://127.0.0.1:5173"
).split(",")

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
# Runtime & lifespan
# ============================================================================

runtime = CognitiveRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    app_logger.info("Starting Arena (unified server)...")
    message_router_module.initialize_message_router(runtime)

    if message_router_module.message_router:
        message_router_module.message_router.set_voice_service(voice_service)
        app_logger.info("Voice service wired into message router")

    # Schedule the autonomous cognitive cycle (observe → generate goals → execute
    # → reflect → consolidate memory → proactive maintenance) on an hourly timer.
    try:
        from app.scheduler import ProactiveScheduler
        ProactiveScheduler.schedule_recurring(
            "autonomous_cycle",
            runtime.run_autonomous_cycle,
            interval_seconds=3600,
        )
        app_logger.info("Autonomous cognitive cycle scheduled (every 3600s).")
    except Exception as e:
        app_logger.warning(f"Could not schedule autonomous cycle: {e}")

    app_logger.info(
        f"Arena started (CORS: {CORS_ORIGINS}, Auth: {'enabled' if API_KEY_ENABLED else 'disabled'})"
    )

    yield

    app_logger.info("Shutting down Arena...")
    try:
        await voice_service.stop()
        app_logger.info("Voice service stopped during shutdown")
    except Exception as e:
        app_logger.error(f"Error stopping voice service during shutdown: {e}")


# ============================================================================
# SPA (frontend) serving
# ============================================================================

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


def _spa_index_or_none() -> FileResponse | None:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return None


# ============================================================================
# App factory
# ============================================================================

def create_app() -> FastAPI:
    app = FastAPI(
        title="Arena",
        description="Local cognitive assistant — core REST + WebSocket + voice + SPA",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Root: React SPA for browsers, JSON status for API clients ──
    # Registered FIRST so it wins over the core router's legacy `/` handler.
    @app.get("/")
    async def root(request: Request):
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            spa = _spa_index_or_none()
            if spa is not None:
                return spa
        return {
            "status": "online",
            "app_name": "Arena - Local AI Assistant",
            "version": "2.0.0",
            "docs": "/docs",
        }

    # ── Core REST routes (127) ──
    app.include_router(core_router)

    # ── API routers (file upload, code exec, multi-modal, screenshot, …) ──
    # SECURITY: gated behind verify_api_key (no-op when ARENA_API_KEY is unset).
    _auth_deps = [Depends(verify_api_key)]
    app.include_router(phase6_router, dependencies=_auth_deps)
    app.include_router(screenshot_router, dependencies=_auth_deps)
    app.include_router(wakeword_router, dependencies=_auth_deps)
    app.include_router(language_router, dependencies=_auth_deps)
    app.include_router(device_router, dependencies=_auth_deps)
    app.include_router(theme_router, dependencies=_auth_deps)
    app.include_router(speaker_router, dependencies=_auth_deps)

    # ── Health & conversations ──
    @app.get("/health")
    async def health_check():
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
        return {"conversations": ws_manager.get_active_conversations()}

    # ── WebSocket endpoints ──
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
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
                        await websocket.send_json({"type": "error", "message": "Server not ready"})

                elif "bytes" in message:
                    if voice_service and voice_service.pipeline and voice_service.pipeline.audio_capture:
                        pass  # Audio comes via local mic in PC mode
                    else:
                        app_logger.debug(
                            f"Received {len(message['bytes'])} audio bytes (no pipeline active)"
                        )
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)
            app_logger.info("WebSocket client disconnected")
        except Exception as e:
            app_logger.error(f"WebSocket error: {e}", exc_info=True)
            await ws_manager.disconnect(websocket)

    @app.websocket("/ws/voice")
    async def websocket_voice_endpoint(websocket: WebSocket):
        await websocket_endpoint(websocket)

    # ── SPA static assets + catch-all (registered LAST so specific routes win) ──
    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

        @app.get("/{full_path:path}")
        async def serve_frontend(request: Request, full_path: str):
            file_path = FRONTEND_DIST / full_path
            if full_path and file_path.is_file():
                return FileResponse(str(file_path))
            spa = _spa_index_or_none()
            if spa is not None:
                return spa
            return JSONResponse({
                "status": "online",
                "app_name": "Arena - Local AI Assistant",
                "message": "Frontend not built. Run 'cd frontend && npm run build'.",
                "api_docs": "/docs",
            })

    return app


app = create_app()
