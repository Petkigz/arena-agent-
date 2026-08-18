from unittest.mock import patch
from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel, ObservationType


def test_process_probe_records_running_or_not_running_only(tmp_path):
    """
    P0 Fix Verification:
    Verify that os_process_probe strictly establishes process.status = 'running' or 'not_running'
    as direct environmental observations, and NEVER labels 'launched' as a direct observation.
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )

    exec_res = ExecutionResult(
        proposal_id=proposal.proposal_id,
        action_type=proposal.action_type,
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=["Launched application 'Photoshop'"],
        assistant_reply="I launched Photoshop.",
        execution_facts=[{
            "subject": "photoshop",
            "predicate": "launch_command",
            "value": "succeeded",
            "source": "system_app_inventory"
        }]
    )

    with patch("psutil.process_iter", return_value=[]):
        ObservationCollector.collect_and_ingest_observations(proposal, exec_res, world_model=wm)

        status_obs = wm.latest_observation("photoshop", "status")
        assert status_obs is not None
        assert status_obs.value == "not_running"
        assert status_obs.observation_type == ObservationType.DIRECT.value
        assert status_obs.source == "os_process_probe"
        assert status_obs.value != "launched"
