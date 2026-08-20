"""Backward-compatible shim for the unified Arena server.

The WebSocket chat, /api/* routers, /health, SPA serving, and the 127 core REST
routes are now all served by `app.server:app` (the single authoritative entry
point). This module re-exports it so existing imports (`from backend.main import
app`) and any `uvicorn backend.main:app` invocations keep working unchanged.

Run the canonical entry point with:
    PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000
"""

from app.server import (  # noqa: F401  (re-export)
    app,
    create_app,
    runtime,
    verify_api_key,
    CORS_ORIGINS,
    API_KEY,
    API_KEY_ENABLED,
)
