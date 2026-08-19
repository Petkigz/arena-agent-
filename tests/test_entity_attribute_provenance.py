"""
P0 Regression: Entity attributes must never carry environmental state.

Environmental state (status, source, observation_type) belongs exclusively
in Observations where provenance is enforced. Entity attributes hold only
identity/descriptor data (file_path, aliases, etc.).

This prevents downstream systems (BeliefEngine, MemoryLearner,
ReflectionEngine, Planning, Attention) from interpreting entity attributes
as authoritative environmental facts.
"""

import pytest
from app.cognition.world_model import WorldModel, Observation


class TestEntityAttributeProvenanceInvariant:

    def test_upsert_strips_status_from_attributes(self, tmp_path):
        wm = WorldModel(str(tmp_path / "wm.db"))
        entity = wm.upsert_entity("chrome", "process", {
            "status": "running", "source": "os_process_probe",
            "observation_type": "direct"
        })
        assert "status" not in entity.attributes
        assert "source" not in entity.attributes
        assert "observation_type" not in entity.attributes

    def test_upsert_preserves_identity_attributes(self, tmp_path):
        wm = WorldModel(str(tmp_path / "wm.db"))
        entity = wm.upsert_entity("report.pdf", "file", {
            "file_path": "/docs/report.pdf",
            "status": "identified",          # should be stripped
            "source": "filesystem_probe",     # should be stripped
        })
        assert entity.attributes.get("file_path") == "/docs/report.pdf"
        assert "status" not in entity.attributes
        assert "source" not in entity.attributes

    def test_upsert_merge_strips_state_keys(self, tmp_path):
        wm = WorldModel(str(tmp_path / "wm.db"))
        wm.upsert_entity("chrome", "process", {"aliases": ["google-chrome"]})
        entity = wm.upsert_entity("chrome", "process", {
            "status": "running", "pid": 1234
        })
        # aliases preserved, status stripped, pid preserved (not a state key)
        assert entity.attributes.get("aliases") == ["google-chrome"]
        assert entity.attributes.get("pid") == 1234
        assert "status" not in entity.attributes

    def test_entity_state_derived_from_observation(self, tmp_path):
        wm = WorldModel(str(tmp_path / "wm.db"))
        wm.upsert_entity("chrome", "process")
        wm.observe(Observation(
            id="obs1", subject="chrome", predicate="status",
            value="running", source="os_process_probe",
            confidence=1.0, observation_type="direct"
        ))

        state = wm.get_entity_state("chrome", "status")
        assert state is not None
        assert state["value"] == "running"
        assert state["source"] == "os_process_probe"
        assert state["confidence"] == 1.0
        assert state["observation_type"] == "direct"

    def test_entity_state_returns_none_without_observation(self, tmp_path):
        wm = WorldModel(str(tmp_path / "wm.db"))
        wm.upsert_entity("chrome", "process")

        state = wm.get_entity_state("chrome", "status")
        assert state is None  # No observation → state is unknown

    def test_state_keys_constant_is_complete(self):
        """Verify the set of state keys that must be excluded."""
        required_keys = {"status", "source", "observation_type"}
        assert required_keys.issubset(WorldModel.ENTITY_STATE_KEYS)

    def test_entity_attributes_cannot_masquerade_as_observation(self, tmp_path):
        """
        Even if someone passes observation-like data in attributes,
        it must be stripped before storage.
        """
        wm = WorldModel(str(tmp_path / "wm.db"))
        entity = wm.upsert_entity("server", "process", {
            "status": "running",
            "source": "os_process_probe",
            "observation_type": "direct",
            "confidence": 1.0,
            "hostname": "prod-01",     # identity data — should survive
        })

        # Identity data preserved
        assert entity.attributes.get("hostname") == "prod-01"

        # All state keys stripped
        for key in WorldModel.ENTITY_STATE_KEYS:
            assert key not in entity.attributes, \
                f"Entity attribute '{key}' should have been stripped"

    def test_perception_layer_entities_have_no_state(self, tmp_path):
        """
        Simulates what the perception layer does and verifies the invariant.
        """
        from app.cognition.perception import ObservationCollector
        from app.cognition.action_proposal import ActionProposal

        wm = WorldModel(str(tmp_path / "wm.db"))
        proposal = ActionProposal(action_type="open_application", payload={"app_name": "chrome"})
        exec_result = {
            "success": True,
            "execution_facts": [],
            "raw_output": {},
            "executed_actions": ["Launched Chrome"],
            "assistant_reply": "Chrome launched."
        }

        from unittest.mock import patch, MagicMock
        mock_proc = MagicMock()
        mock_proc.info = {"name": "chrome"}
        with patch("psutil.process_iter", return_value=[mock_proc]):
            ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        # Entity was created by the process probe
        entities = wm.find_entities(name="chrome")
        assert len(entities) >= 1
        entity = entities[0]

        # Entity attributes must NOT contain state
        assert "status" not in entity.attributes
        assert "source" not in entity.attributes
        assert "observation_type" not in entity.attributes

        # State is available through observations
        state = wm.get_entity_state("chrome", "status")
        assert state is not None
        assert state["value"] == "running"
        assert state["source"] == "os_process_probe"
