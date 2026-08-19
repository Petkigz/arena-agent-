"""
P0 Regression: capture_observed_world_state() entity-attribute fallback.

When an entity exists in WorldModel but has NO latest observation,
the fallback must NOT inherit entity attributes as provenance.
Entity attributes are creation-time metadata, not environmental observations.

Without this fix, the chain was:
  Execution fact -> entity attributes -> capture_observed_world_state() -> verification
which bypassed the provenance boundary even though GoalVerifier was strict.
"""

import pytest
from unittest.mock import patch
from app.cognition.runtime import CognitiveRuntime
from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel, Observation
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_lifecycle import GoalLifecycleState


def test_entity_without_observation_defaults_to_unknown_not_attributes(tmp_path):
    """
    An entity with status='running' in attributes but NO observation
    must report status='unknown' with source='not_observed' in
    capture_observed_world_state(), NOT inherit the attribute values.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))

    # Create an entity directly with contaminated-looking attributes
    # (simulating what would happen if execution claims leaked into attributes)
    runtime.world.upsert_entity(
        name="photoshop",
        entity_type="process",
        attributes={
            "status": "running",
            "source": "os_process_probe",
            "observation_type": "direct",
            "confidence": 1.0
        }
    )
    # Crucially: do NOT create any observation for this entity

    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    obs_state = runtime.capture_observed_world_state(
        executed_actions=["Launched Photoshop"],
        assistant_reply="Done.",
        goal_rep=goal_rep
    )

    # Find the photoshop entity in the captured state
    entities = obs_state.get("world_state", {}).get("entities", [])
    photoshop_entities = [e for e in entities if "photoshop" in e.get("name", "").lower()]

    if photoshop_entities:
        ent = photoshop_entities[0]
        # Must NOT inherit the contaminated attributes
        assert ent["status"] == "unknown", \
            f"Entity without observation must report 'unknown', got '{ent['status']}'"
        assert ent["source"] == "not_observed", \
            f"Entity without observation must report 'not_observed', got '{ent['source']}'"
        assert ent["confidence"] == 0.0, \
            f"Entity without observation must have confidence 0.0, got {ent['confidence']}"


def test_entity_with_observation_uses_observation_not_attributes(tmp_path):
    """
    When an entity HAS a latest observation, capture_observed_world_state
    must use the observation's values, not the entity attributes.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))

    # Create entity with one set of attributes
    runtime.world.upsert_entity(
        name="chrome",
        entity_type="process",
        attributes={"status": "running", "source": "old_claim"}
    )

    # Create a separate observation with different (authoritative) values
    runtime.world.observe(Observation(
        id="obs_chrome_probe",
        subject="chrome",
        predicate="status",
        value="not_running",
        source="os_process_probe",
        confidence=1.0,
        observation_type="direct"
    ))

    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Chrome")
    obs_state = runtime.capture_observed_world_state(
        executed_actions=["Launched Chrome"],
        assistant_reply="Done.",
        goal_rep=goal_rep
    )

    entities = obs_state.get("world_state", {}).get("entities", [])
    chrome_entities = [e for e in entities if "chrome" in e.get("name", "").lower()]

    assert len(chrome_entities) >= 1
    ent = chrome_entities[0]
    # Must use observation values, NOT entity attributes
    assert ent["status"] == "not_running", \
        "Must use observation value, not entity attribute"
    assert ent["source"] == "os_process_probe", \
        "Must use observation source, not entity attribute source"


def test_contaminated_entity_cannot_satisfy_verification_through_capture(tmp_path):
    """
    End-to-end: create a contaminated entity (no observation), run
    capture_observed_world_state(), then verify the goal is NOT satisfied.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "test.db"))

    # Simulate a contaminated entity (as if execution claims leaked)
    runtime.world.upsert_entity(
        name="photoshop",
        entity_type="process",
        attributes={
            "status": "running",
            "source": "os_process_probe",
            "observation_type": "direct"
        }
    )

    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    obs_state = runtime.capture_observed_world_state(
        executed_actions=["Launched Photoshop"],
        assistant_reply="Done.",
        goal_rep=goal_rep
    )

    result = GoalVerifier.verify_goal_achievement(
        goal_rep,
        executed_actions=["Launched Photoshop"],
        assistant_reply="Done.",
        observed_state=obs_state
    )

    # Must NOT be satisfied — no environmental observation exists
    assert result.verified_success is False, \
        "Contaminated entity attributes must not satisfy goal verification"
