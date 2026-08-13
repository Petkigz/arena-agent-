from app.cognition.beliefs import BeliefStore


def test_matching_evidence_strengthens_belief():
    store = BeliefStore()
    first = store.observe("chrome", "status", "running", source="desktop", confidence=0.8)
    second = store.observe("chrome", "status", "running", source="process", confidence=0.7)
    assert second.value == "running"
    assert second.confidence >= first.confidence
    assert len(second.evidence) == 2


def test_stronger_conflicting_evidence_can_revise_belief():
    store = BeliefStore()
    store.observe("chrome", "status", "running", source="desktop", confidence=0.4)
    belief = store.observe("chrome", "status", "stopped", source="process", confidence=0.95)
    assert belief.value == "stopped"
    assert belief.confidence > 0.5


def test_contradictions_are_visible():
    store = BeliefStore()
    store.observe("chrome", "status", "running", source="desktop", confidence=0.8)
    store.observe("chrome", "status", "stopped", source="process", confidence=0.4)
    assert len(store.contradictions("chrome")) == 1


def test_stale_evidence_loses_weight():
    store = BeliefStore()
    belief = store.observe("service", "status", "running", source="monitor", confidence=1.0, half_life_seconds=1)
    assert belief.evidence[0].effective_confidence() > 0
