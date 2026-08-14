from app.cognition.world_model import WorldModel


def test_entity_resolution_and_query(tmp_path):
    model = WorldModel(str(tmp_path / "world.db"))
    chrome = model.upsert_entity("Google Chrome", "application", {"aliases": ["chrome", "chrome.exe"]})
    model.upsert_entity("Windows 11", "operating_system")
    model.relate(chrome.id, "runs_on", model.resolve_entity("Windows 11").id)

    assert model.resolve_entity("chrome", "application").id == chrome.id
    result = model.query(entity_type="application")
    assert len(result["entities"]) == 1
    assert result["entities"][0].name == "Google Chrome"
    assert model.related(chrome.id, "runs_on")
