import pytest
from app.cognition.environment_grounding import EnvironmentGroundingEngine

def test_environment_grounding_probe():
    env = EnvironmentGroundingEngine.probe_complete_environment()
    assert "host_os" in env
    assert env["cpu_threads"] > 0
    assert env["installed_apps_count"] >= 0

def test_environment_grounding_prompt():
    prompt = EnvironmentGroundingEngine.generate_grounding_prompt_context()
    assert "[ENVIRONMENTAL SELF-GROUNDING" in prompt
    assert "Hardware Profile:" in prompt


def test_rapid_repeat_grounding_observations_do_not_collide(tmp_path, caplog):
    """Live 2026-09-05 (D6 window): the environment-grounding observation
    id was a '%H%M%S' timestamp — two topology observations inside the
    same second collided on the world_observations PRIMARY KEY
    ("UNIQUE constraint failed"). Ids are now uuid-based; two immediate
    probes must both land, with distinct ids and no constraint warning."""
    import logging
    from app.cognition.world_model import WorldModel
    wm = WorldModel(db_path=str(tmp_path / "wm.db"))
    with caplog.at_level(logging.WARNING):
        EnvironmentGroundingEngine.probe_complete_environment(world_model=wm)
        EnvironmentGroundingEngine.probe_complete_environment(world_model=wm)
    observations = wm.recent_observations(subject="host_environment",
                                          limit=10)
    assert len(observations) >= 2, observations
    ids = {obs.id for obs in observations}
    assert len(ids) == len(observations)  # all distinct
    assert not any("UNIQUE constraint" in r.message for r in caplog.records)
