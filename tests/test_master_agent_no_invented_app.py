"""P0 bottleneck #9: MasterAgent must never invent a default application.
The old 'explorer' fallback turned an ambiguous request into a silently
WRONG action — and because explorer is actually installed, the wrong
request succeeded. Ambiguity is a clarification request, not a guess."""
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.execution_result import ExecutionStatus

OFFLINE = {"success": False, "error": "Model provider is unavailable", "choices": []}


def _prop(payload=None):
    return SimpleNamespace(action_type="open_application", payload=payload or {},
                           proposal_id="prop_test")


def _run(user_text, payload=None, launch_result=None):
    with patch("app.agents.master_agent.llm_client.generate_chat_completion",
               return_value=OFFLINE):
        if launch_result is not None:
            with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app",
                       return_value=launch_result) as mock_launch:
                res = MasterAgentOrchestrator.execute_proposal(_prop(payload), user_text)
                return res, mock_launch
        with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app",
                   side_effect=AssertionError("no app should be launched")) as mock_launch:
            res = MasterAgentOrchestrator.execute_proposal(_prop(payload), user_text)
            return res, mock_launch


def test_ambiguous_open_asks_instead_of_guessing():
    res, mock_launch = _run("can you open")
    assert res.execution_status is ExecutionStatus.FAILED
    assert mock_launch.call_count == 0            # NOTHING was launched
    launch = res.outputs["launch_res"]
    assert launch["success"] is False
    assert launch["clarification_required"] is True
    assert "which application" in res.assistant_reply.lower()
    assert "explorer" not in str(res.outputs).lower()


def test_bare_open_the_app_asks_instead_of_guessing():
    res, mock_launch = _run("open the app")
    assert res.execution_status is ExecutionStatus.FAILED
    assert mock_launch.call_count == 0


def test_named_app_still_launches():
    res, mock_launch = _run("open chrome",
                            launch_result={"success": True, "app_name": "chrome"})
    assert res.execution_status is ExecutionStatus.SUCCEEDED
    mock_launch.assert_called_once_with("chrome")


def test_payload_app_name_takes_precedence():
    res, mock_launch = _run("open that thing again",
                            payload={"app_name": "vscode"},
                            launch_result={"success": True, "app_name": "vscode"})
    assert res.execution_status is ExecutionStatus.SUCCEEDED
    mock_launch.assert_called_once_with("vscode")


def test_unknown_named_app_fails_honestly():
    res, _ = _run("open frobnicator9000",
                  launch_result={"success": False, "error": "No installed application matches"})
    assert res.execution_status is ExecutionStatus.FAILED
    assert "frobnicator9000" in res.executed_actions[0]
