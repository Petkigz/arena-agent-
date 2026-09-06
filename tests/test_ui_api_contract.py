"""UI API contract: docs/UI_API_CONTRACT.md must match the real server surface.

The design review's rule: all clients (web, desktop, future Android) code against ONE
documented contract — not against each other's fetch calls. These tests make the document
honest: every endpoint it documents must exist on the real app (app.server), and the
WebSocket message table must match what desktop/chat_client.py actually speaks.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "UI_API_CONTRACT.md"
CHAT_CLIENT = REPO / "desktop" / "chat_client.py"


def _documented_endpoints(doc_text: str) -> set[tuple[str, str]]:
    """All backticked `METHOD /path` entries in the contract document."""
    found = set()
    for method, path in re.findall(r"`(GET|POST|PUT|DELETE) (/[^`]+)`", doc_text):
        found.add((method, path.strip()))
    return found


def _normalize(path: str) -> str:
    """Collapse path params so {id} matches {project_id}."""
    return re.sub(r"\{[^}]+\}", "{}", path)


@pytest.fixture(scope="module")
def server_routes():
    from app.server import app

    routes = set()
    ws_paths = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        if "WebSocket" in type(route).__name__:
            ws_paths.add(path)
        methods = getattr(route, "methods", None)
        if methods:
            for method in methods:
                if method in ("GET", "POST", "PUT", "DELETE"):
                    routes.add((method, path))
    return routes, ws_paths


def test_contract_document_exists_and_covers_the_ui_surface():
    text = DOC.read_text(encoding="utf-8")
    assert "## 1. WebSocket" in text
    assert "## 2. HTTP" in text
    assert "## 3. Compositions" in text
    endpoints = _documented_endpoints(text)
    # The contract must actually document the core UI surface.
    for required in (
        ("GET", "/health"),
        ("GET", "/api/status"),
        ("POST", "/chat"),
        ("GET", "/conversations"),
        ("GET", "/projects"),
        ("GET", "/memories"),
        ("GET", "/knowledge/graph"),
        ("GET", "/owner-control/autonomous-goals"),
    ):
        assert required in endpoints, f"contract doc lost {required}"


def test_every_documented_endpoint_exists_on_the_server(server_routes):
    routes, _ws_paths = server_routes
    text = DOC.read_text(encoding="utf-8")
    documented = _documented_endpoints(text)
    assert documented, "contract doc documents no endpoints"
    real = {(method, _normalize(path)) for method, path in routes}
    missing = {(m, p) for m, p in documented if (m, _normalize(p)) not in real}
    assert not missing, f"contract doc documents endpoints the server does not serve: {sorted(missing)}"


def test_websocket_contract_matches_the_desktop_client():
    """Every WS message type the desktop client handles/sends must be documented."""
    text = DOC.read_text(encoding="utf-8")
    source = CHAT_CLIENT.read_text(encoding="utf-8")

    handled = set(re.findall(r't == "([a-z_]+)"', source))
    sent = set(re.findall(r'"type": "([a-z_]+)"', source))
    for message_type in handled | sent:
        assert f"`{message_type}`" in text, f"WS message type {message_type!r} missing from the contract doc"

    # The conversation transport endpoint is real.
    routes, ws_paths = None, None  # imported lazily to keep this test standalone
    from app.server import app

    ws_paths = {getattr(r, "path", "") for r in app.routes if "WebSocket" in type(r).__name__}
    assert "/ws" in ws_paths


def test_working_context_composition_uses_contract_endpoints():
    """The inline working-context card composes from documented endpoints only."""
    worker_source = (REPO / "desktop" / "workers.py").read_text(encoding="utf-8")
    assert "autonomous_goals" in worker_source
    assert "list_projects" in worker_source
    assert "list_memories" in worker_source

    text = DOC.read_text(encoding="utf-8")
    assert "Working-context card" in text
    for endpoint in ("GET /projects", "GET /owner-control/autonomous-goals", "GET /memories"):
        assert f"`{endpoint}`" in text
