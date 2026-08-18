from unittest.mock import patch, MagicMock
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel


def test_execution_status_enum_values():
    """
    Verify ExecutionStatus enum contains all required first-class states.
    """
    assert ExecutionStatus.NOT_ATTEMPTED.value == "not_attempted"
    assert ExecutionStatus.RUNNING.value == "running"
    assert ExecutionStatus.SUCCEEDED.value == "succeeded"
    assert ExecutionStatus.FAILED.value == "failed"
    assert ExecutionStatus.PARTIAL.value == "partial"
    assert ExecutionStatus.UNKNOWN.value == "unknown"


def test_execute_proposal_returns_first_class_execution_result_object(tmp_path):
    """
    P1 Fix Verification:
    Verify MasterAgentOrchestrator.execute_proposal returns a first-class ExecutionResult object
    carrying proposal_id, action_type, execution_status, executed_actions, outputs, and facts.
    """
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"},
        proposal_id="prop_test_123"
    )

    with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app", return_value={"success": True, "app_name": "photoshop"}):
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Open Photoshop")

        assert isinstance(res, ExecutionResult)
        assert res.proposal_id == "prop_test_123"
        assert res.action_type == "open_application"
        assert res.execution_status == ExecutionStatus.SUCCEEDED
        assert res.attempted is True
        assert res.success is True
        assert "Photoshop" in res.executed_actions[0]
        assert len(res.execution_facts) >= 1

        # Dict compatibility
        assert res["success"] is True
        assert res.get("proposal_id") == "prop_test_123"


def test_execute_proposal_failed_status_mapping():
    """
    Verify MasterAgentOrchestrator.execute_proposal returns ExecutionStatus.FAILED on error.
    """
    proposal = ActionProposal(
        action_type="unsupported_quantum_magic",
        payload={},
        proposal_id="prop_fail_456"
    )

    res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="Do quantum magic")

    assert isinstance(res, ExecutionResult)
    assert res.proposal_id == "prop_fail_456"
    assert res.execution_status == ExecutionStatus.FAILED
    assert res.success is False
    assert res.error is not None


def test_observation_collector_populates_execution_result_observations(tmp_path):
    """
    Verify ObservationCollector ingests observations and attaches them to execution_result.observations.
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "report.pdf"},
        proposal_id="prop_fs_789"
    )

    exec_res = ExecutionResult(
        proposal_id="prop_fs_789",
        action_type="search_files",
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=["Found file report.pdf"],
        execution_facts=[{
            "subject": "filesystem",
            "predicate": "file_path",
            "value": "/home/user/report.pdf",
            "source": "universal_filesystem"
        }],
        outputs={"matched_files": [{"file_name": "report.pdf", "file_path": "/home/user/report.pdf"}]}
    )

    obs_list = ObservationCollector.collect_and_ingest_observations(proposal, exec_res, world_model=wm)

    assert len(obs_list) >= 1
    assert len(exec_res.observations) >= 1
    assert exec_res.observations[0].value == "/home/user/report.pdf"
