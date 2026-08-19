from app.cognition.belief_engine import BeliefEngine
from app.cognition.source_types import SourceType


def test_engine_connects_evidence_and_hypotheses():
    engine = BeliefEngine()
    # Use canonical admissible source
    result = engine.ingest("chrome", "status", "running",
                           source=SourceType.SYSTEM_PROBE, observation_type="direct", confidence=0.8)
    assert result.has_belief is True
    assert result.belief_value == "running"
    assert result.belief_confidence > 0
    # Hypothesis also tracked
    assert result.hypothesis_value == "running"

    result = engine.ingest("chrome", "status", "stopped",
                           source=SourceType.OS_PROCESS_PROBE, observation_type="direct", confidence=0.95)
    # Stronger admissible source → belief updates
    assert result.belief_value == "stopped"
    assert "running" in result.alternatives


def test_engine_accepts_string_sources():
    """Backward compatibility: string sources are converted via SourceType.from_string()."""
    engine = BeliefEngine()
    result = engine.ingest("chrome", "status", "running",
                           source="os_process_probe", observation_type="direct", confidence=0.9)
    assert result.has_belief is True
    assert result.belief_value == "running"


def test_inadmissible_evidence_no_belief():
    """Inadmissible evidence creates hypothesis but NOT belief."""
    engine = BeliefEngine()
    result = engine.ingest("chrome", "status", "running",
                           source=SourceType.SELF_REPORTED, confidence=1.0,
                           observation_type="self_reported")
    # No admissible evidence → no belief
    assert result.has_belief is False
    assert result.belief_value is None
    assert result.belief_confidence == 0.0
    # But hypothesis is tracked
    assert result.hypothesis_value == "running"


def test_inadmissible_string_source():
    """String sources that map to inadmissible types are rejected."""
    engine = BeliefEngine()
    result = engine.ingest("chrome", "status", "running",
                           source="self_reported", confidence=1.0,
                           observation_type="self_reported")
    assert result.has_belief is False
    assert result.belief_value is None


def test_unknown_source_is_inadmissible():
    """Unknown sources (not in canonical enum) are inadmissible."""
    engine = BeliefEngine()
    result = engine.ingest("chrome", "status", "running",
                           source="some_random_source", observation_type="direct", confidence=0.9)
    assert result.has_belief is False
    assert result.belief_value is None
    # But tracked as hypothesis
    assert result.hypothesis_value == "running"


def test_tool_output_is_inadmissible():
    """tool:* sources are classified as TOOL_OUTPUT (inadmissible)."""
    engine = BeliefEngine()
    result = engine.ingest("server", "health", "degraded",
                           source="tool:health_check", confidence=0.8,
                           observation_type="inferred")
    assert result.has_belief is False
    assert result.hypothesis_value == "degraded"


def test_hypothesis_never_masquerades_as_belief():
    """Even if hypothesis ranks highest, belief must come from admissible evidence."""
    engine = BeliefEngine()
    # Admissible: Chrome = stopped
    engine.ingest("chrome", "status", "stopped",
                  source=SourceType.OS_PROCESS_PROBE,
                  confidence=0.9, observation_type="direct")
    # Inadmissible: Chrome = running (strong claim)
    result = engine.ingest("chrome", "status", "running",
                           source=SourceType.EXECUTION_RESULT, confidence=1.0,
                           observation_type="self_reported")
    # Belief must be "stopped" (from admissible evidence)
    assert result.belief_value == "stopped"
    assert result.has_belief is True
    # Hypothesis might rank "running" higher but that doesn't change the belief
    assert result.belief_value != result.hypothesis_value or result.belief_confidence > 0
