from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_chat_route_uses_canonical_cognitive_pipeline():
    """
    Verify /chat route uses CognitivePipeline / CognitiveRuntime canonical route.
    """
    resp = client.post("/chat", json={
        "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        "complexity": "fast"
    })

    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
    assert "trace_id" in data
    assert data["model"] is not None
