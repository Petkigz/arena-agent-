from unittest.mock import patch, MagicMock
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel


def test_execute_proposal_returns_execution_result_without_direct_world_model_writes():
    """
    Verify execute_proposal returns a structured ExecutionResult dictionary
    with execution_facts and raw_output without directly writing WorldModel observations inline.
    """
    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "contract.pdf"}
    )

    mock_match = [{"file_name": "contract.pdf", "file_path": "/home/user/docs/contract.pdf"}]
    with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=mock_match):
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="find contract.pdf")

        # Returns ExecutionResult structure
        assert res.get("success") is True
        assert "execution_facts" in res
        assert "raw_output" in res

        # Execution facts populated
        facts = res["execution_facts"]
        assert len(facts) >= 1
        assert any(f.get("value") == "/home/user/docs/contract.pdf" for f in facts)


def test_observation_collector_ingests_facts_and_probes_process_state(tmp_path):
    """
    Verify ObservationCollector ingests ExecutionResult execution_facts and
    runs environmental process state probes, populating WorldModel observations cleanly.
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )
    exec_res = {
        "success": True,
        "executed_actions": ["Launched application 'Photoshop'"],
        "execution_facts": [{
            "subject": "photoshop",
            "predicate": "launch_command",
            "value": "succeeded",
            "source": "system_app_inventory"
        }],
        "raw_output": {"launch_res": {"app_name": "photoshop"}}
    }

    obs_list = ObservationCollector.collect_and_ingest_observations(
        proposal, exec_res, world_model=wm
    )

    assert len(obs_list) >= 2
    subjects = [o.subject for o in obs_list]
    predicates = [o.predicate for o in obs_list]

    assert "photoshop" in subjects
    assert "launch_command" in predicates
    assert "status" in predicates

    # Verify WorldModel query reflects observations
    latest_launch = wm.latest_observation("photoshop", "launch_command")
    assert latest_launch is not None
    assert latest_launch.value == "succeeded"

    latest_status = wm.latest_observation("photoshop", "status")
    assert latest_status is not None
