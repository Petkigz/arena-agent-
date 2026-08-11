import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_read_root_json():
    # Non-HTML request should return JSON
    response = client.get("/", headers={"accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["app_name"] == "Local Personal Assistant"

def test_read_root_html():
    # HTML request should return HTML index page
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Visual Dashboard" in response.text

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["app_name"] == "Local Personal Assistant"

def test_chat_endpoint():
    # Tests chat completion endpoint (works both when LM Studio is online or offline)
    response = client.post("/chat", json={
        "messages": [{"role": "user", "content": "How's the weather?"}],
        "complexity": "fast"
    })
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    content = data["choices"][0]["message"]["content"]
    assert isinstance(content, str) and len(content) > 0

def test_tasks_endpoints():
    # Create task
    task_payload = {
        "title": "Build UI Component",
        "goal": "Build dashboard with dark mode support",
        "priority": "high",
        "plan": ["Setup templates", "Integrate tailwind"]
    }
    create_resp = client.post("/tasks", json=task_payload)
    assert create_resp.status_code == 201
    task = create_resp.json()
    assert task["id"] is not None
    assert task["status"] == "queued"
    
    # Retrieve task
    get_resp = client.get(f"/tasks/{task['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Build UI Component"
    
    # Update task
    update_resp = client.patch(f"/tasks/{task['id']}", json={
        "status": "completed",
        "checkpoint": "Completed successfully!"
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "completed"
    
    # Delete task
    delete_resp = client.delete(f"/tasks/{task['id']}")
    assert delete_resp.status_code == 200
    
    # Confirm deletion
    get_deleted = client.get(f"/tasks/{task['id']}")
    assert get_deleted.status_code == 404

def test_policy_evaluation():
    response = client.post("/policies/evaluate", json={
        "action_type": "send_email",
        "details": {"to": "someone@example.com", "body": "Hello"}
    })
    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is False
    assert "requires explicit user approval" in data["reason"]

def test_manual_and_rules():
    manual_resp = client.get("/manual")
    assert manual_resp.status_code == 200
    assert "User Operating Manual" in manual_resp.json()["content"]
    
    rules_resp = client.get("/rules")
    assert rules_resp.status_code == 200
    assert "Rules & Permission Boundaries" in rules_resp.json()["content"]

def test_update_manual_and_rules():
    # Save original content
    orig_m = client.get("/manual").json()["content"]
    orig_r = client.get("/rules").json()["content"]

    try:
        m_update = client.post("/manual", json={"content": "# User Operating Manual\nTest manual content."})
        assert m_update.status_code == 200
        assert "updated successfully" in m_update.json()["message"]
        
        m_get = client.get("/manual")
        assert "Test manual content." in m_get.json()["content"]

        r_update = client.post("/rules", json={"content": "# Rules & Permission Boundaries\nTest rules content."})
        assert r_update.status_code == 200
        assert "updated successfully" in r_update.json()["message"]

        r_get = client.get("/rules")
        assert "Test rules content." in r_get.json()["content"]
    finally:
        # Restore original content
        client.post("/manual", json={"content": orig_m})
        client.post("/rules", json={"content": orig_r})

def test_models_endpoints():
    # GET models
    get_resp = client.get("/models")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "lm_studio_online" in data
    assert "configured_fast_model" in data
    assert "configured_main_model" in data

    # POST config models
    post_resp = client.post("/models/config", json={
        "fast_model": "qwen2.5-3b-instruct",
        "main_model": "qwen2.5-coder-7b-instruct"
    })
    assert post_resp.status_code == 200
    assert post_resp.json()["configured_fast_model"] == "qwen2.5-3b-instruct"
    assert post_resp.json()["configured_main_model"] == "qwen2.5-coder-7b-instruct"
