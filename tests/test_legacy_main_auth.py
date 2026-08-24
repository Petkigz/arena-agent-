from fastapi.testclient import TestClient
from app.main import app

def test_legacy_main_requires_configured_key(monkeypatch):
 monkeypatch.setenv('ARENA_API_KEY','owner-key');client=TestClient(app)
 assert client.get('/api/status').status_code==403
 assert client.get('/api/status',headers={'X-API-Key':'owner-key'}).status_code==200
 monkeypatch.delenv('ARENA_API_KEY')

def test_legacy_main_fail_closed_when_enforced_without_key(monkeypatch):
 monkeypatch.delenv('ARENA_API_KEY',raising=False);monkeypatch.setenv('ARENA_ENFORCE_AUTH','1');client=TestClient(app)
 assert client.get('/api/status').status_code==503
 monkeypatch.delenv('ARENA_ENFORCE_AUTH')
