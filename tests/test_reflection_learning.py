import pytest
from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import MemoryLearner, Lesson
from app.cognition.goal_verifier import GoalVerificationResult
from app.cognition.goal_lifecycle import GoalLifecycleState

def test_reflection_and_memory_learning(tmp_path):
    store = MemoryStore(tmp_path / "test_reflection.db")
    learner = MemoryLearner(store)

    # 1. Process outcome reflection (legacy path with outcome_summary)
    record = learner.process_outcome_reflection(
        task_title="Open Firefox Browser",
        goal="Launch browser for search",
        outcome_summary="Firefox launched successfully.",
        surprisal=0.0
    )

    assert record.kind == "lesson"
    assert "Open Firefox Browser" in record.content
    assert record.importance >= 0.5
    # Legacy path marks as unverified
    assert "[UNVERIFIED]" in record.content


def test_reflection_with_verified_outcome(tmp_path):
    store = MemoryStore(tmp_path / "test_verified.db")
    learner = MemoryLearner(store)

    # Create a GoalVerificationResult
    verify_res = GoalVerificationResult(
        goal_id="test_goal",
        verified_success=True,
        final_state=GoalLifecycleState.ACHIEVED,
        verification_reason="All conditions met",
        met_conditions=["browser_running", "page_loaded"],
        failed_conditions=[]
    )

    # Process with verified outcome
    record = learner.process_outcome_reflection(
        task_title="Open Firefox Browser",
        goal="Launch browser for search",
        verification_result=verify_res,
        surprisal=0.0
    )

    assert record.kind == "lesson"
    assert "Open Firefox Browser" in record.content
    assert record.importance >= 0.5
    # Verified path includes structured verification data
    assert "Verified: True" in record.content
    assert "State: achieved" in record.content
    assert "Met: 2 conditions" in record.content
    # Should NOT be marked as unverified
    assert "[UNVERIFIED]" not in record.content


def test_reflection_requires_verification_or_summary(tmp_path):
    store = MemoryStore(tmp_path / "test_required.db")
    learner = MemoryLearner(store)

    # Should raise if neither verification_result nor outcome_summary provided
    with pytest.raises(ValueError, match="Either verification_result or outcome_summary must be provided"):
        learner.process_outcome_reflection(
            task_title="Test Task",
            goal="Test goal",
            surprisal=0.0
        )
