from app.cognition.world_model import Observation, WorldModel


def test_world_model_entity_relationship_observation_round_trip(tmp_path):
    model = WorldModel(str(tmp_path / "world.db"))
    chrome = model.upsert_entity("Chrome", "application", {"version": "151"}, 0.95)
    windows = model.upsert_entity("Windows", "operating_system", {"version": "11"}, 0.99)

    relationship = model.relate(chrome.id, "runs_on", windows.id, 0.9)
    observation = model.observe(Observation("obs-1", chrome.id, "status", "running", "desktop", 0.98))

    assert model.get_entity(chrome.id).attributes["version"] == "151"
    assert model.related(chrome.id)[0].predicate == relationship.predicate
    assert model.recent_observations(chrome.id)[0].value == observation.value
    snapshot = model.snapshot()
    assert snapshot["entities"] == 2
    assert snapshot["relationships"] == 1
    assert snapshot["observations"] == 1


def test_world_model_detects_temporal_changes(tmp_path):
    model = WorldModel(str(tmp_path / "world.db"))
    model.observe(Observation("obs-1", "chrome", "status", "stopped", "desktop", 0.9, "2026-01-01T00:00:00+00:00"))
    model.observe(Observation("obs-2", "chrome", "status", "running", "desktop", 0.98, "2026-01-01T00:01:00+00:00"))

    latest = model.latest_observation("chrome", "status")
    changes = model.changes_for("chrome", "status")

    assert latest.value == "running"
    assert len(changes) == 1
    assert changes[0].previous_value == "stopped"
    assert changes[0].current_value == "running"
