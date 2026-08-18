from app.cognition.belief_engine import BeliefEngine


def test_engine_connects_evidence_and_hypotheses():
    engine = BeliefEngine()
    result = engine.ingest("chrome", "status", "running", source="desktop", confidence=0.8)
    assert result.selected_value == "running"
    assert result.confidence > 0

    result = engine.ingest("chrome", "status", "stopped", source="process", confidence=0.95)
    assert result.selected_value == "stopped"
    assert "running" in result.alternatives
