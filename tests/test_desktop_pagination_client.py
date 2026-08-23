"""Desktop collection calls preserve paging and filter parameters."""

import httpx

from desktop.backend_client import ArenaBackendClient


def test_desktop_collection_page_urls():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url))
        return httpx.Response(200, json={"projects": [], "files": [], "memories": []})

    client = ArenaBackendClient(base_url="http://localhost:8000")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    client.list_projects(offset=50, limit=25, status="on hold")
    client.list_memories_page(offset=20, limit=10, category="user preference")
    client.list_workspace_files_page(offset=5, limit=15, extension=".pdf")
    client.close()

    assert paths == [
        "http://localhost:8000/projects?offset=50&limit=25&status=on%20hold",
        "http://localhost:8000/memories/page?offset=20&limit=10&category=user%20preference",
        "http://localhost:8000/tools/workspace-files/page?offset=5&limit=15&extension=.pdf",
    ]
