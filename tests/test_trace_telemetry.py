import pytest
from app.cognition.trace import CognitiveTrace

def test_cognitive_trace_telemetry():
    trace = CognitiveTrace(user_input="Test telemetry trace", session_id="sess_telemetry_001")
    assert trace.user_input == "Test telemetry trace"
    assert trace.session_id == "sess_telemetry_001"
    assert trace.is_finalized is False

    trace.finalize(reply="Telemetry captured.", actions=["launch_app"], latency=120.5)
    assert trace.is_finalized is True
    assert trace.latency_ms == 120.5
    assert trace.actions_executed == ["launch_app"]
