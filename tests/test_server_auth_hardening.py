"""Regression guards for the P0 server-hardening fixes.

- core_router must be behind the same auth as the /api/* routers (when a key is set).
- unauthenticated instances must reject non-loopback clients (insecure-LAN guard),
  unless ARENA_ALLOW_INSECURE_LAN is set.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def reloaded_server(monkeypatch):
    """Reload app.server with a controlled env, then restore on teardown."""
    import app.server as server_module
    monkeypatch.setenv("ARENA_API_KEY", "test-secret-key")
    monkeypatch.delenv("ARENA_ALLOW_INSECURE_LAN", raising=False)
    monkeypatch.delenv("ARENA_ENFORCE_AUTH", raising=False)
    importlib.reload(server_module)
    yield server_module.app
    # Restore the default (no key) app so other tests are unaffected.
    monkeypatch.delenv("ARENA_API_KEY", raising=False)
    importlib.reload(server_module)


def test_core_router_requires_key_when_auth_enabled(reloaded_server):
    """P0 #3: /api/status (core router) must reject when the key is missing."""
    c = TestClient(reloaded_server)
    # No key → 403 (or 401) on a core route.
    resp = c.get("/api/status")
    assert resp.status_code in (401, 403)

    # Correct key → 200.
    resp = c.get("/api/status", headers={"X-API-Key": "test-secret-key"})
    assert resp.status_code == 200


def test_api_routers_require_key_when_auth_enabled(reloaded_server):
    c = TestClient(reloaded_server)
    # /api/wakeword/models is a GET route (no body) — a clean auth probe.
    resp = c.get("/api/wakeword/models")
    assert resp.status_code in (401, 403)


def test_health_is_open_even_when_auth_enabled(reloaded_server):
    """Health check stays unauthenticated (it reveals no capability surface)."""
    c = TestClient(reloaded_server)
    resp = c.get("/health")
    assert resp.status_code == 200


def test_insecure_lan_guard_rejects_non_localhost(monkeypatch):
    import app.server as server_module
    monkeypatch.delenv("ARENA_API_KEY", raising=False)
    monkeypatch.delenv("ARENA_ALLOW_INSECURE_LAN", raising=False)
    importlib.reload(server_module)
    try:
        c = TestClient(server_module.app, client=("192.168.1.50", 12345))
        resp = c.get("/health")
        assert resp.status_code == 403
        assert "localhost" in resp.text or "ARENA_API_KEY" in resp.text
    finally:
        monkeypatch.delenv("ARENA_API_KEY", raising=False)
        importlib.reload(server_module)


def test_insecure_lan_guard_allows_localhost(monkeypatch):
    import app.server as server_module
    monkeypatch.delenv("ARENA_API_KEY", raising=False)
    monkeypatch.delenv("ARENA_ALLOW_INSECURE_LAN", raising=False)
    importlib.reload(server_module)
    try:
        c = TestClient(server_module.app)  # default "testclient" is treated as local
        assert c.get("/health").status_code == 200
    finally:
        importlib.reload(server_module)


def test_insecure_lan_opt_out_allows_non_localhost(monkeypatch):
    import app.server as server_module
    monkeypatch.delenv("ARENA_API_KEY", raising=False)
    monkeypatch.setenv("ARENA_ALLOW_INSECURE_LAN", "1")
    importlib.reload(server_module)
    try:
        c = TestClient(server_module.app, client=("192.168.1.50", 12345))
        assert c.get("/health").status_code == 200
    finally:
        monkeypatch.delenv("ARENA_ALLOW_INSECURE_LAN", raising=False)
        importlib.reload(server_module)
