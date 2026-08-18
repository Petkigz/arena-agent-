from unittest.mock import patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal


def test_execute_proposal_investigate_runs_real_diagnostic_probes():
    """
    P1 Fix Verification:
    Verify that executing an investigate proposal runs real diagnostic probe tools
    (filesystem log/file search & hardware telemetry) and returns actual evidence.
    """
    proposal = ActionProposal(
        action_type="investigate",
        payload={"query": "app crash log"}
    )

    mock_matched = [{"file_name": "crash.log", "file_path": "/var/log/crash.log"}]
    mock_hw = {"cpu_used_percent": 12.5, "ram_used_percent": 45.0}

    with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=mock_matched) as mock_search, \
         patch("app.utils.hardware_monitor.HardwareMonitor.get_hardware_stats", return_value=mock_hw) as mock_hw_stats:

        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Investigate app crash")

        assert res["success"] is True
        mock_search.assert_called_once_with("app crash log", max_results=3)
        assert mock_hw_stats.called

        executed = res["executed_actions"][0]
        # Real probe findings MUST be present in action log
        assert "/var/log/crash.log" in executed
        assert "CPU 12.5%" in executed
        assert "RAM 45.0%" in executed
