from app.cognition.runtime import CognitiveRuntime
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier


def test_llm_hallucinated_text_does_not_manufacture_running_status(tmp_path):
    """
    P0 Fix Verification:
    Verify that an LLM assistant reply stating 'Sure, the application has been launched'
    does NOT manufacture status='running' during world state capture when WorldModel
    contains no process observation.
    """
    path = str(tmp_path / "arena.db")
    runtime = CognitiveRuntime(db_path=path)

    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    obs_state = runtime.capture_observed_world_state(
        executed_actions=[],
        assistant_reply="Sure, Photoshop has been launched and opened successfully on your screen.",
        goal_rep=goal_rep
    )

    entities = obs_state["entities"]
    assert len(entities) > 0
    ps_entity = next(e for e in entities if e["name"] == "Photoshop")

    # MUST remain 'unknown' - LLM text MUST NOT fabricate 'running'
    assert ps_entity["status"] == "unknown"


def test_llm_hallucinated_text_fails_goal_verification_without_observation(tmp_path):
    """
    P0 Fix Verification:
    Verify that goal verification FAILS when LLM text claims success but no real
    WorldModel process observation or execution evidence exists.
    """
    path = str(tmp_path / "arena.db")
    runtime = CognitiveRuntime(db_path=path)

    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    obs_state = runtime.capture_observed_world_state(
        executed_actions=[],
        assistant_reply="Sure, Photoshop is running active.",
        goal_rep=goal_rep
    )

    res = GoalVerifier.verify_goal_achievement(
        goal_rep,
        executed_actions=[],
        assistant_reply="Sure, Photoshop is running active.",
        observed_state=obs_state
    )

    # Goal verification MUST fail because entity status is 'unknown', not 'running'
    assert res.verified_success is False
