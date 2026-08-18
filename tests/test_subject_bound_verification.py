from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier


def test_unrelated_process_running_does_not_satisfy_target_entity_condition():
    """
    P1 Fix Verification:
    Verify that an unrelated process observation (e.g. process 'chrome' = running)
    does NOT satisfy a goal condition requiring a specific target entity (e.g. 'photoshop')
    to be running.
    """
    goal_rep = SemanticGoalRepresentation(
        user_query="Open Photoshop",
        primary_intent_type="action_intent",
        target_domain="desktop_os",
        goal="Launch Photoshop",
        desired_outcome="Photoshop process running",
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

    unrelated_obs_map = {
        "chrome.status": "running"
    }
    unrelated_entity_states = {
        "chrome": "running"
    }

    res = GoalVerifier.evaluate_condition_against_world_model(
        succ_cond="app_process_running = true",
        goal_rep=goal_rep,
        observations_map=unrelated_obs_map,
        verified_entity_states=unrelated_entity_states,
        executed_actions=["Launched Chrome"],
        reply_clean="Done.",
        failed_conditions=[]
    )

    # Must be False because chrome is running, NOT photoshop!
    assert res is False


def test_matching_subject_bound_observation_satisfies_condition():
    """
    Verify that a matching subject-bound observation (photoshop.status = running)
    correctly satisfies the condition.
    """
    goal_rep = SemanticGoalRepresentation(
        user_query="Open Photoshop",
        primary_intent_type="action_intent",
        target_domain="desktop_os",
        goal="Launch Photoshop",
        desired_outcome="Photoshop process running",
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

    matching_obs_map = {
        "photoshop.status": "running"
    }
    matching_entity_states = {
        "photoshop": "running"
    }

    res = GoalVerifier.evaluate_condition_against_world_model(
        succ_cond="app_process_running = true",
        goal_rep=goal_rep,
        observations_map=matching_obs_map,
        verified_entity_states=matching_entity_states,
        executed_actions=["Launched Photoshop"],
        reply_clean="Done.",
        failed_conditions=[]
    )

    assert res is True
