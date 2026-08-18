import pytest
from app.cognition.goal_lifecycle import GoalTracker, GoalLifecycleState, InvalidStateTransitionError


def test_valid_goal_lifecycle_state_transitions():
    """
    CREATED -> UNDERSTOOD -> PLANNED -> EXECUTING -> VERIFYING -> ACHIEVED
    """
    tracker = GoalTracker(user_query="Open Photoshop")
    assert tracker.current_state == GoalLifecycleState.CREATED

    tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed query")
    assert tracker.current_state == GoalLifecycleState.UNDERSTOOD

    tracker.transition(GoalLifecycleState.PLANNED, "Generated candidates")
    assert tracker.current_state == GoalLifecycleState.PLANNED

    tracker.transition(GoalLifecycleState.EXECUTING, "Executing launcher")
    assert tracker.current_state == GoalLifecycleState.EXECUTING

    tracker.transition(GoalLifecycleState.VERIFYING, "Verifying environment")
    assert tracker.current_state == GoalLifecycleState.VERIFYING

    tracker.transition(GoalLifecycleState.ACHIEVED, "Verified app running")
    assert tracker.current_state == GoalLifecycleState.ACHIEVED

    assert len(tracker.history) == 5


def test_invalid_goal_lifecycle_state_transition_raises_error():
    """
    Transitioning directly from CREATED to ACHIEVED is invalid and MUST raise InvalidStateTransitionError.
    """
    tracker = GoalTracker(user_query="Open Photoshop")

    with pytest.raises(InvalidStateTransitionError):
        tracker.transition(GoalLifecycleState.ACHIEVED, "Bypassed verification")
