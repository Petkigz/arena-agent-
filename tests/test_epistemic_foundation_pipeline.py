from unittest.mock import patch
from app.cognition.goal_interpreter import SemanticGoalRepresentation, SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier, ConditionStatus
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_replanner import GoalReplanner
from app.cognition.perception import ObservationCollector
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.world_model import WorldModel, Observation, ObservationType
from app.cognition.action_proposal import ActionProposal


def test_epistemic_evidence_pipeline_tri_branch_outcomes(tmp_path):
    """
    P0 Epistemic Foundation Invariant Test:
    Verifies the complete epistemic evidence pipeline:
    World -> ObservationCollector -> Evidence Object -> GoalVerifier ->
    TRUE (ACHIEVED) | FALSE (REPLAN) | UNKNOWN (OBSERVE)
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    # 1. Branch TRUE -> ACHIEVED: Process probe observes 'running' in OS
    wm.observe(Observation(
        id="obs_true",
        subject="photoshop",
        predicate="status",
        value="running",
        source="os_process_probe",
        confidence=1.0,
        observation_type=ObservationType.DIRECT.value
    ))

    obs_state_true = {
        "entities": [{"name": "photoshop", "status": "running"}],
        "observations": {
            "photoshop.status": {
                "value": "running",
                "source": "os_process_probe",
                "confidence": 1.0,
                "observation_type": "direct"
            }
        }
    }

    res_true = GoalVerifier.verify_goal_achievement(
        goal_rep, ["Launched Photoshop"], "Photoshop launched.", observed_state=obs_state_true
    )

    assert res_true.verified_success is True
    assert res_true.final_state == GoalLifecycleState.ACHIEVED

    # 2. Branch FALSE -> REPLAN: Process probe observes explicit crash/failure
    wm.observe(Observation(
        id="obs_false",
        subject="photoshop",
        predicate="status",
        value="crashed",
        source="os_process_probe",
        confidence=1.0,
        observation_type=ObservationType.DIRECT.value
    ))

    obs_state_false = {
        "entities": [{"name": "photoshop", "status": "crashed"}],
        "observations": {
            "photoshop.status": {
                "value": "crashed",
                "source": "os_process_probe",
                "confidence": 1.0,
                "observation_type": "direct"
            }
        }
    }

    tracker_fail = GoalTracker("Open Photoshop")
    tracker_fail.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
    tracker_fail.transition(GoalLifecycleState.PLANNED, "Planned")
    tracker_fail.transition(GoalLifecycleState.EXECUTING, "Executing")

    res_false = GoalVerifier.verify_goal_achievement(
        goal_rep, ["Launched Photoshop"], "Error: Photoshop process crashed on launch.",
        tracker=tracker_fail, observed_state=obs_state_false
    )

    assert res_false.verified_success is False
    assert res_false.is_unknown is False
    assert res_false.final_state == GoalLifecycleState.FAILED

    replan_proposal_fail = GoalReplanner.execute_reassessment_and_replan(
        user_text="Open Photoshop",
        goal_rep=goal_rep,
        failed_result=res_false,
        tracker=tracker_fail
    )

    # Hard failure triggers Plan B strategy instance replanning
    assert replan_proposal_fail is not None

    # 3. Branch UNKNOWN -> OBSERVE: Perception evidence missing (zero hard errors)
    tracker_unk = GoalTracker("Open Photoshop")
    tracker_unk.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
    tracker_unk.transition(GoalLifecycleState.PLANNED, "Planned")
    tracker_unk.transition(GoalLifecycleState.EXECUTING, "Executing")

    obs_state_unk = {
        "entities": [],
        "observations": {}
    }

    res_unk = GoalVerifier.verify_goal_achievement(
        goal_rep, ["Launched Photoshop"], "Command sent.",
        tracker=tracker_unk, observed_state=obs_state_unk
    )

    assert res_unk.verified_success is False
    assert res_unk.is_unknown is True

    replan_proposal_unk = GoalReplanner.execute_reassessment_and_replan(
        user_text="Open Photoshop",
        goal_rep=goal_rep,
        failed_result=res_unk,
        tracker=tracker_unk
    )

    # Missing evidence triggers diagnostic re-observation probe ('investigate') to OBSERVE again
    assert replan_proposal_unk is not None
    assert replan_proposal_unk.action_type == "investigate"
