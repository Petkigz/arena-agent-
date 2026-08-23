import pytest
from app.utils.hardware_monitor import HardwareMonitor
from app.utils.notifier import SystemNotifier
from app.scheduler import ProactiveScheduler
from app.agents.multi_agent import MultiAgentTeam

def test_hardware_monitor_stats():
    stats = HardwareMonitor.get_hardware_stats()
    assert "cpu_percent" in stats
    assert "ram_used_gb" in stats
    assert "ram_total_gb" in stats

def test_system_notifier():
    res = SystemNotifier.send_notification("Test Title", "Test Notification Message")
    assert "title" in res

def test_proactive_scheduler():
    jobs = ProactiveScheduler.list_jobs()
    assert isinstance(jobs, list)

def test_multi_agent_team_with_real_completion_contract(monkeypatch):
    monkeypatch.setattr(
        "app.llm.llm_client.generate_chat_completion",
        lambda **kwargs: {
            "success": True,
            "model": "test-model",
            "choices": [{"message": {"content": "Verified collaborative output"}}],
        },
    )
    res = MultiAgentTeam.run_collaborative_workflow("Test multi-agent collaboration")
    assert res["success"] is True
    assert "final_verified_solution" in res
