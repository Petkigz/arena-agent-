"""Unified Arena server — the single authoritative entry point.

Combines everything that was previously split across two FastAPI apps:

- `app/main.py`  (127 core REST routes: /chat, /tasks, /models, /tools/*, …)
- `backend/main.py` (WebSocket chat, /api/* routers, /health, SPA serving, voice, scheduler)

Run (localhost-only by default):
    PYTHONPATH=. uvicorn app.server:app --host 127.0.0.1 --port 8000

To expose beyond localhost (LAN / Android over network), you MUST opt in:

    export ARENA_API_KEY=<a strong random key>   # enables auth on ALL routes + WS
    PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000

Binding to 0.0.0.0 with no ARENA_API_KEY is an insecure default and is refused
unless you explicitly set ARENA_ALLOW_INSECURE_LAN=1.
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
from app.api.owner_control_autonomy import router as owner_control_autonomy_router

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
# Fail-closed mode: when the owner sets ARENA_ENFORCE_AUTH=1, requests are
# rejected (rather than allowed) if ARENA_API_KEY is not configured — useful for
# catching a misconfigured LAN deployment instead of silently running open.
API_KEY_ENFORCED = os.getenv("ARENA_ENFORCE_AUTH", "").strip().lower() in ("1", "true", "yes")
# Explicit opt-in for an insecure LAN binding (no API key, non-localhost). The
# default refuses this; set ARENA_ALLOW_INSECURE_LAN=1 only if you understand
# the risk and accept it.
INSECURE_LAN_ALLOWED = os.getenv("ARENA_ALLOW_INSECURE_LAN", "").strip().lower() in ("1", "true", "yes")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# Client addresses that count as "local" for the insecure-LAN guard. `testclient`
# is what starlette's TestClient reports, so it's treated as local in tests.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _client_is_local(client_host: str) -> bool:
    return (client_host or "").strip().lower() in _LOOPBACK_HOSTS


def _insecure_lan_error() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": "This server is unauthenticated and must only be reached "
                      "from localhost. Set ARENA_API_KEY to allow LAN access, or "
                      "ARENA_ALLOW_INSECURE_LAN=1 to accept the risk.",
        },
    )


async def verify_api_key(request: Request, api_key: str = Depends(api_key_header)):
    """Verify API key if authentication is enabled.

    - No API key set and not enforced → allow (localhost-only operation).
    - Enforced but no key configured → fail closed (misconfiguration).
    - Key set → require the correct X-API-Key header on every request.
    """
    if not API_KEY_ENABLED:
        if API_KEY_ENFORCED:
            raise HTTPException(status_code=503, detail="Authentication required but ARENA_API_KEY is not set")
        return  # Auth disabled, allow all
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


# ============================================================================
# Runtime & lifespan
# ============================================================================

# The server, REST routes, WebSocket router, projects, memory, and owner-control
# endpoints must all share the exact same composition root.
runtime = CognitiveRuntime.get_instance()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    app_logger.info("Starting Arena (unified server)...")
    message_router_module.initialize_message_router(runtime)

    if message_router_module.message_router:
        message_router_module.message_router.set_voice_service(voice_service)
        app_logger.info("Voice service wired into message router")

    # Schedule the autonomous cognitive cycle (observe → generate goals → execute
    # → reflect → consolidate memory → proactive maintenance) — governed by the
    # explicit AUTONOMY_MODE policy (default "supervised"). Only "off" disables it;
    # "supervised" keeps it running with Level-3 actions still owner-approved.
    autonomy_mode = (settings.AUTONOMY_MODE or "supervised").strip().lower()
    if autonomy_mode == "off":
        app_logger.info("Autonomy mode is 'off' — autonomous cycle NOT scheduled.")
    else:
        if autonomy_mode not in ("supervised", "bounded", "full"):
            app_logger.warning(
                f"Unknown AUTONOMY_MODE '{autonomy_mode}' — falling back to 'supervised'."
            )
            autonomy_mode = "supervised"
        try:
            from app.scheduler import ProactiveScheduler
            interval = max(60, int(settings.AUTONOMY_INTERVAL_SECONDS or 3600))
            ProactiveScheduler.schedule_recurring(
                "autonomous_cycle",
                runtime.run_autonomous_cycle,
                interval_seconds=interval,
            )
            app_logger.info(
                f"Autonomous cognitive cycle scheduled every {interval}s (mode: {autonomy_mode})."
            )
        except Exception as e:
            app_logger.warning(f"Could not schedule autonomous cycle: {e}")

    if API_KEY_ENABLED:
        app_logger.info(
            f"Arena started (CORS: {CORS_ORIGINS}, Auth: ENABLED — all routes + WS require X-API-Key)"
        )
    else:
        app_logger.warning(
            "Arena started with authentication DISABLED. This instance exposes "
            "filesystem, application, communications, and Level-3 tools over HTTP. "
            "It must only be bound to localhost (--host 127.0.0.1). To allow LAN "
            "access, set ARENA_API_KEY (all routes + WS will then require it)."
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

    from app.tools.manifest import ToolDependencyUnavailable

    @app.exception_handler(ToolDependencyUnavailable)
    async def _optional_tool_unavailable(_request: Request, exc: ToolDependencyUnavailable):
        return JSONResponse(status_code=503, content=exc.as_result())

    # ── Insecure-LAN guard: unauthenticated instances are localhost-only ──
    # When ARENA_API_KEY is unset (auth off), reject requests from non-loopback
    # clients unless the owner explicitly opted into an insecure LAN binding.
    @app.middleware("http")
    async def _enforce_local_binding(request: Request, call_next):
        if not API_KEY_ENABLED and not INSECURE_LAN_ALLOWED:
            client_host = request.client.host if request.client else ""
            if not _client_is_local(client_host):
                return _insecure_lan_error()
        return await call_next(request)

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
    # SECURITY (P0 fix): the core router carries the powerful capability routes
    # (chat, tools execution, tasks, models, …). Gate it behind verify_api_key
    # exactly like the /api/* routers, so that when ARENA_API_KEY is set, EVERY
    # route is protected — not just the newer ones. (verify_api_key is a no-op
    # when the key is unset, preserving localhost-only operation.)
    _auth_deps = [Depends(verify_api_key)]
    app.include_router(core_router, dependencies=_auth_deps)
    app.include_router(owner_control_autonomy_router, dependencies=_auth_deps)

    # ── API routers (file upload, code exec, multi-modal, screenshot, …) ──
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

    @app.get("/conversations", dependencies=_auth_deps)
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
        elif not INSECURE_LAN_ALLOWED:
            # Unauthenticated instance → reject non-loopback WS clients, same as HTTP.
            client_host = websocket.client.host if websocket.client else ""
            if not _client_is_local(client_host):
                await websocket.close(code=4003, reason="LAN access requires ARENA_API_KEY")
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
                    # Binary frames are always from a remote device (the Android
                    # phone streams raw PCM). Route them to the voice service for
                    # utterance detection → STT → cognitive runtime.
                    # (ingest_remote_audio is synchronous — it buffers audio and
                    # schedules transcription via asyncio.create_task internally.)
                    audio_bytes = message["bytes"]
                    if voice_service:
                        voice_service.ingest_remote_audio(audio_bytes)
                    else:
                        app_logger.debug(
                            f"Received {len(audio_bytes)} audio bytes (no voice service)"
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
