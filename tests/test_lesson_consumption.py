"""Regression guard: structured lessons must actually influence replanning.

This closes the "write half exists, read half is unwired" gap. The lesson store's
read API (lesson_influence, corrective_suggestion) must flow through
GoalReplanner → ActionPlanner → CounterfactualSimulator so that a recorded past
failure changes a future decision — not just sit in storage.
"""

from unittest.mock import MagicMock, patch

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerificationResult
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_replanner import GoalReplanner
from app.cognition.structured_lessons import LessonStore


def _failed_result(tracker):
    return GoalVerificationResult(
        goal_id=tracker.goal_id,
        verified_success=False,
        final_state=GoalLifecycleState.FAILED,
        verification_reason="Process crashed on launch",
        failed_action_type="open_application",
        failed_conditions=["process_crashed = true"],
    )


def test_replanner_passes_lesson_store_to_planner(tmp_path):
    """GoalReplanner must forward lesson_store into ActionPlanner (the wiring gap)."""
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    tracker = GoalTracker("Open Photoshop")
    tracker.current_state = GoalLifecycleState.FAILED
    failed_result = _failed_result(tracker)
    lesson_store = LessonStore(db_path=str(tmp_path / "lessons.db"))

    with patch("app.cognition.goal_replanner.ActionPlanner.plan_and_evaluate_action") as mock_plan:
        mock_plan.return_value = MagicMock()  # we only assert the call args
        GoalReplanner.execute_reassessment_and_replan(
            user_text="Open Photoshop",
            goal_rep=goal_rep,
            failed_result=failed_result,
            tracker=tracker,
            lesson_store=lesson_store,
        )
        # The lesson_store must be forwarded (not dropped) into the planner.
        _, kwargs = mock_plan.call_args
        assert kwargs.get("lesson_store") is lesson_store


def test_replanner_forwards_lesson_store_on_unknown_verification(tmp_path):
    """The UNKNOWN-verification branch must also forward lesson_store."""
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    tracker = GoalTracker("Open Photoshop")
    tracker.current_state = GoalLifecycleState.VERIFYING

    unknown_result = GoalVerificationResult(
        goal_id=tracker.goal_id,
        verified_success=False,
        final_state=GoalLifecycleState.VERIFYING,
        verification_reason="unknown",
        is_unknown=True,
        unknown_conditions=["app_process_running"],
        failed_conditions=[],
    )
    lesson_store = LessonStore(db_path=str(tmp_path / "lessons.db"))

    with patch("app.cognition.goal_replanner.ActionPlanner.plan_and_evaluate_action") as mock_plan:
        mock_plan.return_value = None
        GoalReplanner.execute_reassessment_and_replan(
            user_text="Open Photoshop",
            goal_rep=goal_rep,
            failed_result=unknown_result,
            tracker=tracker,
            lesson_store=lesson_store,
        )
        _, kwargs = mock_plan.call_args
        assert kwargs.get("lesson_store") is lesson_store


def test_runtime_replan_consumes_lessons_end_to_end(tmp_path):
    """A recorded failure lowers the utility of the same action on the next
    simulation — proving the lesson store influences future strategy selection."""
    lesson_store = LessonStore(db_path=str(tmp_path / "lessons.db"))
    lesson_store.extract_lesson(
        task_type="action_intent",
        action_type="open_application",
        final_state="failed",
        verified_success=False,
        failed_conditions=["process_crashed = true"],
        reply_text="Photoshop process crashed on startup",
    )

    from app.cognition.counterfactual_simulator import CounterfactualSimulator
    candidates = [
        {"name": "open app", "action_type": "open_application", "payload": {}},
        {"name": "web search", "action_type": "web_search", "payload": {}},
    ]
    result = CounterfactualSimulator.simulate_competing_branches(
        "Open Photoshop", candidates, goal_type="action_intent", lesson_store=lesson_store,
    )
    by_action = {b.hypothetical_action: b for b in result.competing_branches}
    # The previously-failed action must be penalized relative to the clean one.
    assert by_action["open_application"].history_adjustment < 1.0
    assert by_action["web_search"].history_adjustment >= 1.0
    assert by_action["open_application"].utility_score < by_action["web_search"].utility_score
