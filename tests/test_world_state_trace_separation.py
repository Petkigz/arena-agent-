from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier


def test_observed_state_separates_world_state_execution_trace_and_response():
    """
    P1 Fix Verification:
    Verify that GoalVerifier.verify_goal_achievement returns an observed_state dictionary
    that distinctly separates pure environmental evidence ('world_state') from execution
    history ('execution_trace') and language output ('assistant_response'), preventing
    accidental evidence contamination.
    """
    goal_rep = SemanticGoalRepresentation(
        user_query="Open Photoshop",
        primary_intent_type="action_intent",
        target_domain="desktop_os",
        goal="Launch Photoshop",
        desired_outcome="Photoshop running",
        entities=["photoshop"],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=["app_process_running = true"],
        failure_conditions=[],
        required_capabilities=["os.launch_app"],
        risk_factors=[]
    )

    observed_input = {
        "entities": [{"name": "photoshop", "status": "running"}],
        "observations": {"photoshop.status": "running"}
    }

    res = GoalVerifier.verify_goal_achievement(
        goal_rep=goal_rep,
        executed_actions=["Launched Photoshop"],
        assistant_reply="I launched Photoshop for you.",
        observed_state=observed_input
    )

    assert res.verified_success is True
    obs_payload = res.observed_state

    # Sections MUST be distinctly structured
    assert "world_state" in obs_payload
    assert "execution_trace" in obs_payload
    assert "assistant_response" in obs_payload

    # Pure environmental evidence in world_state
    world_state = obs_payload["world_state"]
    assert "entities" in world_state
    assert "observations" in world_state
    assert world_state["observations"].get("photoshop.status") == "running"

    # Execution history in execution_trace
    exec_trace = obs_payload["execution_trace"]
    assert exec_trace["executed_actions"] == ["Launched Photoshop"]

    # Language output in assistant_response
    resp = obs_payload["assistant_response"]
    assert resp["text"] == "I launched Photoshop for you."
