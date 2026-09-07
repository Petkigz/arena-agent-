import sqlite3

import pytest

from app.cognition.functional_affect import FunctionalAffectError, FunctionalAffectStore


def test_functional_affect_is_bounded_persistent_and_advisory(tmp_path):
    store = FunctionalAffectStore(tmp_path / "affect.db")
    initial = store.snapshot()
    assert initial.confidence == pytest.approx(0.5)
    updated = store.apply_signal(
        "uncertainty",
        0.8,
        source="verified_failure",
        trace_id="trace-1",
        evidence_ids=["evidence:failure"],
    )
    assert updated.uncertainty == pytest.approx(1.0)
    modifiers = store.advisory_modifiers()
    assert 0.85 <= modifiers["clarification_multiplier"] <= 1.15
    assert 0.85 <= modifiers["exploration_multiplier"] <= 1.15
    assert modifiers["bounded"] is True
    assert modifiers["advisory_only"] is True
    assert modifiers["authority"] == "none"

    reopened = FunctionalAffectStore(tmp_path / "affect.db")
    assert reopened.snapshot().uncertainty == pytest.approx(1.0)
    assert reopened.history()[0]["trace_id"] == "trace-1"


def test_affect_outcome_records_effect_measurement_without_claiming_causality(tmp_path):
    store = FunctionalAffectStore(tmp_path / "affect.db")
    record = store.record_outcome(
        trace_id="trace-outcome",
        outcome="verified_success",
        evidence_ids=["evidence:success"],
    )
    assert record["outcome_id"].startswith("affect_outcome_")
    assert record["affect_is_not_causal_proof"] is True
    with sqlite3.connect(tmp_path / "affect.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM affect_outcomes").fetchone()[0] == 1


def test_affect_rejects_unbounded_or_unsupported_updates(tmp_path):
    store = FunctionalAffectStore(tmp_path / "affect.db")
    with pytest.raises(FunctionalAffectError, match="unsupported affect field"):
        store.apply_signal("valence", 0.2, source="test", trace_id="t", evidence_ids=["e"])
    with pytest.raises(FunctionalAffectError, match="in \[-1, 1\]"):
        store.apply_signal("load", 2.0, source="test", trace_id="t", evidence_ids=["e"])
    with pytest.raises(FunctionalAffectError, match="evidence_ids"):
        store.apply_signal("load", 0.1, source="test", trace_id="t", evidence_ids=[])


def test_affect_store_rejects_unknown_schema(tmp_path):
    with sqlite3.connect(tmp_path / "unsupported.db") as conn:
        conn.execute(
            "CREATE TABLE affect_meta "
            "(singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL, vector_json TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, revision INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO affect_meta VALUES (1, 99, '{}', 'now', 0)")
    with pytest.raises(FunctionalAffectError, match="unsupported functional affect"):
        FunctionalAffectStore(tmp_path / "unsupported.db")
