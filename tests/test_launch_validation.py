from app.cognition.goal_interpreter import SemanticGoalRepresentation
"""Launch validation + GoalVerifier honesty: three stacked live bugs.

1. launch_any_app accepted entire sentences as app names (bidirectional
   substring match: 'now in contrrol panel open user accounts' contained
   'control panel' so it "matched").
2. The OS error 'The system cannot find the file' was printed by Windows
   but the GoalVerifier never saw it — it checked only the friendly action
   description.
3. The GoalVerifier said VerifiedSuccess=True on a failed launch; the
   self-reflection then claimed 'successfully executed without issues'.
"""
from app.tools.app_inventory import SystemAppInventory
from app.cognition.goal_verifier import GoalVerifier


def test_launch_refuses_sentence_as_app_name():
    result = SystemAppInventory.launch_any_app("now in contrrol panel open user accounts")
    assert result["success"] is False
    assert result.get("refused") is True
    assert "sentence" in result["error"].lower()


def test_launch_refuses_how_many_tabs_question():
    result = SystemAppInventory.launch_any_app("how many tabs are open on this desktop")
    assert result["success"] is False
    assert result.get("refused") is True


def test_short_app_name_still_works():
    """The fix must not break legitimate short app queries."""
    result = SystemAppInventory.launch_any_app("control panel")
    # On this Linux sandbox, there's no control panel — but the point is
    # it's NOT refused for being a sentence; it proceeds to matching.
    assert not (result.get("refused") and "sentence" in str(result.get("error", "")).lower())


def test_verifier_detects_cannot_find_file():
    """The exact live error must fail verification."""
    goal = SemanticGoalRepresentation(
        user_query="open user accounts",
        primary_intent_type="action_intent", target_domain="desktop_os",
        goal="open user accounts", desired_outcome="User Accounts window open",
        entities=["user accounts"], constraints=[], assumptions=[], unknowns=[],
        preconditions=[],
        success_conditions=["app_state = running"], failure_conditions=["launch_failed"],
        required_capabilities=[], risk_factors=[], recommended_candidates=[],
    )
    result = GoalVerifier.verify_goal_achievement(
        goal,
        executed_actions=["Attempting to launch application 'now in contrrol panel open user accounts'"],
        assistant_reply="The system cannot find the file now in contrrol panel open user accounts.",
    )
    assert result.verified_success is False, (
        "The verifier must NOT claim success when Windows says 'cannot find the file'")


def test_verifier_fails_on_tool_reporting_false():
    goal = SemanticGoalRepresentation(
        user_query="open app",
        primary_intent_type="action_intent", target_domain="desktop_os",
        goal="open app", desired_outcome="app open",
        entities=["app"], constraints=[], assumptions=[], unknowns=[],
        preconditions=[],
        success_conditions=["app_state = running"], failure_conditions=[],
        required_capabilities=[], risk_factors=[], recommended_candidates=[],
    )
    result = GoalVerifier.verify_goal_achievement(
        goal,
        executed_actions=["Launch attempt with result: {'success': False, 'refused': True}"],
        assistant_reply="Could not launch the application.",
    )
    assert result.verified_success is False


def test_verifier_still_passes_on_real_success():
    goal = SemanticGoalRepresentation(
        user_query="open control panel",
        primary_intent_type="action_intent", target_domain="desktop_os",
        goal="open control panel", desired_outcome="Control Panel open",
        entities=["control panel"], constraints=[], assumptions=[], unknowns=[],
        preconditions=[],
        success_conditions=["response_delivered = true"], failure_conditions=["launch_failed"],
        required_capabilities=[], risk_factors=[], recommended_candidates=[],
    )
    result = GoalVerifier.verify_goal_achievement(
        goal,
        executed_actions=["Successfully launched application 'Control Panel'"],
        assistant_reply="Control Panel is now open.",
    )
    assert result.verified_success is True
