import pytest
from unittest.mock import patch
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

    # POST config models (use the models actually run on the target machine)
    post_resp = client.post("/models/config", json={
        "fast_model": "qwen2.5-3b-instruct",
        "main_model": "qwen2.5-9b-instruct"
    })
    assert post_resp.status_code == 200
    assert post_resp.json()["configured_fast_model"] == "qwen2.5-3b-instruct"
    assert post_resp.json()["configured_main_model"] == "qwen2.5-9b-instruct"

def test_daily_briefing_api():
    resp = client.post("/tools/daily-briefing", json={"generate_audio": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "GOOD MORNING EXECUTIVE BRIEFING" in data["briefing_text"]

def test_workflow_execute_api():
    payload = {
        "workflow_name": "API Test Flow",
        "steps": [
            {"action": "log_memory", "params": {"content": "API test workflow step", "category": "test"}}
        ]
    }
    resp = client.post("/tools/workflow-execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_name"] == "API Test Flow"
    assert data["overall_success"] is True

@patch(
    "app.llm.llm_client.generate_chat_completion",
    return_value={
        "success": True,
        "model": "test-model",
        "choices": [{"message": {"content": "Verified generated test content"}}],
    },
)
def test_human_and_opsec_and_pentest_apis(_model):
    # Human assimilate API
    resp_h = client.post("/human/assimilate", json={
        "user_text": "I am working on cybersecurity and AI",
        "assistant_response": "Acknowledged.",
        "feedback": "Great"
    })
    assert resp_h.status_code == 200
    assert resp_h.json()["success"] is True

    # Universal media learn API
    resp_m = client.post("/tools/universal-media-learn", json={
        "target_url_or_path": "https://example.com"
    })
    assert resp_m.status_code == 200
    assert resp_m.json()["success"] is True

    # OpSec audit API
    resp_o1 = client.post("/opsec/audit-footprint", json={
        "query_identifier": "testuser@example.com"
    })
    assert resp_o1.status_code == 200
    assert resp_o1.json()["success"] is True

    # OpSec erasure API
    resp_o2 = client.post("/opsec/generate-erasure", json={
        "target_service_name": "TestBroker",
        "user_identifier": "testuser@example.com"
    })
    assert resp_o2.status_code == 200
    assert resp_o2.json()["success"] is True

    # Pentest RoE API
    resp_p1 = client.post("/specialists/security/draft-roe", json={
        "client_company_name": "SecureCorp",
        "authorized_ip_ranges": ["192.168.1.1"]
    })
    assert resp_p1.status_code == 200
    assert resp_p1.json()["success"] is True

    # Pentest Report API
    resp_p2 = client.post("/specialists/security/pentest-report", json={
        "client_company_name": "SecureCorp",
        "target_scope": ["192.168.1.1"],
        "vulnerabilities_found": []
    })
    assert resp_p2.status_code == 200
    assert resp_p2.json()["success"] is True

@patch(
    "app.llm.llm_client.generate_chat_completion",
    return_value={
        "success": True,
        "model": "test-model",
        "choices": [{"message": {"content": "Verified skill analysis"}}],
    },
)
def test_sandbox_and_skills_apis(_model):
    # 1. Create Sandbox
    sb_resp = client.post("/sandbox/create", json={"sandbox_name": "API_Sandbox"})
    assert sb_resp.status_code == 200
    sb_data = sb_resp.json()
    assert sb_data["success"] is True
    sandbox_id = sb_data["sandbox_id"]

    # 2. Run Command in Sandbox
    run_resp = client.post("/sandbox/run", json={
        "sandbox_id": sandbox_id,
        "command": "echo Hello API Sandbox"
    })
    assert run_resp.status_code == 200
    assert run_resp.json()["success"] is True

    # 3. Destroy Sandbox
    destroy_resp = client.post("/sandbox/destroy", json={"sandbox_id": sandbox_id})
    assert destroy_resp.status_code == 200
    assert destroy_resp.json()["success"] is True

    # 4. Teach Skill API
    teach_resp = client.post("/skills/teach", json={
        "skill_name": "API Teachable Skill Test",
        "category": "testing",
        "instructions": "Step 1: Run API test.",
        "sample_commands": "echo Testing {target}"
    })
    assert teach_resp.status_code == 200
    assert teach_resp.json()["success"] is True

    # 5. List Skills API
    list_resp = client.get("/skills/list")
    assert list_resp.status_code == 200
    assert "skills" in list_resp.json()

    # 6. Execute Skill API
    exec_resp = client.post("/skills/execute", json={
        "skill_name": "API Teachable Skill Test",
        "target_parameter": "target.local",
        "run_in_sandbox": True
    })
    assert exec_resp.status_code == 200
    assert exec_resp.json()["success"] is True

def test_system_apps_apis():
    resp_get = client.get("/system/apps")
    assert resp_get.status_code == 200
    assert "total_apps_count" in resp_get.json()

    resp_scan = client.post("/system/apps/scan")
    assert resp_scan.status_code == 200
    assert resp_scan.json()["success"] is True

    resp_launch = client.post("/system/apps/launch", json={"app_query": "echo"})
    assert resp_launch.status_code == 200
    assert "success" in resp_launch.json()
