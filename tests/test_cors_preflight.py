"""CORS preflight + API-key header robustness (owner live test 2026-09-08).

The owner's browser preflight for POST /api/wakeword/train was answered
"400 Disallowed CORS origin": the allowlist only had dev-server ports while
the SPA is served by this server itself (localhost:<server port>, LAN IP,
machine name). Pins:

* preflight from the server's own/local/private origins succeeds,
* public origins stay disallowed,
* no X-API-Key header shape can 500 the auth dependency.
"""
import os

os.environ.setdefault("ARENA_ANNOUNCEMENT_GUARD", "0")

import pytest
from fastapi.testclient import TestClient

from app.server import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def _preflight(client, origin):
    return client.options(
        "/api/wakeword/train",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8000",      # the server's own serving origin
        "http://localhost:3000",      # explicit allowlist entry
        "http://127.0.0.1:8000",
        "http://192.168.1.50:8000",   # LAN IP
        "http://10.0.0.7:5173",       # private range
        "http://172.16.4.9:8080",     # private range boundary
        "http://mypc:8000",           # single-label machine name
        "http://mypc.local:8000",     # mDNS name
    ],
)
def test_preflight_allowed_for_local_and_private_origins(client, origin):
    r = _preflight(client, origin)
    assert r.status_code == 200, f"{origin} -> {r.status_code} {r.text[:80]}"
    assert r.headers.get("access-control-allow-origin") == origin
    assert "POST" in r.headers.get("access-control-allow-methods", "")


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        "http://arena-evil.example.com:8000",
    ],
)
def test_preflight_still_rejects_public_origins(client, origin):
    r = _preflight(client, origin)
    assert r.status_code == 400
    assert "Disallowed CORS origin" in r.text


def test_actual_post_from_local_origin_gets_cors_headers(client):
    # A disallowed sample request (no grounding ids) must still carry the
    # CORS headers on the actual response, not just the preflight.
    r = client.post(
        "/api/wakeword/train",
        json={"wake_word": "arena", "samples": []},
        headers={"Origin": "http://localhost:8000"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_wakeword_train_preflight_full_flow(client):
    """The exact owner-facing flow: preflight 200 THEN the real POST runs
    (and honestly reports the missing-samples validation instead of the
    browser dying on a 400 preflight)."""
    pre = _preflight(client, "http://localhost:8000")
    assert pre.status_code == 200
    post = client.post(
        "/api/wakeword/train",
        json={"wake_word": "arena", "samples": []},
        headers={"Origin": "http://localhost:8000"},
    )
    assert post.status_code in (200, 422, 400)
    body = post.json()
    if post.status_code == 200:
        assert body.get("success") is False  # honest validation result


def test_auth_dependency_never_500s_on_any_header_shape(monkeypatch):
    """auto_error=False yields None for a missing header; every shape must
    resolve to an HTTP response (403), never an ASGI exception."""
    monkeypatch.setenv("ARENA_API_KEY", "secret")
    import importlib

    import app.server as server_module

    importlib.reload(server_module)
    try:
        c = TestClient(server_module.create_app(), raise_server_exceptions=False)
        for headers in (
            {},
            {"X-API-Key": ""},
            {"X-API-Key": "wrong"},
            {"X-API-Key": "secret"},
            {"X-API-Key": "a, b"},  # list-shaped value
        ):
            r = c.get("/api/wakeword/models", headers=headers)
            assert r.status_code in (200, 403), headers
        # Direct dependency call with None (the auto_error=False path).
        import asyncio

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(server_module.verify_api_key(None, None))
        assert exc_info.value.status_code == 403
    finally:
        monkeypatch.delenv("ARENA_API_KEY", raising=False)
        importlib.reload(server_module)
