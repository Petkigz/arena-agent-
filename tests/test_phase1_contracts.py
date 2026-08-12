"""Phase 1 contract tests.

These tests intentionally exercise only the cognitive foundation and do not
start the FastAPI application, browser, desktop automation, or LLM services.
"""

from app.cognition.blackboard import Blackboard
from app.cognition.cognitive_state import CognitiveState
from app.cognition.event_bus import EventBus
from app.cognition.events import CognitiveEvent
from app.cognition.session import CognitiveSession
from app.runtime.resource_manager import ResourceManager


def test_blackboard_preserves_metadata():
    board = Blackboard()
    board.set("answer", 42, source="test", confidence=0.9)
    item = board.get_entry("answer")
    assert item is not None
    assert item.value == 42
    assert item.source == "test"
    assert item.confidence == 0.9


def test_event_bus_dispatches_without_cross_event_leaks():
    bus = EventBus()
    received = []
    bus.subscribe("tool_execution_completed", received.append)
    bus.publish(CognitiveEvent(event_type="tool_execution_completed", data={"ok": True}))
    assert len(received) == 1
    assert received[0].data["ok"] is True


def test_session_lifecycle():
    session = CognitiveSession()
    assert session.active is True
    before = session.last_activity
    session.touch()
    assert session.last_activity >= before
    session.close()
    assert session.active is False


def test_cognitive_state_has_stable_identity():
    first = CognitiveState()
    second = CognitiveState()
    assert first.session.session_id != second.session.session_id


def test_resource_manager_returns_safe_policy():
    manager = ResourceManager()
    policy = manager.execution_policy()
    assert policy is not None
    assert "preferred_model_tier" in policy
