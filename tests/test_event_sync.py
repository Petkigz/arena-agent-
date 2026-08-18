import pytest
from app.cognition.event_bus import EventBus
from app.cognition.events import CognitiveEvent

def test_event_bus_synchronization():
    bus = EventBus()
    received_events = []

    def handle_event(evt):
        received_events.append(evt)

    # Subscribe to state_changed event
    bus.subscribe("state_changed", handle_event)

    # Emit event
    bus.emit("state_changed", {"new_state": "active_reasoning"}, source="test_runner")

    assert len(received_events) == 1
    assert received_events[0].event_type == "state_changed"
    assert received_events[0].data["new_state"] == "active_reasoning"
