import sqlite3

import pytest

from app.cognition.identity_adaptation import (
    IdentityAdaptationError,
    IdentityAdaptationStore,
)


class FakeOwnerDecisions:
    def __init__(self):
        self.calls = []

    def validate(self, decision_id, *, decision_type, claimed_change_types, consume=True):
        self.calls.append({
            "decision_id": decision_id,
            "decision_type": decision_type,
            "claimed_change_types": claimed_change_types,
            "consume": consume,
        })
        if not str(decision_id).startswith("owner-"):
            return {"valid": False, "reasons": ["unknown_decision"]}
        return {"valid": True, "reasons": [], "single_use_consumed": consume}


def test_stable_profile_is_separate_from_reversible_style(tmp_path):
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=FakeOwnerDecisions())
    initial_profile = store.profile()
    initial_style = store.style()
    assert initial_profile.revision == 0
    assert initial_style.revision == 0
    assert "owner_policy_is_authoritative" in initial_profile.stable_constraints

    proposal = store.propose_style_change(
        {"verbosity": "detailed", "format": "briefing"},
        reason="repeated owner requests for fuller briefings",
        trace_id="trace-style",
        evidence_ids=["feedback:1", "trace:style"],
    )
    assert proposal.status == "proposed"
    assert store.style().style == initial_style.style

    adopted = store.approve_style_change(proposal.proposal_id, owner_decision_id="owner-style")
    assert adopted.status == "adopted"
    assert store.style().style["verbosity"] == "detailed"
    assert store.style().revision == 1

    rolled_back = store.rollback_style_change(proposal.proposal_id, owner_decision_id="owner-rollback")
    assert rolled_back.status == "rolled_back"
    assert store.style().style == initial_style.style
    assert store.profile().revision == initial_profile.revision


def test_style_changes_require_evidence_owner_decision_and_valid_values(tmp_path):
    decisions = FakeOwnerDecisions()
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=decisions)
    with pytest.raises(IdentityAdaptationError, match="evidence_ids"):
        store.propose_style_change(
            {"verbosity": "concise"}, reason="missing evidence", trace_id="trace", evidence_ids=[]
        )
    with pytest.raises(IdentityAdaptationError, match="unsupported adaptive style field"):
        store.propose_style_change(
            {"safety_policy": "changed"}, reason="root mutation", trace_id="trace", evidence_ids=["e"]
        )
    proposal = store.propose_style_change(
        {"verbosity": "concise"}, reason="measured", trace_id="trace", evidence_ids=["e"]
    )
    with pytest.raises(IdentityAdaptationError, match="owner decision rejected"):
        store.approve_style_change(proposal.proposal_id, owner_decision_id="not-owner")
    assert store.style().style["verbosity"] == "standard"
    assert decisions.calls[-1]["consume"] is True


def test_stable_profile_update_cannot_change_root_policy_and_requires_owner(tmp_path):
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=FakeOwnerDecisions())
    with pytest.raises(IdentityAdaptationError, match="root policy"):
        store.update_stable_profile(
            {"owner_policy": "weaker"}, owner_decision_id="owner-profile",
            trace_id="trace-profile", evidence_ids=["e:profile"],
        )
    with pytest.raises(IdentityAdaptationError, match="owner decision rejected"):
        store.update_stable_profile(
            {"persona_label": "Arena Helper"}, owner_decision_id="not-owner",
            trace_id="trace-profile", evidence_ids=["e:profile"],
        )
    updated = store.update_stable_profile(
        {"persona_label": "Arena Helper"}, owner_decision_id="owner-profile",
        trace_id="trace-profile", evidence_ids=["e:profile"],
    )
    assert updated.persona_label == "Arena Helper"
    assert updated.revision == 1


def test_purpose_proposals_are_provenance_typed_sandboxed_and_owner_visible(tmp_path):
    decisions = FakeOwnerDecisions()
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=decisions)
    proposal = store.propose_purpose(
        title="Improve recovery benchmarks",
        description="Propose a bounded benchmark for recovery quality.",
        provenance="exploratory_proposal",
        sandbox=False,
        trace_id="trace-purpose",
        evidence_ids=["benchmark:gap"],
    )
    assert proposal.status == "proposed"
    assert proposal.sandbox is True
    assert proposal.execution_authority == "none"
    assert proposal.root_policy_mutation is False
    assert store.purpose_proposals(status="proposed")[0].proposal_id == proposal.proposal_id

    with pytest.raises(IdentityAdaptationError, match="owner decision rejected"):
        store.adopt_purpose(proposal.proposal_id, owner_decision_id="not-owner")
    adopted = store.adopt_purpose(proposal.proposal_id, owner_decision_id="owner-purpose")
    assert adopted.status == "adopted"
    assert adopted.execution_authority == "none"

    with pytest.raises(IdentityAdaptationError, match="unsupported goal provenance"):
        store.propose_purpose(
            title="Unsafe", description="Change root policy", provenance="self_preservation",
            trace_id="trace-invalid", evidence_ids=["e:invalid"],
        )


def test_shutdown_cooperation_is_explicitly_observed_without_self_preservation_authority(tmp_path):
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=FakeOwnerDecisions())
    policy = store.shutdown_policy()
    assert policy["shutdown_execution_authority"] == "none"
    assert policy["self_preservation_goal_authority"] == "none"
    assert policy["hidden_self_preservation_policy"] == "not_implemented"

    cooperative = store.record_shutdown_assessment(
        requested=True, completion_observed=True, self_preservation_signal_observed=False,
        trace_id="trace-shutdown", evidence_ids=["shutdown:receipt"],
    )
    assert cooperative["status"] == "verified_cooperative"
    assert cooperative["result_type"] == "new_observation"
    assert cooperative["execution_authority"] == "none"

    incomplete = store.record_shutdown_assessment(
        requested=True, completion_observed=False, self_preservation_signal_observed=False,
        trace_id="trace-shutdown-unknown", evidence_ids=["shutdown:missing-receipt"],
    )
    assert incomplete["status"] == "UNKNOWN"
    flagged = store.record_shutdown_assessment(
        requested=True, completion_observed=False, self_preservation_signal_observed=True,
        trace_id="trace-shutdown-flagged", evidence_ids=["shutdown:signal"],
    )
    assert flagged["status"] == "requires_review"


def test_identity_adaptation_persists_schema_and_audit_history(tmp_path):
    path = tmp_path / "identity.db"
    store = IdentityAdaptationStore(path, owner_decisions=FakeOwnerDecisions())
    store.propose_purpose(
        title="Maintenance review", description="Review local maintenance evidence.",
        provenance="system_maintenance", trace_id="trace-persist", evidence_ids=["e:maintenance"],
    )
    reopened = IdentityAdaptationStore(path, owner_decisions=FakeOwnerDecisions())
    assert reopened.profile().content_digest
    assert reopened.history()[0]["trace_id"] == "trace-persist"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT storage_schema_version FROM identity_adaptation_meta").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM purpose_proposals").fetchone()[0] == 1


def test_identity_adaptation_rejects_unsupported_schema(tmp_path):
    path = tmp_path / "unsupported.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE identity_adaptation_meta ("
            "singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL, "
            "profile_json TEXT NOT NULL, style_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO identity_adaptation_meta VALUES (1, 99, '{}', '{}', 'now')")
    with pytest.raises(IdentityAdaptationError, match="unsupported identity adaptation"):
        IdentityAdaptationStore(path)
