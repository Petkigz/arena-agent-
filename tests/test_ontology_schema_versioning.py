"""Ontology schema versioning, migration, and owner-authorized rollback."""

import sqlite3

import pytest

from app.cognition.ontology_schema import OntologySchemaError, OntologySchemaStore
from app.cognition.owner_decisions import OwnerDecisionStore


def _decision(store, operation):
    return store.issue(
        "ontology_schema_change",
        {"expected_change_types": [operation]},
        note=operation,
    )


def test_schema_changes_are_staged_then_owner_authorized(tmp_path):
    decisions = OwnerDecisionStore(tmp_path / "owner.db")
    schemas = OntologySchemaStore(tmp_path / "ontology.db", owner_decisions=decisions)

    initial = schemas.current()
    staged = schemas.propose(
        {
            "ontology_schema_version": 1,
            "entities": {"document": {"required": ["document_id"]}},
            "relations": {"supports": {"from": "document", "to": "claim"}},
            "epistemic_fields": {"source": "required", "observation_type": "required"},
        },
        note="add explicit document and claim relation",
    )

    assert initial.revision == 1
    assert staged.revision == 2
    assert staged.parent_revision == initial.revision
    assert staged.status == "staged"
    assert schemas.current().revision == initial.revision

    with pytest.raises(PermissionError):
        schemas.activate(staged.revision, owner_decision_id=None)
    assert schemas.current().revision == initial.revision

    decision = _decision(decisions, "activate_ontology_schema")
    active = schemas.activate(staged.revision, owner_decision_id=decision.decision_id)
    assert active.revision == staged.revision
    assert schemas.current().digest == staged.digest
    assert schemas.events()[-1]["event_type"] == "migrate"


def test_rollback_is_append_only_and_owner_authorized(tmp_path):
    decisions = OwnerDecisionStore(tmp_path / "owner.db")
    schemas = OntologySchemaStore(tmp_path / "ontology.db", owner_decisions=decisions)
    revision_two = schemas.propose({"ontology_schema_version": 1, "entities": {"file": {}}, "relations": {}})
    schemas.activate(
        revision_two.revision,
        owner_decision_id=_decision(decisions, "activate_ontology_schema").decision_id,
    )
    revision_three = schemas.propose({"ontology_schema_version": 1, "entities": {"file": {}, "folder": {}}, "relations": {}})
    schemas.activate(
        revision_three.revision,
        owner_decision_id=_decision(decisions, "activate_ontology_schema").decision_id,
    )

    rolled_back = schemas.rollback(
        revision_two.revision,
        owner_decision_id=_decision(decisions, "rollback_ontology_schema").decision_id,
        note="revert incompatible folder relation",
    )

    assert rolled_back.revision == revision_two.revision
    assert schemas.current().revision == revision_two.revision
    assert len(schemas.revisions()) == 3
    assert [event["event_type"] for event in schemas.events()] == [
        "initialize", "migrate", "migrate", "rollback"
    ]
    assert schemas.events()[-1]["previous_revision"] == revision_three.revision


def test_wrong_or_reused_owner_decision_cannot_change_schema(tmp_path):
    decisions = OwnerDecisionStore(tmp_path / "owner.db")
    schemas = OntologySchemaStore(tmp_path / "ontology.db", owner_decisions=decisions)
    staged = schemas.propose({"ontology_schema_version": 1, "entities": {"claim": {}}, "relations": {}})

    wrong = decisions.issue(
        "ontology_schema_change",
        {"expected_change_types": ["rollback_ontology_schema"]},
    )
    with pytest.raises(PermissionError):
        schemas.activate(staged.revision, owner_decision_id=wrong.decision_id)
    assert schemas.current().revision == 1

    right = _decision(decisions, "activate_ontology_schema")
    schemas.activate(staged.revision, owner_decision_id=right.decision_id)
    next_staged = schemas.propose(
        {"ontology_schema_version": 1, "entities": {"claim": {}, "source": {}}, "relations": {}}
    )
    with pytest.raises(PermissionError):
        schemas.activate(next_staged.revision, owner_decision_id=right.decision_id)
    assert schemas.current().revision == staged.revision


def test_ontology_schema_persists_across_reopen_and_rejects_unknown_store_version(tmp_path):
    decisions = OwnerDecisionStore(tmp_path / "owner.db")
    db_path = tmp_path / "ontology.db"
    schemas = OntologySchemaStore(db_path, owner_decisions=decisions)
    staged = schemas.propose(
        {"ontology_schema_version": 1, "entities": {"claim": {}}, "relations": {}}
    )
    schemas.activate(
        staged.revision,
        owner_decision_id=_decision(decisions, "activate_ontology_schema").decision_id,
    )
    reopened = OntologySchemaStore(db_path, owner_decisions=decisions)
    assert reopened.current().revision == staged.revision
    assert reopened.events()[-1]["event_type"] == "migrate"

    with sqlite3.connect(tmp_path / "unsupported.db") as conn:
        conn.execute(
            "CREATE TABLE ontology_store_meta (singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO ontology_store_meta VALUES (1, 99)")
    with pytest.raises(OntologySchemaError, match="unsupported ontology store"):
        OntologySchemaStore(tmp_path / "unsupported.db", owner_decisions=decisions)


def test_ontology_schema_rejects_missing_or_unsupported_versions(tmp_path):
    decisions = OwnerDecisionStore(tmp_path / "owner.db")
    schemas = OntologySchemaStore(tmp_path / "ontology.db", owner_decisions=decisions)

    with pytest.raises(ValueError, match="missing version|ambiguous"):
        schemas.propose({"entities": {}, "relations": {}})
    with pytest.raises(ValueError, match="unsupported ontology_schema_version"):
        schemas.propose({"ontology_schema_version": 99, "entities": {}, "relations": {}})
