import pytest
from app.tools.daily_briefing import DailyBriefingEngine
from app.tools.workflow_engine import WorkflowEngine

def test_daily_briefing_generation():
    res = DailyBriefingEngine.generate_briefing(
        custom_topics=["Cybersecurity Threat Intelligence", "Local AI Agents"],
        generate_audio=False
    )
    assert res.get("success") is True
    assert "GOOD MORNING EXECUTIVE BRIEFING" in res.get("briefing_text", "")
    assert res.get("file_path") is not None

def test_workflow_engine_execution():
    steps = [
        {
            "action": "log_memory",
            "params": {"content": "Test workflow memory entry", "category": "test"}
        },
        {
            "action": "daily_briefing",
            "params": {"generate_audio": False}
        }
    ]
    res = WorkflowEngine.execute_workflow("Test Routine", steps)
    assert res.get("workflow_name") == "Test Routine"
    assert res.get("overall_success") is True
    assert len(res.get("step_results", [])) == 2
