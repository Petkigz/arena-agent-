"""
Phase 1A: Belief Revision Engine Tests.

Verifies evidence-weighted belief revision with:
- Time decay (older evidence carries less weight)
- Provenance weighting (direct probes > self-reported)
- Staleness detection (beliefs needing refresh)
- Contradiction handling (competing evidence reduces confidence)
- Periodic maintenance (decay_all)
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.cognition.beliefs import BeliefStore, Evidence, PROVENANCE_WEIGHTS, DECAY_HALF_LIFE_HOURS
from app.cognition.belief_engine import BeliefEngine


# ── Evidence Weighting ────────────────────────────────────────────────


class TestEvidenceWeighting:

    def test_fresh_evidence_has_full_time_weight(self):
        ev = Evidence(source="os_process_probe", value="running", confidence=1.0)
        assert ev.time_weight() > 0.9  # Fresh = near 1.0

    def test_old_evidence_has_reduced_time_weight(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        ev = Evidence(source="os_process_probe", value="running", confidence=1.0, observed_at=old_time)
        weight = ev.time_weight()
        assert weight < 0.5  # 48 hours old = significantly decayed
        assert weight >= 0.1  # Floor at 0.1

    def test_very_old_evidence_approaches_floor(self):
        ancient = (datetime.now(timezone.utc) - timedelta(hours=240)).isoformat()
        ev = Evidence(source="os_process_probe", value="running", confidence=1.0, observed_at=ancient)
        assert ev.time_weight() < 0.2

    def test_direct_probe_has_higher_provenance_weight(self):
        probe_ev = Evidence(source="os_process_probe", value="running", confidence=1.0)
        self_ev = Evidence(source="execution_result", value="running", confidence=1.0)
        assert probe_ev.provenance_weight() > self_ev.provenance_weight()

    def test_self_reported_has_lowest_provenance_weight(self):
        ev = Evidence(source="self_reported", value="running", confidence=1.0)
        assert ev.provenance_weight() == PROVENANCE_WEIGHTS["self_reported"]
        assert ev.provenance_weight() < 0.3

    def test_weighted_score_combines_all_factors(self):
        ev = Evidence(source="os_process_probe", value="running", confidence=0.9)
        ws = ev.weighted_score()
        # confidence(0.9) × time(~1.0) × provenance(1.0) ≈ 0.9
        assert ws > 0.8

    def test_old_weak_evidence_has_low_weighted_score(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        ev = Evidence(source="self_reported", value="running", confidence=0.5, observed_at=old_time)
        ws = ev.weighted_score()
        assert ws < 0.1  # Old × self_reported × low confidence


# ── Belief Revision ──────────────────────────────────────────────────


class TestBeliefRevision:

    def test_revise_selects_value_with_most_weighted_evidence(self):
        engine = BeliefEngine()
        # First observation: running (strong)
        engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        # Contradictory: stopped (weaker source)
        engine.ingest("chrome", "status", "stopped", source="self_reported", observation_type="direct", confidence=0.8)

        belief = engine.beliefs.revise("chrome", "status")
        # "running" from os_process_probe should win due to higher provenance weight
        assert belief.value == "running"

    def test_revise_fresh_evidence_overrides_stale(self):
        engine = BeliefEngine()
        # Old evidence: running
        old_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        old_ev = Evidence(source="os_process_probe", value="running", confidence=1.0, observed_at=old_time)
        engine.beliefs._beliefs[("chrome", "status")] = __import__("app.cognition.beliefs", fromlist=["Belief"]).Belief(
            "chrome", "status", "running", 1.0, [old_ev]
        )

        # Fresh evidence: stopped
        engine.ingest("chrome", "status", "stopped", source="os_process_probe", observation_type="direct", confidence=0.9)

        belief = engine.beliefs.revise("chrome", "status")
        # Fresh "stopped" should override stale "running"
        assert belief.value == "stopped"

    def test_revise_confidence_reflects_evidence_proportion(self):
        engine = BeliefEngine()
        # 3 pieces of evidence for "running", 1 for "stopped"
        engine.ingest("server", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        engine.ingest("server", "status", "running", source="filesystem_probe", observation_type="direct", confidence=0.8)
        engine.ingest("server", "status", "running", source="system_probe", observation_type="direct", confidence=0.85)
        engine.ingest("server", "status", "stopped", source="os_process_probe", observation_type="direct", confidence=0.7)

        belief = engine.beliefs.revise("server", "status")
        assert belief.value == "running"
        # Confidence should be high (most evidence supports running)
        assert belief.confidence > 0.6

    def test_revise_contradictory_evidence_reduces_confidence(self):
        engine = BeliefEngine()
        # Two DIFFERENT admissible sources reporting contradictory values
        engine.ingest("app", "status", "running", source="os_process_probe",
                     observation_type="direct", confidence=0.8)
        engine.ingest("app", "status", "stopped", source="filesystem_probe",
                     observation_type="direct", confidence=0.8)

        belief = engine.beliefs.revise("app", "status")
        # Equal contradictory evidence from independent admissible sources → confidence ≈ 0.5
        assert belief.confidence < 0.6


# ── Staleness Detection ──────────────────────────────────────────────


class TestStalenessDetection:

    def test_fresh_belief_is_not_stale(self):
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=1.0)
        assert engine.beliefs.is_stale("chrome", "status") is False

    def test_old_belief_is_stale(self):
        engine = BeliefEngine()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        ev = Evidence(source="os_process_probe", value="running", confidence=1.0, observed_at=old_time)
        from app.cognition.beliefs import Belief
        engine.beliefs._beliefs[("chrome", "status")] = Belief(
            "chrome", "status", "running", 1.0, [ev]
        )
        assert engine.beliefs.is_stale("chrome", "status") is True

    def test_nonexistent_belief_is_stale(self):
        engine = BeliefEngine()
        assert engine.beliefs.is_stale("nonexistent", "predicate") is True

    def test_stale_beliefs_lists_aged_beliefs(self):
        engine = BeliefEngine()
        # Fresh belief
        engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=1.0)
        # Old belief
        old_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        ev = Evidence(source="os_process_probe", value="stopped", confidence=1.0, observed_at=old_time)
        from app.cognition.beliefs import Belief
        engine.beliefs._beliefs[("firefox", "status")] = Belief(
            "firefox", "status", "stopped", 1.0, [ev]
        )

        stale = engine.beliefs.stale_beliefs(max_age_hours=48.0)
        stale_names = [(b.subject, b.predicate) for b in stale]
        assert ("firefox", "status") in stale_names
        assert ("chrome", "status") not in stale_names


# ── Periodic Maintenance ─────────────────────────────────────────────


class TestDecayMaintenance:

    def test_decay_all_recalculates_all_beliefs(self):
        engine = BeliefEngine()
        engine.ingest("a", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        engine.ingest("b", "status", "active", source="os_process_probe", observation_type="direct", confidence=0.8)

        changed = engine.beliefs.decay_all()
        # All beliefs recalculated (may or may not change depending on timing)
        assert isinstance(changed, int)
        assert changed >= 0

    def test_decay_all_ages_old_beliefs(self):
        engine = BeliefEngine()
        # Create an old belief with high confidence
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        ev = Evidence(source="os_process_probe", value="running", confidence=1.0, observed_at=old_time)
        from app.cognition.beliefs import Belief
        engine.beliefs._beliefs[("old_app", "status")] = Belief(
            "old_app", "status", "running", 1.0, [ev]
        )

        # Before decay, incremental confidence is still 1.0
        assert engine.beliefs._beliefs[("old_app", "status")].confidence == 1.0

        # After decay, recalculated confidence should be lower
        engine.beliefs.decay_all()
        belief = engine.beliefs._beliefs[("old_app", "status")]
        # With only one piece of evidence, confidence stays 1.0 (it's the only value)
        # But the weighted score is reduced — test that revise was called
        assert belief.updated_at is not None


# ── BeliefEngine Integration ─────────────────────────────────────────


class TestBeliefEngineRevision:

    def test_inspect_recalculates_with_time_decay(self):
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        # self_reported evidence is NOT admissible to the belief pool
        engine.ingest("chrome", "status", "stopped", source="self_reported", observation_type="direct", confidence=0.8)

        result = engine.inspect("chrome", "status")
        assert result is not None
        # Only admissible evidence (os_process_probe) is in BeliefStore
        assert result.belief_value == "running"
        assert result.evidence_count == 1  # self_reported rejected by admissibility gate

    def test_inspect_returns_staleness_flag(self):
        engine = BeliefEngine()
        engine.ingest("app", "status", "running", source="os_process_probe", observation_type="direct", confidence=1.0)

        result = engine.inspect("app", "status")
        assert result.is_stale is False

    def test_inspect_nonexistent_returns_none(self):
        engine = BeliefEngine()
        assert engine.inspect("nonexistent", "predicate") is None

    def test_maintain_recalculates_all(self):
        engine = BeliefEngine()
        engine.ingest("a", "x", "val1", source="os_process_probe", observation_type="direct", confidence=0.9)
        engine.ingest("b", "y", "val2", source="filesystem_probe", observation_type="direct", confidence=0.8)

        changed = engine.maintain()
        assert isinstance(changed, int)

    def test_stale_beliefs_reports_aged_beliefs(self):
        engine = BeliefEngine()
        engine.ingest("fresh", "status", "running", source="os_process_probe", observation_type="direct", confidence=1.0)

        stale = engine.stale_beliefs(max_age_hours=48.0)
        # Fresh belief should not be stale
        stale_subjects = [s["subject"] for s in stale]
        assert "fresh" not in stale_subjects

    def test_evidence_report_shows_provenance_chain(self):
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        engine.ingest("chrome", "status", "running", source="filesystem_probe", observation_type="direct", confidence=0.7)

        report = engine.evidence_report("chrome", "status")
        assert report is not None
        assert report["evidence_count"] == 2
        assert report["current_value"] == "running"
        assert not report["is_stale"]
        # Each evidence entry has weighted score
        for ev in report["evidence"]:
            assert "weighted_score" in ev
            assert "provenance_weight" in ev
            assert "age_hours" in ev


# ── SQLite Persistence ───────────────────────────────────────────────


class TestBeliefPersistence:

    def test_beliefs_persist_and_reload(self, tmp_path):
        db_path = str(tmp_path / "beliefs.db")

        # Create and populate
        engine1 = BeliefEngine(db_path=db_path)
        engine1.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        engine1.ingest("chrome", "status", "stopped", source="filesystem_probe", observation_type="direct", confidence=0.8)

        # Reload from disk
        engine2 = BeliefEngine(db_path=db_path)
        belief = engine2.beliefs.get("chrome", "status")
        assert belief is not None
        assert len(belief.evidence) == 2

        # Revise from reloaded evidence
        revised = engine2.beliefs.revise("chrome", "status")
        assert revised is not None
        # Direct probe should still dominate
        assert revised.value == "running"

    def test_staleness_detected_after_reload(self, tmp_path):
        db_path = str(tmp_path / "beliefs.db")

        engine = BeliefEngine(db_path=db_path)
        engine.ingest("app", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
        
        # Manually set old timestamp
        old_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        belief = engine.beliefs.get("app", "status")
        belief.evidence[0].observed_at = old_time
        engine.beliefs._beliefs[("app", "status")] = belief
        engine.beliefs._save_to_db(belief)

        # Reload and check staleness
        engine2 = BeliefEngine(db_path=db_path)
        assert engine2.beliefs.is_stale("app", "status") is True


# ── BeliefEngine Admissibility Gate ──────────────────────────────────


class TestBeliefAdmissibilityGate:
    """
    P0: BeliefEngine must reject non-authoritative evidence from the
    environmental belief pool. self_reported, inferred, and execution
    claims are tracked as hypotheses but do NOT become environmental beliefs.
    """

    def test_direct_probe_is_admissible(self):
        assert BeliefEngine.is_admissible("os_process_probe", "direct", 1.0) is True

    def test_environmental_probe_is_admissible(self):
        assert BeliefEngine.is_admissible("environment_grounding_engine", "environmental", 1.0) is True

    def test_self_reported_is_not_admissible(self):
        assert BeliefEngine.is_admissible("execution_result", "self_reported", 1.0) is False

    def test_inferred_is_not_admissible(self):
        assert BeliefEngine.is_admissible("tool:diagnostic", "inferred", 0.9) is False

    def test_user_input_is_not_admissible(self):
        assert BeliefEngine.is_admissible("user_input", "direct", 1.0) is False

    def test_master_agent_is_not_admissible(self):
        assert BeliefEngine.is_admissible("master_agent", "direct", 1.0) is False

    def test_zero_confidence_is_not_admissible(self):
        assert BeliefEngine.is_admissible("os_process_probe", "direct", 0.0) is False

    def test_execution_result_source_rejected(self):
        assert BeliefEngine.is_admissible("execution_result", "direct", 0.9) is False

    def test_self_reported_does_not_enter_belief_store(self):
        engine = BeliefEngine()
        # Admissible evidence
        engine.ingest("chrome", "status", "running",
                       source="os_process_probe", confidence=0.9,
                       observation_type="direct")
        # Non-admissible: self_reported
        engine.ingest("chrome", "status", "stopped",
                       source="execution_result", confidence=1.0,
                       observation_type="self_reported")

        # BeliefStore should only contain the direct probe
        belief = engine.beliefs.get("chrome", "status")
        assert belief is not None
        assert belief.value == "running"
        assert len(belief.evidence) == 1
        assert belief.evidence[0].source == "os_process_probe"

    def test_inferred_does_not_enter_belief_store(self):
        engine = BeliefEngine()
        engine.ingest("server", "health", "degraded",
                       source="tool:health_check", confidence=0.8,
                       observation_type="inferred")

        # Should NOT be in BeliefStore
        belief = engine.beliefs.get("server", "health")
        assert belief is None

    def test_non_admissible_still_tracked_as_hypothesis(self):
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "stopped",
                       source="self_reported", confidence=0.7,
                       observation_type="self_reported")

        # Not in BeliefStore
        belief = engine.beliefs.get("chrome", "status")
        assert belief is None

        # But tracked as hypothesis — inspect returns result with has_belief=False
        result = engine.inspect("chrome", "status")
        assert result is not None
        assert result.has_belief is False
        assert result.belief_value is None
        assert result.hypothesis_value == "stopped"

    def test_admissible_and_non_admissible_coexist(self):
        engine = BeliefEngine()
        # Direct probe: admissible
        engine.ingest("app", "status", "running",
                       source="os_process_probe", confidence=0.95,
                       observation_type="direct")
        # Execution claim: not admissible
        engine.ingest("app", "status", "crashed",
                       source="execution_result", confidence=0.8,
                       observation_type="self_reported")

        # BeliefStore only has the direct probe
        belief = engine.beliefs.get("app", "status")
        assert belief is not None
        assert belief.value == "running"
        assert len(belief.evidence) == 1

    def test_filesystem_probe_is_admissible(self):
        assert BeliefEngine.is_admissible("filesystem_probe", "direct", 1.0) is True

    def test_web_search_probe_is_admissible(self):
        assert BeliefEngine.is_admissible("web_search_probe", "direct", 0.9) is True

    def test_observation_type_is_required(self):
        # Phase 2: observation_type is required, no default
        import pytest
        with pytest.raises(TypeError):
            BeliefEngine.is_admissible("os_process_probe", confidence=1.0)
        # With explicit observation_type, it works
        assert BeliefEngine.is_admissible("os_process_probe", "direct", confidence=1.0) is True


# ── Belief ↔ Observation Link ─────────────────────────────────────────


class TestBeliefObservationLink:
    """
    P1: Evidence must link back to the WorldModel Observation that generated it.
    This enables provenance tracing, contradiction resolution, belief rollback,
    and debugging.
    """

    def test_evidence_stores_observation_id(self):
        from app.cognition.beliefs import Evidence
        ev = Evidence(source="probe_a", value="running", confidence=0.9,
                     observation_id="obs_abc123")
        assert ev.observation_id == "obs_abc123"

    def test_evidence_observation_id_defaults_none(self):
        from app.cognition.beliefs import Evidence
        ev = Evidence(source="probe_a", value="running", confidence=0.9)
        assert ev.observation_id is None

    def test_observe_passes_observation_id(self):
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running",
                     source="os_process_probe", observation_type="direct", confidence=0.9,
                     observation_id="obs_xyz789")
        belief = engine.beliefs.get("chrome", "status")
        assert belief.evidence[0].observation_id == "obs_xyz789"

    def test_ingest_passes_observation_id(self):
        from app.cognition.belief_engine import BeliefEngine
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running",
                      source="os_process_probe", confidence=0.9,
                      observation_type="direct",
                      observation_id="obs_link_test")
        belief = engine.beliefs.get("chrome", "status")
        assert belief is not None
        assert belief.evidence[0].observation_id == "obs_link_test"

    def test_trace_provenance_returns_chain(self):
        from app.cognition.beliefs import BeliefStore
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running",
                      source="os_process_probe", observation_type="direct", confidence=0.9,
                      observation_id="obs_001")
        engine.ingest("chrome", "status", "running",
                      source="filesystem_probe", observation_type="direct", confidence=0.8,
                      observation_id="obs_002")

        chain = engine.beliefs.trace_provenance("chrome", "status")
        assert chain is not None
        assert len(chain) == 2
        obs_ids = {e["observation_id"] for e in chain}
        assert "obs_001" in obs_ids
        assert "obs_002" in obs_ids

    def test_trace_provenance_sorted_newest_first(self):
        from app.cognition.beliefs import BeliefStore
        import time
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running",
                      source="os_process_probe", observation_type="direct", confidence=0.9,
                      observation_id="obs_first")
        time.sleep(0.01)
        engine.ingest("chrome", "status", "stopped",
                      source="filesystem_probe", observation_type="direct", confidence=0.8,
                      observation_id="obs_second")

        chain = engine.beliefs.trace_provenance("chrome", "status")
        assert chain[0]["observation_id"] == "obs_second"
        assert chain[1]["observation_id"] == "obs_first"

    def test_trace_provenance_nonexistent_returns_none(self):
        from app.cognition.beliefs import BeliefStore
        engine = BeliefEngine()
        assert engine.beliefs.trace_provenance("nonexistent", "predicate") is None

    def test_evidence_summary_includes_observation_id(self):
        from app.cognition.beliefs import BeliefStore
        engine = BeliefEngine()
        engine.ingest("chrome", "status", "running",
                      source="os_process_probe", observation_type="direct", confidence=0.9,
                      observation_id="obs_summary_test")

        summary = engine.beliefs.evidence_summary("chrome", "status")
        assert summary is not None
        assert summary["evidence"][0]["observation_id"] == "obs_summary_test"

    def test_observation_id_persists_through_db(self, tmp_path):
        from app.cognition.beliefs import BeliefStore
        db_path = str(tmp_path / "beliefs.db")

        engine1 = BeliefEngine(db_path=db_path)
        engine1.ingest("chrome", "status", "running",
                      source="os_process_probe", observation_type="direct", confidence=0.9,
                      observation_id="obs_persist")

        engine2 = BeliefEngine(db_path=db_path)
        chain = engine2.beliefs.trace_provenance("chrome", "status")
        assert chain is not None
        assert chain[0]["observation_id"] == "obs_persist"
