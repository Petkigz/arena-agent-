from app.cognition.runtime import CognitiveRuntime
from app.cognition.world_model import WorldModel


def test_capture_world_state_does_not_fabricate_running_status(tmp_path):
    """
    P0 Fix Verification:
    Verify that an entity in WorldModel without an explicit status observation/attribute
    defaults to status='unknown' rather than fabricating 'running' or 'active'.
    """
    path = str(tmp_path / "arena.db")
    wm = WorldModel(path)
    wm.upsert_entity(name="photoshop.exe", entity_type="process", attributes={"pid": 1234})

    runtime = CognitiveRuntime(db_path=path)

    obs_state = runtime.capture_observed_world_state(
        executed_actions=["Launched photoshop.exe"],
        assistant_reply="Execution finished."
    )

    entities = obs_state["entities"]
    assert len(entities) > 0
    ps_entity = next(e for e in entities if e["name"] == "photoshop.exe")

    # MUST NOT fabricate "running" or "active"
    assert ps_entity["status"] == "unknown"


def test_capture_world_state_reflects_real_observation(tmp_path):
    """
    Verify that when a real observation exists in WorldModel, capture_observed_world_state
    reflects that exact observed value.
    """
    from app.cognition.world_model import Observation

    path = str(tmp_path / "arena.db")
    wm = WorldModel(path)
    wm.upsert_entity(name="chrome.exe", entity_type="process", attributes={})
    wm.observe(Observation(
        id="obs_c1",
        subject="chrome.exe",
        predicate="status",
        value="running",
        source="process_monitor"
    ))

    runtime = CognitiveRuntime(db_path=path)

    obs_state = runtime.capture_observed_world_state(
        executed_actions=["Launched chrome.exe"],
        assistant_reply="Chrome launched."
    )

    entities = obs_state["entities"]
    chrome_entity = next(e for e in entities if e["name"] == "chrome.exe")

    # Real observation MUST be reflected
    assert chrome_entity["status"] == "running"
