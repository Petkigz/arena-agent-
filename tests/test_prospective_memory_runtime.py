"""Contracts for explicit turn-based prospective memory in the runtime."""

from unittest.mock import patch

from app.cognition.runtime import CognitiveRuntime
from app.cognition.trace import CognitiveTrace
from app.tools.calendar_service import CalendarService


def test_runtime_turn_reminder_handler_returns_durable_owner_visible_result(tmp_path, monkeypatch):
    monkeypatch.setattr(CalendarService, "STORE_PATH", tmp_path / "calendar.json")
    runtime = object.__new__(CognitiveRuntime)

    # The handler contract is about routing and truthful response metadata;
    # avoid writing this unit test's trace into the shared application DB.
    with patch.object(CognitiveTrace, "finalize"):
        result = runtime._handle_turn_reminder_request(
            user_text="Remind me in three turns to review the deployment",
            request={"turns": 3, "title": "review the deployment"},
            complexity="fast",
            session_id="session-a",
        )

    assert result["success"] is True
    assert result["goal_verified"] is True
    assert result["reminder"]["session_id"] == "session-a"
    assert result["reminder"]["delivery_condition"] == {
        "type": "conversation_turn",
        "session_id": "session-a",
        "due_turn": 3,
    }
    assert result["reminder"]["status"] == "pending"
    assert result["epistemic_presentation"]["evidence_state"] == "verified"
    assert result["grounding"]["status"] == "supported"
    assert result["executed_actions"] == ["Scheduled turn reminder: review the deployment"]
