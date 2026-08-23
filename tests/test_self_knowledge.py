"""Evidence-linked self-knowledge and conservative agency attribution."""

from __future__ import annotations

from app.cognition.self_knowledge import SelfKnowledgeLedger


def test_self_claim_requires_supported_provenance(tmp_path):
    ledger = SelfKnowledgeLedger(tmp_path / "self.db")

    try:
        ledger.assert_claim(
            "capability.camera", True,
            source_type="self_report", evidence=["I said so"], confidence=1.0,
        )
        assert False, "unsupported self-report source should fail"
    except ValueError:
        pass

    try:
        ledger.assert_claim(
            "capability.camera", True,
            source_type="capability_probe", evidence=[], confidence=1.0,
        )
        assert False, "evidence-free claim should fail"
    except ValueError:
        pass


def test_claim_revision_preserves_contradiction_history(tmp_path):
    ledger = SelfKnowledgeLedger(tmp_path / "self.db")
    first = ledger.assert_claim(
        "capability.camera", True,
        source_type="capability_probe", evidence=["camera probe opened"], confidence=0.9,
    )
    second = ledger.assert_claim(
        "capability.camera", False,
        source_type="capability_probe", evidence=["camera probe unavailable"], confidence=1.0,
    )

    current = ledger.current_claims()
    history = ledger.history("capability.camera")
    assert len(current) == 1
    assert current[0].claim_id == second.claim_id
    assert current[0].value is False
    assert history[1].claim_id == first.claim_id
    assert history[1].status == "superseded"
    assert second.supersedes_claim_id == first.claim_id


def test_identical_fresh_claim_is_idempotent(tmp_path):
    ledger = SelfKnowledgeLedger(tmp_path / "self.db")
    first = ledger.assert_claim(
        "capability.screen", True, source_type="capability_probe",
        evidence=["screen probe"], confidence=1.0, ttl_seconds=60,
    )
    repeated = ledger.assert_claim(
        "capability.screen", True, source_type="capability_probe",
        evidence=["screen probe"], confidence=1.0, ttl_seconds=60,
    )
    assert repeated.claim_id == first.claim_id
    assert len(ledger.history("capability.screen")) == 1


def test_inference_confidence_is_capped_and_expiry_is_visible(tmp_path):
    ledger = SelfKnowledgeLedger(tmp_path / "self.db")
    inferred = ledger.assert_claim(
        "performance.future_success", 0.95,
        source_type="inference", evidence=["three historical outcomes"],
        confidence=0.99, ttl_seconds=1,
    )

    assert inferred.confidence == 0.7
    assert inferred.fresh is True
    assert inferred.valid_until is not None


def test_temporal_proximity_never_proves_self_causation(tmp_path):
    ledger = SelfKnowledgeLedger(tmp_path / "self.db")
    temporal = ledger.attribute_change(
        "A file appeared after an action",
        execution_id="exec-1", execution_attempted=True,
        environment_observed=False, goal_verified=None,
        evidence=["timestamps are close"],
    )
    verified = ledger.attribute_change(
        "The exact authorized note exists",
        execution_id="exec-2", execution_attempted=True,
        environment_observed=True, goal_verified=True,
        evidence=["note id observed", "content hash matched"],
    )
    external = ledger.attribute_change(
        "Repository changed remotely", external_source="git remote",
        evidence=["remote commit signature"],
    )

    assert temporal.cause_type == "unknown"
    assert temporal.confidence < 0.5
    assert verified.cause_type == "self_caused"
    assert verified.confidence >= 0.9
    assert external.cause_type == "external"


def test_snapshot_explicitly_denies_consciousness_claim(tmp_path):
    ledger = SelfKnowledgeLedger(tmp_path / "self.db")
    ledger.assert_claim(
        "consciousness.evidence_available", False,
        source_type="capability_probe",
        evidence=["no phenomenal measurement registered"], confidence=1.0,
    )

    snapshot = ledger.snapshot()
    assert "not consciousness" in snapshot["note"].lower()
    assert snapshot["claims"][0]["value"] is False
