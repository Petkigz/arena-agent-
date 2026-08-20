"""
Regression guard: the unified server (app.server:app) must expose BOTH the core
REST routes (previously `app.main:app`) AND the WebSocket/API/health/SPA surface
(previously `backend.main:app`). This is the single authoritative entry point.
"""

from fastapi.testclient import TestClient

from app.server import app
from backend.main import app as shim_app


def _route_paths(a):
    """Recursively collect concrete path strings from an app's routes."""
    paths = set()

    def walk(routes):
        for r in routes:
            ctx = getattr(r, "include_context", None)
            if ctx is not None:
                walk(ctx.included_router.routes)
            else:
                p = getattr(r, "path", None)
                if p:
                    paths.add(p)

    walk(a.routes)
    return paths


def test_unified_exposes_core_routes():
    paths = _route_paths(app)
    for want in ("/chat", "/tasks", "/models", "/api/status", "/tools/daily-briefing"):
        assert want in paths, f"core route {want} missing"


def test_unified_exposes_backend_surface():
    paths = _route_paths(app)
    for want in ("/health", "/conversations", "/ws", "/ws/voice",
                 "/api/code/execute", "/api/files/upload", "/api/attachments/analyze"):
        assert want in paths, f"backend route {want} missing"


def test_unified_smoke_endpoints():
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/status").status_code == 200
    assert c.get("/").status_code == 200


def test_backend_main_is_shim_to_unified():
    """backend.main.app must be the SAME app object as app.server.app."""
    assert shim_app is app
