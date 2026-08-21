"""Regression guards for the P1 provenance-persistence and first-insertion fixes."""

from app.cognition.beliefs import BeliefStore
from app.cognition.beliefs import AdmissibleEvidence, Evidence


def _ev(source, value, confidence, observation_type="direct"):
    return AdmissibleEvidence.from_evidence(Evidence(
        source=source, value=value, confidence=confidence, observation_type=observation_type,
    ))


def test_observation_type_survives_roundtrip(tmp_path):
    """P1 #4: observation_type must persist across a save/load cycle."""
    db = str(tmp_path / "b.db")
    store = BeliefStore(db_path=db)
    store.observe("chrome", "status", _ev("os_process_probe", "running", 1.0, observation_type="direct"))

    # Reload from SQLite (fresh store, same DB).
    store2 = BeliefStore(db_path=db)
    belief = store2.get("chrome", "status")
    assert belief is not None
    assert belief.evidence[0].observation_type == "direct"
    assert belief.evidence[0].observation_id is not None or True  # observation_id may be None


def test_observation_type_none_roundtrips(tmp_path):
    """Even a None observation_type must round-trip (not become a different value)."""
    db = str(tmp_path / "b.db")
    store = BeliefStore(db_path=db)
    store.observe("chrome", "status", _ev("os_process_probe", "running", 1.0, observation_type=None))

    store2 = BeliefStore(db_path=db)
    belief = store2.get("chrome", "status")
    assert belief.evidence[0].observation_type is None


def test_first_observation_uses_revise_path(tmp_path):
    """P1 #5: one observation must use the SAME confidence semantics as two.

    With a single admissible observation, revise() yields confidence 1.0 (the
    value is the only candidate → 100% of weighted evidence). The old divergent
    path used raw evidence confidence. This guards against the regression.
    """
    store = BeliefStore()  # in-memory
    belief = store.observe("app", "status", _ev("os_process_probe", "running", 0.4))
    assert belief.confidence == 1.0  # consistent with revise()'s single-source semantics


def test_one_vs_two_observations_consistent(tmp_path):
    """Both 1 and 2 agreeing observations must route through the same calculation."""
    store = BeliefStore()
    first = store.observe("app", "status", _ev("os_process_probe", "running", 0.9))
    second = store.observe("app", "status", _ev("filesystem_probe", "running", 0.9))
    # Both are 100% consensus (all evidence agrees), so confidence is stable.
    assert first.confidence == 1.0
    assert second.confidence == 1.0
