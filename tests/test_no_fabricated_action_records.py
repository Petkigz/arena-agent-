from unittest.mock import patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal


def test_failed_screen_capture_returns_execution_failure():
    """
    P1 Fix Verification:
    Verify that when ScreenCaptureTool returns success=False, execute_proposal returns
    success=False and records 'Failed to capture' rather than fabricating a success action record.
    """
    proposal = ActionProposal(action_type="screen_capture", payload={})

    failed_cap = {"success": False, "error": "Display server unavailable"}

    with patch("app.tools.screen_capture.ScreenCaptureTool.capture_screen", return_value=failed_cap):
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Take screenshot")

        assert res["success"] is False
        assert len(res["executed_actions"]) > 0
        assert "Failed to capture" in res["executed_actions"][0]


def test_successful_screen_capture_returns_execution_success():
    """
    Verify that when ScreenCaptureTool returns success=True, execute_proposal records
    successful action log and returns success=True.
    """
    proposal = ActionProposal(action_type="screen_capture", payload={})

    successful_cap = {"success": True, "file_name": "screen.png", "file_path": "/tmp/screen.png"}

    with patch("app.tools.screen_capture.ScreenCaptureTool.capture_screen", return_value=successful_cap):
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Take screenshot")

        assert res["success"] is True
        assert len(res["executed_actions"]) > 0
        assert "Captured active desktop screen window" in res["executed_actions"][0]
