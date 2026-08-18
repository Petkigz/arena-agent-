from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerificationResult
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_replanner import GoalReplanner


def test_replanner_uses_structured_failed_action_type_to_exclude_strategy():
    """
    Verify GoalReplanner uses failed_result.failed_action_type (e.g. 'open_application')
    to filter out the failed strategy and select a non-failing alternative strategy.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    tracker = GoalTracker("Open Photoshop")

    failed_result = GoalVerificationResult(
        goal_id=tracker.goal_id,
        verified_success=False,
        final_state=GoalLifecycleState.FAILED,
        verification_reason="Process crashed on launch",
        failed_action_type="open_application",
        failed_conditions=["process_crashed = true"]
    )

    replan_proposal = GoalReplanner.execute_reassessment_and_replan(
        user_text="Open Photoshop",
        goal_rep=goal_rep,
        failed_result=failed_result,
        tracker=tracker
    )

    # Replan proposal MUST NOT be open_application (which was failed_action_type)
    assert replan_proposal is not None
    assert replan_proposal.action_type != "open_application"
    assert tracker.current_state == GoalLifecycleState.REPLAN
