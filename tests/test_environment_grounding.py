import pytest
from app.cognition.environment_grounding import EnvironmentGroundingEngine

def test_environment_grounding_probe():
    env = EnvironmentGroundingEngine.probe_complete_environment()
    assert "host_os" in env
    assert env["cpu_threads"] > 0
    assert env["installed_apps_count"] >= 0

def test_environment_grounding_prompt():
    prompt = EnvironmentGroundingEngine.generate_grounding_prompt_context()
    assert "[ENVIRONMENTAL SELF-GROUNDING" in prompt
    assert "Hardware Profile:" in prompt
