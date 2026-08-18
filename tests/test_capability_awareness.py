from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime
from app.cognition.reasoning_cycle import ReasoningCycle, ReasoningAction
from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_capability_availability_resolution(tmp_path):
    """
    Verify CognitiveRuntime.check_capability_availability resolves granular
    capability statuses (e.g. filesystem.search -> True, phone.adb -> False when offline).
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    caps = ["filesystem.search", "os.launch_app", "phone.adb"]
    cap_map = runtime.check_capability_availability(caps, "mobile_phone")

    assert cap_map["filesystem.search"] is True
    assert cap_map["os.launch_app"] is True
    # ADB phone command fails in test environment without real phone connected -> False
    assert cap_map["phone.adb"] is False


def test_reasoning_cycle_defers_when_required_capability_unavailable():
    """
    Verify ReasoningCycle defers when required capability is unavailable (e.g. phone.adb = False).
    """
    cycle = ReasoningCycle()

    available_caps = {
        "filesystem.search": True,
        "phone.adb": False
    }

    decision = cycle.decide(
        subject="user",
        predicate="action_intent",
        action_available=False,  # False because phone.adb is False
        available_capabilities=available_caps
    )

    assert decision.action == ReasoningAction.DEFER
    assert "phone.adb" in decision.reason
    assert "unavailable or offline" in decision.reason
