import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["app_name"] == "Local Personal Assistant"

def test_chat_endpoint_simulation():
    response = client.post("/chat", json={
        "messages": [{"role": "user", "content": "How's the weather?"}],
        "complexity": "fast"
    })
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert "Simulated Response" in data["choices"][0]["message"]["content"]

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
