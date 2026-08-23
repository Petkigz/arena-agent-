"""Desktop authentication is local and reaches every protected API call."""

import httpx

from desktop.backend_client import ArenaBackendClient
from desktop.settings import DEFAULTS


def test_api_key_header_is_applied_rotated_and_removed_locally():
    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.headers.get("X-API-Key"))
        return httpx.Response(200, json={"status": "healthy"})

    client = ArenaBackendClient(api_key="first-secret")
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"X-API-Key": client.api_key},
    )
    client.health()
    client.set_api_key("rotated-secret")
    client.health()
    client.set_api_key("")
    client.health()
    client.close()

    assert observed == ["first-secret", "rotated-secret", None]
    assert DEFAULTS["api_key"] == ""
