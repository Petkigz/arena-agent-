from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier, GoalConditionType, ConditionStatus


def test_classify_condition_type_distinguishes_response_from_environment():
    """
    P1 Fix Verification:
    Verify classify_condition_type correctly routes:
    1. Conversational / knowledge_query goals -> GoalConditionType.RESPONSE
    2. Operational action_intent goals -> GoalConditionType.ENVIRONMENT / ARTIFACT
    """
    # Conversational goal
    ct_resp = GoalVerifier.classify_condition_type(
        "response_delivered = true",
        primary_intent_type="knowledge_query",
        target_domain="conversation"
    )
    assert ct_resp == GoalConditionType.RESPONSE

    # Operational action goal
    ct_env = GoalVerifier.classify_condition_type(
        "response_delivered = true",
        primary_intent_type="action_intent",
        target_domain="desktop_os"
    )
    assert ct_env == GoalConditionType.ENVIRONMENT

    ct_proc = GoalVerifier.classify_condition_type(
        "app_process_running = true",
        primary_intent_type="action_intent",
        target_domain="desktop_os"
    )
    assert ct_proc == GoalConditionType.ENVIRONMENT


def test_action_intent_goal_cannot_be_satisfied_by_text_response_alone():
    """
    Verify that an action_intent goal requiring environmental process state (app_process_running = true)
    is NOT satisfied merely because assistant_reply text exists.
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

    # Empty WorldModel observations (no direct process probe evidence)
    empty_obs_map = {}

    st = GoalVerifier.evaluate_condition_status_against_world_model(
        succ_cond="app_process_running = true",
        goal_rep=goal_rep,
        observations_map=empty_obs_map,
        verified_entity_states={},
        executed_actions=["Launched Photoshop"],
        reply_clean="I opened Photoshop for you.",
        failed_conditions=[]
    )

    # Text response alone CANNOT satisfy environmental process condition!
    assert st != ConditionStatus.SATISFIED
    assert st == ConditionStatus.UNKNOWN


def test_knowledge_query_goal_is_satisfied_by_response_delivery():
    """
    Verify that a knowledge_query goal requiring response delivery
    IS satisfied by conversational language output.
    """
    goal_rep = SemanticGoalRepresentation(
        user_query="Explain TCP/IP",
        primary_intent_type="knowledge_query",
        target_domain="conversation",
        goal="Explain TCP/IP networking",
        desired_outcome="Conversational explanation delivered",
        entities=["TCP/IP"],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=["response_delivered = true"],
        failure_conditions=[],
        required_capabilities=["llm.generate"],
        risk_factors=[]
    )

    st = GoalVerifier.evaluate_condition_status_against_world_model(
        succ_cond="response_delivered = true",
        goal_rep=goal_rep,
        observations_map={},
        verified_entity_states={},
        executed_actions=[],
        reply_clean="TCP/IP is the foundational networking suite...",
        failed_conditions=[]
    )

    assert st == ConditionStatus.SATISFIED
