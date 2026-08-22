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


def test_hardware_stats_and_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/hardware-stats":
            return httpx.Response(200, json={"cpu_percent": 12.0, "ram_percent": 40.0})
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"status": "online", "app_name": "Arena"})
        return httpx.Response(404)

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    assert client.hardware_stats()["cpu_percent"] == 12.0
    assert client.status()["status"] == "online"
    client.close()


def test_search_files_posts_query():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json=[{"name": "README.md", "path": "/README.md"}])

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    client.search_files("README")
    assert captured["body"]["query"] == "README"
    client.close()


def test_upload_camera_photo_sends_multipart():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "file_name": "photo.jpg"})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    res = client.upload_camera_photo("photo.jpg", b"\xff\xd8\xff\xd9", content_type="image/jpeg")
    assert res["success"] is True
    client.close()


def test_report_location_posts_coordinates():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"success": True})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    client.report_location(0.35, 32.58, city="Kampala")
    assert captured["body"]["latitude"] == 0.35
    assert captured["body"]["longitude"] == 32.58
    assert captured["body"]["city"] == "Kampala"
    client.close()


def test_capture_screen_posts_empty_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"success": True, "file_name": "screen_1.png"})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    res = client.capture_screen()
    assert captured["path"] == "/vision/capture"
    assert res["success"] is True
    client.close()


def test_capture_and_analyze_adds_prompt_focus_query():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = request.url.query.decode()
        return httpx.Response(200, json={"success": True})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    client.capture_and_analyze("the error dialog")
    assert captured["path"] == "/vision/capture-and-analyze"
    assert "prompt_focus=the%20error%20dialog" in captured["query"]
    client.close()


def test_ocr_image_posts_image_path():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"extracted_text": "hello"})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    res = client.ocr_image("/tmp/shot.png")
    assert captured["body"]["image_path"] == "/tmp/shot.png"
    assert res["extracted_text"] == "hello"
    client.close()


def test_analyze_image_posts_path_focus_and_flag():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"ai_analysis": "a window is open"})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    res = client.analyze_image("/tmp/shot.png", prompt_focus="errors", auto_save_memory=False)
    assert captured["body"]["image_path"] == "/tmp/shot.png"
    assert captured["body"]["prompt_focus"] == "errors"
    assert captured["body"]["auto_save_memory"] is False
    assert res["ai_analysis"] == "a window is open"
    client.close()


def test_fetch_image_bytes_gets_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x89PNG\r\n\x1a\n")

    client = ArenaBackendClient(base_url="http://localhost:8000")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    data = client.fetch_image_bytes("/static/workspace/screenshots/screen_1.png")
    assert data == b"\x89PNG\r\n\x1a\n"
    client.close()


def test_get_shared_settings_with_short_timeout():
    """Startup hydration uses a bounded timeout (backend may be offline)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"theme": "light", "wake_word": "hey_arena"})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    data = client.get_shared_settings(timeout=2.0)
    assert data["theme"] == "light"
    client.close()


def test_get_shared_settings_timeout_raises_backend_error():
    """A short-timeout hydration fails fast (BackendConnectionError), not hang."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    with pytest.raises(BackendConnectionError):
        client.get_shared_settings(timeout=0.5)
    client.close()


def test_resolve_location_uses_native_service(monkeypatch):
    from desktop import backend_client as bc

    monkeypatch.setattr(
        bc, "__import__", None
    ) if False else None  # no-op guard

    class _FakeLS:
        @staticmethod
        def resolve_location():
            return {"success": True, "latitude": 0.35, "longitude": 32.58, "source": "ip_geolocation"}

    import app.tools.location_service as ls
    monkeypatch.setattr(ls, "LocationService", _FakeLS)

    client = ArenaBackendClient()
    res = client.resolve_location()
    assert res["success"] is True
    assert res["latitude"] == 0.35
    client.close()
