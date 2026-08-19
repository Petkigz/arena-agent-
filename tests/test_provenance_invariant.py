"""
Provenance invariant: every observation in WorldModel must carry a correct
observation_type that reflects its actual source.

  direct         — environmental probe (os_process_probe, filesystem_probe, etc.)
  environmental  — system topology sensor
  inferred       — tool investigation output, derived from other observations
  self_reported  — user input, LLM output, execution trace claims

No component may create an observation with observation_type="direct"
unless it originates from an actual environmental probe.
"""

import pytest
from app.cognition.world_ingest import WorldIngestor, WorldChange
from app.cognition.world_model import WorldModel, Observation


class TestWorldIngestorProvenance:

    def test_observation_type_is_required(self, tmp_path):
        """Phase 2: WorldIngestor requires explicit observation_type, no default."""
        import pytest
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        # Without observation_type → TypeError
        with pytest.raises(TypeError):
            ingestor.ingest("user", "query", "hello", source="user_input")

        # With explicit observation_type → works
        obs, _ = ingestor.ingest("user", "query", "hello",
                                 source="user_input",
                                 observation_type="self_reported")
        assert obs.observation_type == "self_reported"

    def test_explicit_direct_type_preserved(self, tmp_path):
        """Explicit observation_type='direct' is passed through."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        obs, _ = ingestor.ingest(
            "chrome", "status", "running",
            source="os_process_probe",
            observation_type="direct"
        )
        assert obs.observation_type == "direct"

    def test_inferred_type_for_tool_output(self, tmp_path):
        """Tool investigation output should be tagged as inferred."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        obs, _ = ingestor.ingest(
            "system", "diagnostic", {"cpu": 50},
            source="tool:diagnostic_probe",
            observation_type="inferred"
        )
        assert obs.observation_type == "inferred"

    def test_environmental_type_for_topology(self, tmp_path):
        """System topology probes should be tagged as environmental."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        obs, _ = ingestor.ingest(
            "host_environment", "topology", {"os": "linux"},
            source="environment_grounding_engine",
            observation_type="environmental"
        )
        assert obs.observation_type == "environmental"

    def test_change_record_carries_observation_type(self, tmp_path):
        """WorldChange records must carry the observation_type."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        ingestor.ingest("chrome", "status", "running", source="probe", observation_type="direct")
        _, change = ingestor.ingest("chrome", "status", "stopped", source="probe", observation_type="direct")

        assert change is not None
        assert change.observation_type == "direct"

    def test_self_reported_change_record(self, tmp_path):
        """User input changes should be tagged self_reported in change records."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        ingestor.ingest("user", "query", "first", source="user_input", observation_type="self_reported")
        _, change = ingestor.ingest("user", "query", "second", source="user_input", observation_type="self_reported")

        assert change is not None
        assert change.observation_type == "self_reported"


class TestObservationTypeIntegrity:
    """Verify that observation_type is correctly stored and retrievable."""

    def test_observation_type_round_trips_through_db(self, tmp_path):
        wm = WorldModel(str(tmp_path / "wm.db"))

        for obs_type in ["direct", "environmental", "inferred", "self_reported"]:
            obs = Observation(
                id=f"test_{obs_type}",
                subject="test",
                predicate="type_check",
                value=obs_type,
                source="test_source",
                confidence=1.0,
                observation_type=obs_type,
            )
            wm.observe(obs)

        for obs_type in ["direct", "environmental", "inferred", "self_reported"]:
            latest = wm.latest_observation("test", "type_check")
            # latest_observation returns the most recent — check all via recent
            break

        all_obs = wm.recent_observations("test", limit=10)
        types_found = {o.observation_type for o in all_obs}
        assert "direct" in types_found
        assert "environmental" in types_found
        assert "inferred" in types_found
        assert "self_reported" in types_found

    def test_no_unqualified_environmental_facts_from_llm_output(self, tmp_path):
        """
        LLM output ingested via WorldIngestor must NOT be tagged as 'direct'.
        This is the core invariant: no component can turn LLM statements
        into unqualified environmental facts.
        """
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        # Simulate LLM reply being ingested
        ingestor.ingest(
            "system", "response", "The server is running on port 8080",
            source="master_agent",
            observation_type="self_reported",
        )

        obs = wm.latest_observation("system", "response")
        assert obs is not None
        assert obs.observation_type != "direct", \
            "LLM output must never be tagged as 'direct' observation"
        assert obs.observation_type == "self_reported"

    def test_no_unqualified_environmental_facts_from_user_input(self, tmp_path):
        """User input must NOT be tagged as 'direct'."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        ingestor.ingest(
            "user", "query", "Open Chrome browser",
            source="user_input",
            observation_type="self_reported",
        )

        obs = wm.latest_observation("user", "query")
        assert obs is not None
        assert obs.observation_type != "direct", \
            "User input must never be tagged as 'direct' observation"

    def test_no_unqualified_environmental_facts_from_tool_output(self, tmp_path):
        """Tool investigation output must NOT be tagged as 'direct'."""
        wm = WorldModel(str(tmp_path / "wm.db"))
        ingestor = WorldIngestor(wm)

        ingestor.ingest(
            "server", "diagnostic", {"status": "healthy"},
            source="tool:health_check",
            observation_type="inferred",
        )

        obs = wm.latest_observation("server", "diagnostic")
        assert obs is not None
        assert obs.observation_type != "direct", \
            "Tool output must never be tagged as 'direct' observation"
        assert obs.observation_type == "inferred"
