"""
Unit tests for the native desktop client's backend client (no display/server).

The PySide6 GUI itself is not tested here (needs a display); these tests cover the
GUI-free, dependency-light ArenaBackendClient which the window consumes.
"""

import httpx
import pytest

from desktop.backend_client import ArenaBackendClient, BackendConnectionError


def test_health_returns_dict(respx_mock=None):
    # Use httpx.MockTransport to avoid a live server.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "healthy", "service": "arena-backend"})

    client = ArenaBackendClient(base_url="http://localhost:8000")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    assert client.health()["status"] == "healthy"
    assert client.is_online() is True
    client.close()


def test_is_online_false_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = ArenaBackendClient(base_url="http://localhost:9999")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    assert client.is_online() is False
    with pytest.raises(BackendConnectionError):
        client.health()
    client.close()


def test_chat_text_extracts_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "the reply"}}],
            "model": "fast",
        })

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    assert client.chat_text("hello") == "the reply"
    client.close()


def test_chat_text_raises_on_bad_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    with pytest.raises(BackendConnectionError):
        client.chat_text("hello")
    client.close()


def test_chat_sends_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Response(200, request=request).request.content
        # decode body
        import json as _json
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = ArenaBackendClient(base_url="http://localhost:8000/")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    client.chat("hi", complexity="main")

    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["body"]["complexity"] == "main"
    assert captured["url"] == "http://localhost:8000/chat"
    client.close()


def test_context_manager_closes_client():
    with ArenaBackendClient() as client:
        assert client._client.is_closed is False
    assert client._client.is_closed is True
