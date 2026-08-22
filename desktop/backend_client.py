"""HTTP + WebSocket client for the Arena backend (used by the native desktop app).

Kept GUI-free and dependency-light so it is unit-testable without a display or a
running server. The desktop window (PySide6) consumes this class.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx


class BackendConnectionError(Exception):
    """Raised when the backend cannot be reached or returns an unexpected shape."""


class ArenaBackendClient:
    """Synchronous HTTP client for the unified Arena server (app.server:app)."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 180.0):
        # Strip trailing slash so url-joining is predictable.
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    # ── health ──────────────────────────────────────────────────────────────
    def health(self) -> Dict[str, Any]:
        """GET /health → dict, or raise BackendConnectionError if unreachable."""
        try:
            r = self._client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"Backend unreachable at {self.base_url}: {e}") from e

    def is_online(self) -> bool:
        try:
            return self.health().get("status") == "healthy"
        except BackendConnectionError:
            return False

    # ── chat ────────────────────────────────────────────────────────────────
    def chat(self, content: str, complexity: str = "fast", session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        POST /chat (delegates to the cognitive runtime) and return the parsed
        OpenAI-style response dict.

        Returns the raw response; convenience accessors below extract the text.
        """
        payload: Dict[str, Any] = {
            "messages": [{"role": "user", "content": content}],
            "complexity": complexity,
        }
        if session_id:
            payload["session_id"] = session_id

        try:
            r = self._client.post(f"{self.base_url}/chat", json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"Chat request failed: {e}") from e

    def chat_text(self, content: str, complexity: str = "fast") -> str:
        """Convenience: send a message and return just the assistant reply text."""
        data = self.chat(content, complexity=complexity)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise BackendConnectionError(f"Unexpected chat response shape: {data}") from e

    # ── hardware / status ───────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        """GET /api/status."""
        return self._get_json("/api/status")

    def hardware_stats(self) -> Dict[str, Any]:
        """GET /api/hardware-stats (CPU/RAM/disk telemetry)."""
        return self._get_json("/api/hardware-stats")

    # ── location ────────────────────────────────────────────────────────────
    def report_location(self, latitude: float, longitude: float, city: str = "") -> Dict[str, Any]:
        """POST /mobile/location — store a location context in memory."""
        return self._post_json("/mobile/location", {
            "latitude": latitude,
            "longitude": longitude,
            "city": city,
        })

    def resolve_location(self) -> Dict[str, Any]:
        """Resolve native location (phone GPS → IP fallback)."""
        from app.tools.location_service import LocationService
        return LocationService.resolve_location()

    # ── camera ──────────────────────────────────────────────────────────────
    def upload_camera_photo(self, filename: str, data: bytes, content_type: str = "image/jpeg") -> Dict[str, Any]:
        """POST /mobile/camera — upload a captured still."""
        try:
            r = self._client.post(
                f"{self.base_url}/mobile/camera",
                files={"file": (filename, data, content_type)},
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"Camera upload failed: {e}") from e

    # ── filesystem ──────────────────────────────────────────────────────────
    def search_files(self, query: str, root_dir: str = "", max_results: int = 20) -> Dict[str, Any]:
        """POST /filesystem/search."""
        return self._post_json("/filesystem/search", {
            "query": query,
            "root_dir": root_dir or None,
            "max_results": max_results,
        })

    # ── vision / images ─────────────────────────────────────────────────────
    def capture_screen(self) -> Dict[str, Any]:
        """POST /vision/capture — grab the host desktop screen (native sight)."""
        return self._post_json("/vision/capture", {})

    def capture_and_analyze(self, prompt_focus: Optional[str] = None) -> Dict[str, Any]:
        """POST /vision/capture-and-analyze — capture the screen, OCR + LLM-analyse it."""
        path = "/vision/capture-and-analyze"
        if prompt_focus:
            path += f"?prompt_focus={quote(prompt_focus)}"
        return self._post_json(path, {})

    def ocr_image(self, image_path: str) -> Dict[str, Any]:
        """POST /vision/ocr — extract text from an image already on the host."""
        return self._post_json("/vision/ocr", {"image_path": image_path})

    def analyze_image(self, image_path: str, prompt_focus: Optional[str] = None,
                      auto_save_memory: bool = True) -> Dict[str, Any]:
        """POST /vision/analyze — OCR + LLM analysis of an image on the host."""
        return self._post_json("/vision/analyze", {
            "image_path": image_path,
            "prompt_focus": prompt_focus,
            "auto_save_memory": auto_save_memory,
        })

    def upload_image_file(self, file_path: str) -> Dict[str, Any]:
        """POST /mobile/camera — upload a local image file (by path) for analysis."""
        with open(file_path, "rb") as f:
            data = f.read()
        name = file_path.replace("\\", "/").rsplit("/", 1)[-1] or "image.jpg"
        return self.upload_camera_photo(name, data)

    def fetch_image_bytes(self, image_url: str) -> bytes:
        """GET an image served by the backend (e.g. /static/…) and return its bytes."""
        try:
            r = self._client.get(f"{self.base_url}{image_url}")
            r.raise_for_status()
            return r.content
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"Image download failed: {e}") from e

    # ── knowledge / memory (Pansophy) ───────────────────────────────────────
    def list_memories(self, category: Optional[str] = None) -> list:
        """GET /memories → list of memory dicts."""
        path = "/memories" + (f"?category={category}" if category else "")
        data = self._get_json(path)
        return data if isinstance(data, list) else []

    def knowledge_graph(self, limit: int = 500) -> Dict[str, Any]:
        """GET /knowledge/graph → {entities, relationships}."""
        return self._get_json(f"/knowledge/graph?limit={limit}")

    # ── shared settings (cross-platform) ────────────────────────────────────
    def get_shared_settings(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """GET /settings → settings dict.

        `timeout` bounds the wait (used at startup to hydrate local settings
        without hanging the window for the full 180s default when the backend
        is offline)."""
        try:
            r = self._client.get(
                f"{self.base_url}/settings",
                timeout=timeout,  # per-request override (None → client default)
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"GET /settings failed: {e}") from e

    def update_shared_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """POST /settings → merged settings dict."""
        return self._post_json("/settings", patch)

    # ── models (Settings) ───────────────────────────────────────────────────
    def list_models(self) -> Dict[str, Any]:
        """GET /models → LM Studio model info."""
        return self._get_json("/models")

    def update_model_config(self, fast_model: str = "", main_model: str = "",
                            lm_studio_url: str = "") -> Dict[str, Any]:
        """POST /models/config → set fast/main models + LM Studio endpoint.

        Only non-empty fields are sent (the backend ignores falsy values, so an
        empty field would otherwise never clear a previously-set value).
        """
        payload: Dict[str, Any] = {}
        if fast_model.strip():
            payload["fast_model"] = fast_model.strip()
        if main_model.strip():
            payload["main_model"] = main_model.strip()
        if lm_studio_url.strip():
            payload["lm_studio_url"] = lm_studio_url.strip()
        return self._post_json("/models/config", payload)

    # ── voice (Settings) ────────────────────────────────────────────────────
    def list_piper_voices(self) -> list:
        """GET /voice/piper-voices → discovered Piper voices + active voice."""
        data = self._get_json("/voice/piper-voices")
        return data.get("voices") or []

    def select_piper_voice(self, voice_id: str) -> Dict[str, Any]:
        """POST /voice/piper/select → set the active Piper voice."""
        return self._post_json("/voice/piper/select", {"profile_name": voice_id})

    # ── code execution ──────────────────────────────────────────────────────
    def execute_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """POST /code/execute."""
        return self._post_json("/code/execute", {"code": code, "language": language})

    # ── helpers ─────────────────────────────────────────────────────────────
    def _get_json(self, path: str) -> Dict[str, Any]:
        try:
            r = self._client.get(f"{self.base_url}{path}")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"GET {path} failed: {e}") from e

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            r = self._client.post(f"{self.base_url}{path}", json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise BackendConnectionError(f"POST {path} failed: {e}") from e

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ArenaBackendClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def parse_stream_event(line: str) -> Dict[str, Any]:
    """Parse one WebSocket text frame (already JSON-decoded at the call site).

    Provided here as a documented helper for the WebSocket streaming path used by
    the voice feature in later phases.
    """
    return json.loads(line)
