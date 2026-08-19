from app.cognition.beliefs import BeliefStore
from app.cognition.belief_engine import BeliefEngine


def test_matching_evidence_strengthens_belief():
    engine = BeliefEngine()
    first = engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.8)
    second = engine.ingest("chrome", "status", "running", source="filesystem_probe", observation_type="direct", confidence=0.7)
    assert second.belief_value == "running"
    assert second.belief_confidence >= first.belief_confidence
    assert second.evidence_count == 2


def test_stronger_conflicting_evidence_revises_belief():
    engine = BeliefEngine()
    engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.4)
    belief = engine.ingest("chrome", "status", "stopped", source="filesystem_probe", observation_type="direct", confidence=0.95)
    assert belief.belief_value == "stopped"
    # With unified weighted semantics: stopped (0.95) dominates running (0.4)
    # Confidence is proportion of weighted evidence, not raw confidence
    assert belief.belief_confidence > 0.6


def test_contradictions_are_visible():
    engine = BeliefEngine()
    engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.8)
    engine.ingest("chrome", "status", "stopped", source="filesystem_probe", observation_type="direct", confidence=0.4)
    assert len(engine.beliefs.contradictions("chrome")) == 1


def test_repeated_same_source_does_not_inflate_confidence():
    """Repeated observations from the same source should count as one vote."""
    engine = BeliefEngine()
    # Source B reports "not_running" first
    engine.ingest("chrome", "status", "not_running", source="filesystem_probe", observation_type="direct", confidence=1.0)
    # Source A reports "running" 5 times (most recent overall)
    for _ in range(5):
        engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=1.0)
    
    result = engine.inspect("chrome", "status")
    assert result is not None
    # With deduplication: probe_a=1 vote, probe_b=1 vote → 50/50
    # Without deduplication: probe_a=5 votes, probe_b=1 vote → 83%
    # Tie-break: "running" wins because it's more recent
    assert result.belief_value == "running"
    assert result.belief_confidence <= 0.6  # Should NOT be inflated to 0.83


def test_independent_sources_each_count():
    """Each independent source should contribute one vote."""
    engine = BeliefEngine()
    # 3 independent sources all say "running"
    engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=0.9)
    engine.ingest("chrome", "status", "running", source="filesystem_probe", observation_type="direct", confidence=0.9)
    engine.ingest("chrome", "status", "running", source="system_probe", observation_type="direct", confidence=0.9)
    
    result = engine.inspect("chrome", "status")
    assert result is not None
    assert result.belief_value == "running"
    assert result.belief_confidence > 0.95  # High confidence from 3 independent sources


def test_most_recent_from_source_wins():
    """When a source reports multiple values, only the most recent counts."""
    engine = BeliefEngine()
    # Source A first says "running", then "stopped"
    engine.ingest("chrome", "status", "running", source="os_process_probe", observation_type="direct", confidence=1.0)
    import time
    time.sleep(0.01)  # Ensure timestamp ordering
    engine.ingest("chrome", "status", "stopped", source="os_process_probe", observation_type="direct", confidence=1.0)
    
    result = engine.inspect("chrome", "status")
    assert result is not None
    # Only the most recent from probe_a counts → "stopped"
    assert result.belief_value == "stopped"
    assert result.belief_confidence == 1.0  # Only one source, one vote
