from unittest.mock import patch

from app.cognition.capability_factory import CapabilityFactory


def test_capability_factory_never_registers_unverified_generation():
    unverified = {
        "success": False,
        "verified": False,
        "available": False,
        "error": "provider offline",
        "file_path": None,
    }
    with patch(
        "app.agents.self_evolving_agent.SelfEvolvingAgent.synthesize_and_hotload_tool",
        return_value=unverified,
    ):
        result = CapabilityFactory.synthesize_capability(
            capability_name="System Log Analyzer",
            description="Parses system logs and filters warnings",
        )

    assert result["success"] is False
    assert result["verified"] is False
    assert result["file_path"] is None
