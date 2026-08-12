from app.cognition.beliefs import BeliefStore


def test_matching_evidence_strengthens_belief():
    store = BeliefStore()
    first = store.observe("chrome", "status", "running", source="desktop", confidence=0.8)
    second = store.observe("chrome", "status", "running", source="process", confidence=0.7)
    assert second.value == "running"
    assert second.confidence >= first.confidence
    assert len(second.evidence) == 2


def test_stronger_conflicting_evidence_revises_belief():
    store = BeliefStore()
    store.observe("chrome", "status", "running", source="desktop", confidence=0.4)
    belief = store.observe("chrome", "status", "stopped", source="process", confidence=0.95)
    assert belief.value == "stopped"
    assert belief.confidence == 0.95


def test_contradictions_are_visible():
    store = BeliefStore()
    store.observe("chrome", "status", "running", source="desktop", confidence=0.8)
    store.observe("chrome", "status", "stopped", source="process", confidence=0.4)
    assert len(store.contradictions("chrome")) == 1
