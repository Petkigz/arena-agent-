from unittest.mock import patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel


def test_search_files_distinguishes_execution_success_from_result_found(tmp_path):
    """
    Verify that when UniversalFilesystem returns zero matches:
    1. execution_success = True (tool command ran cleanly)
    2. result_found = False (carried explicitly in raw_output)
    3. ObservationCollector records file_path = "not_found" in WorldModel
    4. GoalVerifier evaluates goal_verified = False
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "non_existent_file.xyz"}
    )

    with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
        res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="find non_existent_file.xyz")

        # Command execution succeeded without error
        assert res["success"] is True

        # Result found is explicitly False
        raw_output = res.get("raw_output", {})
        assert raw_output.get("result_found") is False
        assert raw_output.get("matched_files") == []

        # Perception Layer ingests file_path = "not_found"
        obs_list = ObservationCollector.collect_and_ingest_observations(proposal, res, world_model=wm)
        assert any(o.value == "not_found" for o in obs_list)

        # Goal Verifier evaluates goal as NOT achieved
        goal_rep = SemanticGoalInterpreter.interpret_goal("find non_existent_file.xyz")
        obs_state = {
            "entities": [],
            "observations": {"filesystem.file_path": "not_found"},
            "executed_actions": res["executed_actions"],
            "assistant_reply": res["assistant_reply"]
        }
        verify_res = GoalVerifier.verify_goal_achievement(
            goal_rep, res["executed_actions"], res["assistant_reply"], observed_state=obs_state
        )
        assert verify_res.verified_success is False
