from app.cognition.event_bus import EventBus
from app.cognition.world_ingest import WorldIngestor
from app.cognition.world_model import WorldModel


def test_ingestor_emits_change_event(tmp_path):
    model = WorldModel(str(tmp_path / "world.db"))
    bus = EventBus()
    events = []
    bus.subscribe("world_state_changed", events.append)
    ingestor = WorldIngestor(model, bus)

    ingestor.ingest("chrome", "status", "stopped", source="desktop")
    _, change = ingestor.ingest("chrome", "status", "running", source="desktop")

    assert change is not None
    assert change.previous == "stopped"
    assert change.current == "running"
    assert len(events) == 1
    assert events[0].data["current"] == "running"
