from unittest.mock import patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal


def test_execute_proposal_uses_payload_search_query_authoritatively():
    """
    Verify search_files capability uses proposal.payload["query"] rather than re-parsing user_text.
    """
    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "project_backup"}
    )

    with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[{"file_name": "project_backup.zip", "file_path": "/home/user/project_backup.zip"}]) as mock_search:
        res = MasterAgentOrchestrator.execute_proposal(
            proposal=proposal,
            user_text="Find my documents and music"
        )

        assert res["success"] is True
        # Search query executed MUST be 'project_backup' from proposal payload, NOT 'Find my documents and music'
        # max_results=6 (limit 5 + 1 for truncation detection). root_dir/scope
        # pass through from the payload (D7 live 2026-09-01: they used to be
        # silently dropped — a planner-chosen scope was ignored).
        mock_search.assert_called_once_with(
            "project_backup", root_dir=None, scope=None, max_results=6)
        assert "project_backup.zip" in res["executed_actions"][0]


def test_execute_proposal_uses_payload_app_name_authoritatively():
    """
    Verify open_application capability uses proposal.payload["app_name"] rather than re-parsing user_text.
    """
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "notepad"}
    )

    with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app", return_value={"success": True, "app_name": "notepad"}) as mock_launch:
        res = MasterAgentOrchestrator.execute_proposal(
            proposal=proposal,
            user_text="Open Firefox browser"
        )

        assert res["success"] is True
        # App launched MUST be 'notepad' from proposal payload, NOT 'Firefox browser' from user_text
        mock_launch.assert_called_once_with("notepad")
        assert "Notepad" in res["executed_actions"][0]
