"""
Regression guard: cross-component wiring that per-module unit tests miss.

These tests pin client↔server connections that previously broke silently:

1. ``/static/*`` and ``/audio/*`` must actually be served by the unified app.
   FastAPI's ``include_router()`` drops ``Mount`` routes attached to an
   APIRouter, which previously made every ``/static/*`` and ``/audio/*`` URL
   404 — including TTS playback (TextToSpeech returns
   ``audio_url="/audio/<file>.wav"``).
2. SPA page paths that collide with API GET routes (``/settings``,
   ``/projects/{id}``) must serve the SPA to browsers (``Accept: text/html``)
   and keep serving JSON to API clients.
3. ``GET /`` must explain itself to browsers when the frontend has not been
   built, instead of silently returning bare JSON.
"""

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

from app.config import settings
from app.server import app
from app.utils import spa as spa_module


def test_static_mount_reaches_unified_app():
    """app/static/* must be reachable (the legacy router.mount was dropped)."""
    c = TestClient(app)
    r = c.get("/static/manifest.json")
    assert r.status_code == 200, "/static mount missing on the unified app"


def test_audio_mount_reaches_unified_app():
    """/audio/<file> must be reachable — TTS playback depends on it."""
    audio_dir = Path(settings.DATA_DIR) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    probe = audio_dir / "wiring_regression_probe.txt"
    probe.write_text("probe")
    try:
        c = TestClient(app)
        r = c.get("/audio/wiring_regression_probe.txt")
        assert r.status_code == 200, "/audio mount missing on the unified app"
        assert r.text == "probe"
    finally:
        probe.unlink(missing_ok=True)


def _serve_fake_spa(monkeypatch, tmp_path):
    """Point the SPA helper at a temp index.html and return its body marker.

    Patches both the canonical helper (app.utils.spa, used by spa_for_browsers
    in the core router) and the alias app.server imported at module load.
    """
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><html><body>spa-marker</body></html>")
    fake = lambda: FileResponse(str(index))  # noqa: E731
    monkeypatch.setattr(spa_module, "spa_index_or_none", fake)
    import app.server as server_module
    monkeypatch.setattr(server_module, "_spa_index_or_none", fake)
    return index


def test_settings_serves_spa_to_browsers(monkeypatch, tmp_path):
    """/settings is both an SPA page and an API route: browsers get the app."""
    _serve_fake_spa(monkeypatch, tmp_path)
    c = TestClient(app)
    r = c.get("/settings", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "spa-marker" in r.text
    assert "text/html" in r.headers["content-type"]


def test_settings_serves_json_to_api_clients():
    c = TestClient(app)
    r = c.get("/settings", headers={"accept": "application/json"})
    assert r.status_code == 200
    body = r.json()
    assert "wake_word" in body, f"expected the settings payload, got: {body}"


def test_project_detail_serves_spa_to_browsers(monkeypatch, tmp_path):
    _serve_fake_spa(monkeypatch, tmp_path)
    c = TestClient(app)
    r = c.get("/projects/some-id", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "spa-marker" in r.text


def test_project_detail_keeps_api_404_for_clients():
    c = TestClient(app)
    r = c.get("/projects/definitely-missing-project", headers={"accept": "application/json"})
    assert r.status_code == 404


def test_root_explains_missing_frontend_build(monkeypatch):
    """Browsers hitting / with no built SPA must get an actionable message."""
    monkeypatch.setattr(spa_module, "spa_index_or_none", lambda: None)
    import app.server as server_module
    monkeypatch.setattr(server_module, "_spa_index_or_none", lambda: None)
    c = TestClient(app)
    r = c.get("/", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "npm run build" in r.json().get("message", "")


def test_root_serves_spa_to_browsers_when_built(monkeypatch, tmp_path):
    _serve_fake_spa(monkeypatch, tmp_path)
    c = TestClient(app)
    r = c.get("/", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "spa-marker" in r.text
