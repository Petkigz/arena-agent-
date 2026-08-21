"""HTTP + WebSocket client for the Arena backend (used by the native desktop app).

Kept GUI-free and dependency-light so it is unit-testable without a display or a
running server. The desktop window (PySide6) consumes this class.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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

    # ── capabilities / self-report ──────────────────────────────────────────
    def capabilities(self) -> Dict[str, Any]:
        """POST /chat with a self-report request is overkill; instead read the
        runtime's measured scorecard via a lightweight dedicated call below.
        (The scorecard lives in the runtime; expose it via the app if needed.)
        """
        raise NotImplementedError

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
