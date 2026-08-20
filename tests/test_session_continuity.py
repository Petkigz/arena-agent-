"""
Phase 1D: Session Continuity Tests.

Verifies that cognitive state persists across restarts:
- Beliefs, outcomes, and lessons survive simulated restarts
- session_start() recalculates decayed beliefs
- System remembers what it learned after kill/restart
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.cognition.runtime import CognitiveRuntime
from app.cognition.beliefs import Evidence, Belief


def test_session_start_recalculates_beliefs(tmp_path):
    """session_start() recalculates all beliefs with current time decay."""
    db_path = str(tmp_path / "session.db")
    runtime = CognitiveRuntime(db_path=db_path)

    # Add some beliefs
    runtime.beliefs.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
    runtime.beliefs.ingest("firefox", "status", "active", source="os_process_probe", observation_type="direct", confidence=0.8)

    # Simulate restart
    runtime2 = CognitiveRuntime(db_path=db_path)
    summary = runtime2.session_start()

    assert "beliefs_changed" in summary
    assert "stale_beliefs" in summary
    assert "total_outcomes" in summary
    assert "total_lessons" in summary


def test_beliefs_persist_across_restart(tmp_path):
    """Beliefs survive a simulated kill/restart cycle."""
    db_path = str(tmp_path / "session.db")

    # Session 1: create beliefs
    runtime1 = CognitiveRuntime(db_path=db_path)
    runtime1.beliefs.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.95)

    # Session 2: beliefs should still be there
    runtime2 = CognitiveRuntime(db_path=db_path)
    result = runtime2.beliefs.inspect("chrome", "status")
    assert result is not None
    assert result.belief_value == "running"


def test_outcomes_persist_across_restart(tmp_path):
    """Strategy outcomes survive restart."""
    db_path = str(tmp_path / "session.db")

    runtime1 = CognitiveRuntime(db_path=db_path)
    runtime1.outcomes.record_outcome("action_intent", "open_application", True, 100.0, 0.1)
    runtime1.outcomes.record_outcome("action_intent", "open_application", False, 200.0, 0.5)

    runtime2 = CognitiveRuntime(db_path=db_path)
    assert runtime2.outcomes.total_recorded() == 2

    score = runtime2.outcomes.score_strategy("action_intent", "open_application")
    assert score is not None
    assert score.total_attempts == 2


def test_lessons_persist_across_restart(tmp_path):
    """Structured lessons survive restart."""
    db_path = str(tmp_path / "session.db")

    runtime1 = CognitiveRuntime(db_path=db_path)
    runtime1.lessons.extract_lesson(
        "action_intent", "open_application", "failed", False,
        ["app_process_running = true"], "Process crashed", "Open Photoshop"
    )

    runtime2 = CognitiveRuntime(db_path=db_path)
    assert runtime2.lessons.total_lessons() == 1

    info = runtime2.lessons.what_went_wrong("action_intent", "open_application")
    assert info is not None
    assert info["failure_type"] == "process_crashed"


def test_system_remembers_after_restart(tmp_path):
    """
    Completion criteria: Kill and restart the system; it remembers what it learned.
    Verifies that beliefs + outcomes + lessons all persist and influence decisions.
    """
    db_path = str(tmp_path / "session.db")

    # Session 1: learn from experience
    runtime1 = CognitiveRuntime(db_path=db_path)
    runtime1.beliefs.ingest("server", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
    runtime1.outcomes.record_outcome("search_intent", "search_files", False, 150.0, 0.8)
    runtime1.outcomes.record_outcome("search_intent", "search_files", False, 160.0, 0.7)
    runtime1.outcomes.record_outcome("search_intent", "search_files", False, 140.0, 0.9)
    runtime1.lessons.extract_lesson(
        "search_intent", "search_files", "failed", False,
        ["file_path_identified = true"], "File not found", "Find report"
    )

    # Session 2: verify memory
    runtime2 = CognitiveRuntime(db_path=db_path)
    runtime2.session_start()

    # Beliefs survived
    belief = runtime2.beliefs.inspect("server", "status")
    assert belief is not None
    assert belief.belief_value == "running"

    # Outcomes survived and influence selection
    factor = runtime2.outcomes.adjustment_factor("search_intent", "search_files")
    assert factor < 1.0  # Penalized due to 3 failures

    # Lessons survived and can answer "why did this fail?"
    info = runtime2.lessons.what_went_wrong("search_intent", "search_files")
    assert info is not None
    assert info["times_failed"] == 1  # 1 lesson recorded (with failure_type)
    assert info["corrective_action"] != ""
