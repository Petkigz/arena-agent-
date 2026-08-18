from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier, ConditionStatus
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_replanner import GoalReplanner


def test_tristate_condition_status_evaluation():
    """
    P0 Fix Verification:
    Verify that evaluate_condition_status_against_world_model distinguishes:
    1. SATISFIED (photoshop.status == 'running')
    2. FAILED (photoshop.status == 'crashed')
    3. UNKNOWN (no observation recorded yet)
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

    # 1. SATISFIED
    satisfied_obs = {"photoshop.status": {"value": "running", "observation_type": "direct", "source": "os_process_probe", "confidence": 1.0}}
    st_sat = GoalVerifier.evaluate_condition_status_against_world_model(
        "app_process_running = true", goal_rep, satisfied_obs, {}, ["Launched app"], "Done.", []
    )
    assert st_sat == ConditionStatus.SATISFIED

    # 2. FAILED
    failed_obs = {"photoshop.status": {"value": "crashed", "observation_type": "direct", "source": "os_process_probe", "confidence": 1.0}}
    st_fail = GoalVerifier.evaluate_condition_status_against_world_model(
        "app_process_running = true", goal_rep, failed_obs, {}, ["Launched app"], "Done.", []
    )
    assert st_fail == ConditionStatus.FAILED

    # 3. UNKNOWN (missing perception evidence)
    unknown_obs = {}
    st_unk = GoalVerifier.evaluate_condition_status_against_world_model(
        "app_process_running = true", goal_rep, unknown_obs, {}, ["Launched app"], "Done.", []
    )
    assert st_unk == ConditionStatus.UNKNOWN


def test_verify_goal_achievement_returns_is_unknown_when_evidence_missing():
    """
    Verify GoalVerifier returns is_unknown = True
    when conditions are UNKNOWN (missing perception evidence) without explicit failure.
    """
    tracker = GoalTracker("Open Photoshop")
    tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
    tracker.transition(GoalLifecycleState.PLANNED, "Planned")
    tracker.transition(GoalLifecycleState.EXECUTING, "Executing")

    from app.cognition.goal_interpreter import SemanticGoalInterpreter
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    # Missing perception evidence
    empty_obs_state = {
        "entities": [],
        "observations": {}
    }

    res = GoalVerifier.verify_goal_achievement(
        goal_rep, ["Launched Photoshop"], "Photoshop launch command sent.",
        tracker=tracker, observed_state=empty_obs_state
    )

    assert res.verified_success is False
    assert res.is_unknown is True
    assert len(res.unknown_conditions) >= 1


def test_replanner_triggers_reobservation_probe_when_is_unknown_is_true():
    """
    Verify GoalReplanner generates a diagnostic re-observation probe strategy when
    failed_result.is_unknown is True rather than immediately eliminating the capability.
    """
    tracker = GoalTracker("Open Photoshop")
    tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
    tracker.transition(GoalLifecycleState.PLANNED, "Planned")
    tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
    tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
    tracker.transition(GoalLifecycleState.FAILED, "Failed")

    from app.cognition.goal_interpreter import SemanticGoalInterpreter
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    from app.cognition.goal_verifier import GoalVerificationResult
    unknown_verify_result = GoalVerificationResult(
        goal_id=tracker.goal_id,
        verified_success=False,
        is_unknown=True,
        final_state=GoalLifecycleState.FAILED,
        verification_reason="Missing perception evidence",
        failed_action_type="open_application",
        unknown_conditions=["unobserved_condition: app_process_running = true"]
    )

    replan_proposal = GoalReplanner.execute_reassessment_and_replan(
        user_text="Open Photoshop",
        goal_rep=goal_rep,
        failed_result=unknown_verify_result,
        tracker=tracker
    )

    assert replan_proposal is not None
    assert replan_proposal.action_type == "investigate"
