import sqlite3

import pytest

from app.cognition.scene_causal import SceneCausalReplay
from app.cognition.scene_graph import (
    PhysicsSimulator,
    SceneGraph,
    SceneGraphError,
    SceneGraphStore,
    SceneObject,
)


def box(object_id, *, x=0.0, y=0.5, width=1.0, height=1.0, static=False, support_id=None, vx=0.0):
    return SceneObject(
        object_id=object_id,
        object_type="box",
        x=x,
        y=y,
        width=width,
        height=height,
        static=static,
        support_id=support_id,
        vx=vx,
        evidence_ids=(f"evidence:{object_id}",),
    )


def test_partial_observation_preserves_hidden_objects_without_claiming_absence():
    scene = SceneGraph()
    scene.apply_observation("obs-1", [box("base")], evidence_ids=["camera:1"])
    scene.apply_observation("obs-2", [], occluded_ids=["base"], evidence_ids=["camera:2"])

    assert scene.object("base").visibility == "occluded"
    assert scene.object("base").observed is False
    assert scene.object("base").evidence_ids == ("evidence:base", "camera:1", "camera:2")

    scene.apply_observation("obs-3", [])
    assert scene.object("base").visibility == "unknown"
    assert "base" in scene.objects

    baseline = SceneGraph()
    baseline.add_or_update(box("floor", y=0.5, width=4.0, static=True))
    baseline.add_or_update(box("top", y=1.5, support_id="floor"))
    gap = baseline.clone()
    gap.apply_observation("partial-gap", [])
    assert PhysicsSimulator.simulate(baseline, steps=1).scene.object("top").y == pytest.approx(
        PhysicsSimulator.simulate(gap, steps=1).scene.object("top").y
    )
    with pytest.raises(SceneGraphError, match="unknown objects occluded"):
        scene.apply_observation("obs-4", [], occluded_ids=["never-seen"])


def test_deterministic_physics_predicts_block_stack_and_stability():
    scene = SceneGraph()
    scene.add_or_update(box("floor", y=0.5, width=4.0, static=True))
    scene.add_or_update(box("top", y=4.0, x=0.0))

    first = PhysicsSimulator.simulate(scene, steps=40, dt=0.1)
    second = PhysicsSimulator.simulate(scene, steps=40, dt=0.1)

    assert first.scene.digest() == second.scene.digest()
    assert first.scene.object("top").support_id == "floor"
    assert first.scene.object("top").y == pytest.approx(1.5)
    assert first.stable["top"] is True
    assert first.weights["top"] == pytest.approx(9.81)
    friction_scene = SceneGraph()
    friction_scene.add_or_update(box("floor", y=0.5, width=4.0, static=True))
    friction_scene.add_or_update(box("top", y=1.5, vx=1.0))
    friction_prediction = PhysicsSimulator.simulate(friction_scene, steps=1, dt=0.1, friction=0.2)
    assert friction_prediction.scene.object("top").vx == pytest.approx(0.8)
    assert friction_prediction.friction == pytest.approx(0.2)
    assert first.simulation_only is True
    assert first.observation_required is True

    edge_scene = SceneGraph()
    edge_scene.add_or_update(box("floor", width=2.0, static=True))
    edge_scene.add_or_update(box("edge", x=0.75, y=2.0))
    edge = PhysicsSimulator.simulate(edge_scene, steps=30, dt=0.1)
    assert edge.stable["edge"] is False


def test_scene_store_persists_versioned_snapshots_and_events(tmp_path):
    store = SceneGraphStore(tmp_path / "scene.db")
    scene = SceneGraph()
    scene.add_or_update(box("a"))
    persisted = store.save(
        scene,
        event_type="observation",
        observation_id="obs-1",
        evidence_ids=["camera:1"],
    )

    reopened = SceneGraphStore(tmp_path / "scene.db")
    loaded = reopened.load_latest()
    assert loaded.revision == 1
    assert loaded.digest() == persisted.digest()
    assert reopened.history()[-1]["observation_id"] == "obs-1"
    assert reopened.history()[-1]["event_type"] == "observation"

    with sqlite3.connect(tmp_path / "scene.db") as conn:
        conn.execute("UPDATE scene_snapshots SET snapshot_json=? WHERE revision=1", ('{"tampered": true}',))
    with pytest.raises(SceneGraphError, match="digest"):
        SceneGraphStore(tmp_path / "scene.db").load_latest()

    with sqlite3.connect(tmp_path / "unsupported.db") as conn:
        conn.execute(
            "CREATE TABLE scene_store_meta "
            "(singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL, current_revision INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO scene_store_meta VALUES (1, 99, 0)")
    with pytest.raises(SceneGraphError, match="unsupported scene store"):
        SceneGraphStore(tmp_path / "unsupported.db")


def test_causal_scene_replay_is_side_effect_free_and_prediction_only():
    scene = SceneGraph()
    scene.add_or_update(box("floor", width=4.0, static=True))
    scene.add_or_update(box("top", y=1.5, support_id="floor"))
    baseline_digest = scene.digest()

    replay = SceneCausalReplay.replay(
        scene,
        "floor",
        {"x": 10.0},
        steps=10,
        dt=0.1,
    )

    assert scene.digest() == baseline_digest
    assert replay.baseline_digest == baseline_digest
    assert replay.predicted_digest != baseline_digest
    assert replay.epistemic_status == "PREDICTED"
    assert replay.observation_required is True
    assert replay.execution_performed is False
    assert replay.prediction.scene.object("top").support_id is None
    assert replay.causal_paths == (("scene:floor", "scene:top"),)
