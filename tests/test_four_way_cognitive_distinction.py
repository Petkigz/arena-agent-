from unittest.mock import patch
from app.cognition.runtime import CognitiveRuntime
from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel, Observation
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_lifecycle import GoalLifecycleState


def test_four_way_cognitive_distinction_pipeline(tmp_path):
    """
    P0 Closed-Loop Invariant Test:
    Verifies the fundamental cognitive distinction:
    1. 'I tried it' (ExecutionResult.attempted == True)
    2. 'The tool said it worked' (ExecutionResult.execution_status == ExecutionStatus.SUCCEEDED)
    3. 'I observed that it worked' (WorldModel Observation value == 'running')
    4. 'The goal is proven achieved' (GoalVerifier verified_success == True & ACHIEVED)
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )

    # Stage 1 & 2: Tool Execution produces ExecutionResult
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
        }],
        outputs={"launch_res": {"app_name": "photoshop"}}
    )

    # 1. 'I tried it'
    assert exec_res.attempted is True
    # 2. 'The tool said it worked'
    assert exec_res.execution_status == ExecutionStatus.SUCCEEDED
    assert exec_res.success is True

    # Stage 3: ObservationCollector ingests observations into WorldModel
    with patch("psutil.process_iter", return_value=[]):
        # Case A: Tool command succeeded, but process probe fails -> observed status is 'not_running', NOT 'running'
        obs_a = ObservationCollector.collect_and_ingest_observations(proposal, exec_res, world_model=wm)
        status_obs_a = wm.latest_observation("photoshop", "status")
        assert status_obs_a is not None
        assert status_obs_a.value == "not_running"

        # Verification fails because 'running' was NOT observed!
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
        obs_state_a = {
            "entities": [{"name": "photoshop", "status": "not_running"}],
            "observations": {"photoshop.status": "not_running"},
            "executed_actions": exec_res.executed_actions,
            "assistant_reply": exec_res.assistant_reply
        }
        verify_a = GoalVerifier.verify_goal_achievement(
            goal_rep, exec_res.executed_actions, exec_res.assistant_reply, observed_state=obs_state_a
        )
        # 4. 'The goal is proven achieved' -> FALSE when process_running is not observed
        assert verify_a.verified_success is False
        # No authoritative observation → conditions UNKNOWN (waiting for evidence)
        assert verify_a.final_state in (GoalLifecycleState.FAILED, GoalLifecycleState.WAITING_FOR_EVIDENCE)

    # Case B: Process probe observes 'running' in OS
    wm.observe(Observation(id="obs_running", subject="photoshop", predicate="status", value="running", source="os_process_probe"))

    # 3. 'I observed that it worked'
    status_obs_b = wm.latest_observation("photoshop", "status")
    assert status_obs_b is not None
    assert status_obs_b.value == "running"

    obs_state_b = {
        "entities": [{"name": "photoshop", "status": "running",
                       "source": "os_process_probe", "observation_type": "direct", "confidence": 1.0}],
        "observations": {"photoshop.status": {
            "value": "running", "source": "os_process_probe",
            "confidence": 1.0, "observation_type": "direct"
        }},
        "executed_actions": exec_res.executed_actions,
        "assistant_reply": exec_res.assistant_reply
    }
    verify_b = GoalVerifier.verify_goal_achievement(
        goal_rep, exec_res.executed_actions, exec_res.assistant_reply, observed_state=obs_state_b
    )

    # 4. 'The goal is proven achieved' -> TRUE when subject-bound 'running' observation exists
    assert verify_b.verified_success is True
    assert verify_b.final_state == GoalLifecycleState.ACHIEVED
