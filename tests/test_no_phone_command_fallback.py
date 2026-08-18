from unittest.mock import patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal


def test_unrecognized_phone_command_does_not_fallback_to_battery_status():
    """
    P0 Fix Verification:
    Verify that an unrecognized or unsupported phone_command query (e.g. 'do something random on phone')
    does NOT execute battery status query and instead returns a structured failure with
    unsupported_capability = 'unsupported_phone_command'.
    """
    proposal = ActionProposal(
        action_type="phone_command",
        payload={"query": "do something random on phone"}
    )

    with patch("app.tools.android_adb_controller.AndroidADBController.get_battery_status") as mock_battery:
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="do something random on phone")

        # Battery status function MUST NOT be called!
        assert mock_battery.call_count == 0

        # Must return structured failure
        assert res["success"] is False
        assert res.get("unsupported_capability") == "unsupported_phone_command"
        assert "unsupported phone command" in res.get("assistant_reply", "").lower() or "failed" in res.get("assistant_reply", "").lower()


def test_explicit_battery_query_still_executes_battery_status():
    """
    Verify that an explicit battery status query ('check phone battery level')
    still correctly triggers get_battery_status.
    """
    proposal = ActionProposal(
        action_type="phone_command",
        payload={"query": "check phone battery level"}
    )

    mock_battery_res = {"success": True, "message": "Battery level: 85%"}
    with patch("app.tools.android_adb_controller.AndroidADBController.get_battery_status", return_value=mock_battery_res) as mock_battery:
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="check phone battery level")

        assert mock_battery.call_count == 1
        assert res["success"] is True
        assert any("battery" in act.lower() for act in res["executed_actions"])
