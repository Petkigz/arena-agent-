"""Shared SPA-serving helpers.

Used by both `app/server.py` (unified app) and `app/main.py` (core router) so
that browser requests for paths that collide with API routes (e.g. GET
/settings, GET /projects/{id}) serve the built React SPA, while API clients
(Accept: application/json, */*) keep receiving JSON.

The SPA is the Vite build output in `frontend/dist`. When it has not been
built, `spa_index_or_none()` returns None and callers fall through to their
normal JSON behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import FileResponse

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def spa_index_or_none() -> Optional[FileResponse]:
    """Return a FileResponse for the built SPA index.html, or None."""
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return None


def wants_html(request: Request) -> bool:
    """True when the client is a browser asking for an HTML document."""
    return "text/html" in request.headers.get("accept", "")


def spa_for_browsers(request: Request):
    """Serve the SPA to browsers, or None to continue with the JSON handler.

    Usage inside a route handler::

        spa = spa_for_browsers(request)
        if spa is not None:
            return spa
        ...  # normal JSON path
    """
    if wants_html(request):
        return spa_index_or_none()
    return None
