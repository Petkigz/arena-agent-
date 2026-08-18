from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier


def test_goal_verifier_does_not_manufacture_running_observation():
    """
    P0 Fix Verification:
    Verify that GoalVerifier does NOT manufacture an observation with 'running'
    in result.observed_state["observations"] when observations_map is empty.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("What is Python?")

    res = GoalVerifier.verify_goal_achievement(
        goal_rep,
        executed_actions=[],
        assistant_reply="Python is a high-level programming language."
    )

    assert res.verified_success is True
    obs = res.observed_state.get("observations", {})

    # MUST NOT manufacture "desktop_os.status = running" or similar
    assert obs.get("desktop_os.status") != "running"
    assert obs.get("conversation.status") != "running"
    assert obs == {"status": "unknown", "evidence_source": "not_observed"}
