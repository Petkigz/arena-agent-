from unittest.mock import patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal


def test_execute_proposal_phone_command_executes_call():
    """
    P1 Fix Verification:
    Verify that proposal phone_command with call query executes make_phone_call
    rather than get_battery_status.
    """
    proposal = ActionProposal(
        action_type="phone_command",
        payload={"query": "call 555-1234", "phone_number": "555-1234"}
    )

    call_res = {"success": True, "message": "Initiated phone call to 5551234"}

    with patch("app.tools.android_adb_controller.AndroidADBController.make_phone_call", return_value=call_res) as mock_call, \
         patch("app.tools.android_adb_controller.AndroidADBController.get_battery_status") as mock_battery:

        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Call John")

        assert res["success"] is True
        mock_call.assert_called_once_with("555-1234")
        mock_battery.assert_not_called()
        assert "Initiated phone call to 555-1234" in res["executed_actions"][0]


def test_execute_proposal_phone_command_executes_sms():
    """
    Verify proposal phone_command with sms text query executes send_sms.
    """
    proposal = ActionProposal(
        action_type="phone_command",
        payload={"query": "send sms Hello", "phone_number": "555-8888", "sms_body": "Hello"}
    )

    sms_res = {"success": True, "message": "Sent SMS to 5558888"}

    with patch("app.tools.android_adb_controller.AndroidADBController.send_sms", return_value=sms_res) as mock_sms, \
         patch("app.tools.android_adb_controller.AndroidADBController.get_battery_status") as mock_battery:

        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Send SMS to John")

        assert res["success"] is True
        mock_sms.assert_called_once_with("555-8888", "Hello")
        mock_battery.assert_not_called()
        assert "Sent SMS text to 555-8888" in res["executed_actions"][0]
