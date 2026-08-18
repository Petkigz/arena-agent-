from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_lifecycle import GoalLifecycleState


def test_action_log_alone_without_world_model_observation_fails_verification():
    """
    P0 Fix Verification:
    Verify that an action execution log alone ('Launched Photoshop executable')
    does NOT satisfy 'app_process_running = true' without a WorldModel observation.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    res = GoalVerifier.verify_goal_achievement(
        goal_rep,
        executed_actions=["Launched Photoshop executable"],
        assistant_reply="Command executed.",
        observed_state={"entities": [], "observations": {}}  # No WorldModel observation
    )

    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED


def test_world_model_observation_satisfies_process_running_verification():
    """
    Verify that a real WorldModel observation ('photoshop.status' = 'running')
    satisfies 'app_process_running = true'.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    observed_world_state = {
        "entities": [{"name": "photoshop.exe", "type": "process", "status": "running"}],
        "observations": {"photoshop.status": "running"}
    }

    res = GoalVerifier.verify_goal_achievement(
        goal_rep,
        executed_actions=["Launched Photoshop executable"],
        assistant_reply="Photoshop launched.",
        observed_state=observed_world_state
    )

    assert res.verified_success is True
    assert res.final_state == GoalLifecycleState.ACHIEVED
    assert "app_process_running = true" in res.met_conditions
