from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.world_model import Observation, ObservationType


def test_self_reported_tool_observation_does_not_satisfy_process_running():
    """
    P0 Fix Verification:
    Verify that a self_reported observation (observation_type = 'self_reported' from tool_output)
    is rejected as insufficient evidence for environmental conditions (process_running = true).
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

    self_reported_obs_map = {
        "photoshop.launch_command": {
            "value": "running",
            "source": "system_app_inventory",
            "confidence": 0.5,
            "observation_type": ObservationType.SELF_REPORTED.value
        }
    }

    res = GoalVerifier.evaluate_condition_against_world_model(
        succ_cond="app_process_running = true",
        goal_rep=goal_rep,
        observations_map=self_reported_obs_map,
        verified_entity_states={"photoshop": "launched"},
        executed_actions=["Tool executed launch command"],
        reply_clean="Done.",
        failed_conditions=[]
    )

    # Self-reported tool execution claim MUST NOT satisfy process_running
    assert res is False


def test_direct_perception_probe_satisfies_process_running():
    """
    Verify that a direct perception observation (observation_type = 'direct' from os_process_probe)
    satisfies process_running.
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

    direct_obs_map = {
        "photoshop.status": {
            "value": "running",
            "source": "os_process_probe",
            "confidence": 1.0,
            "observation_type": ObservationType.DIRECT.value
        }
    }

    res = GoalVerifier.evaluate_condition_against_world_model(
        succ_cond="app_process_running = true",
        goal_rep=goal_rep,
        observations_map=direct_obs_map,
        verified_entity_states={"photoshop": "running"},
        executed_actions=["Launched Photoshop"],
        reply_clean="Done.",
        failed_conditions=[]
    )

    assert res is True
