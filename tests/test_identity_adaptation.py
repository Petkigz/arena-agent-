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


def test_style_exposure_and_feedback_are_measurable_without_automatic_adaptation(tmp_path):
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=FakeOwnerDecisions())
    store.record_style_observation(
        trace_id="trace-exposure", evidence_ids=["style:exposure"], feedback="unknown"
    )
    store.record_style_observation(
        trace_id="trace-feedback", evidence_ids=["feedback:owner"], feedback="helpful"
    )
    metrics = store.style_metrics()
    assert metrics["total_observations"] == 2
    assert metrics["known_feedback_count"] == 1
    assert metrics["helpful_rate"] == 1.0
    assert metrics["measurement_status"] == "measured_with_explicit_feedback"
    assert metrics["adaptation_automatic"] is False
    assert metrics["quality_claim"] == "none"

    with pytest.raises(IdentityAdaptationError, match="unsupported style feedback"):
        store.record_style_observation(
            trace_id="trace-invalid-feedback", evidence_ids=["e"], feedback="excellent"
        )


def test_owner_soft_delete_resets_adaptation_without_erasing_audit_or_goals(tmp_path):
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=FakeOwnerDecisions())
    style = store.propose_style_change(
        {"verbosity": "detailed"}, reason="measured", trace_id="trace-style", evidence_ids=["e:style"]
    )
    unlinked = store.propose_purpose(
        title="Unlinked", description="An unlinked proposed purpose.", provenance="exploratory_proposal",
        trace_id="trace-unlinked", evidence_ids=["e:unlinked"],
    )
    linked = store.propose_purpose(
        title="Linked", description="An adopted purpose with an existing goal.", provenance="owner_requested",
        trace_id="trace-linked", evidence_ids=["e:linked"],
    )
    store.adopt_purpose(linked.proposal_id, owner_decision_id="owner-adopt")
    store.link_purpose_to_goal(linked.proposal_id, "goal-existing", trace_id="trace-link", evidence_ids=["e:goal"])
    with pytest.raises(IdentityAdaptationError, match="owner decision rejected"):
        store.clear_adaptive_state(
            owner_decision_id="not-owner", trace_id="trace-delete", evidence_ids=["e:delete"]
        )
    result = store.clear_adaptive_state(
        owner_decision_id="owner-delete", trace_id="trace-delete", evidence_ids=["e:delete"]
    )
    assert result["deletion_mode"] == "soft_clear"
    assert result["stable_profile_preserved"] is True
    assert result["audit_history_preserved"] is True
    assert result["goal_records_untouched"] is True
    assert store.style().style["verbosity"] == "standard"
    assert store.style_proposals()[0].status == "deleted"
    assert store.get_purpose_proposal(unlinked.proposal_id).status == "deleted"
    protected = store.get_purpose_proposal(linked.proposal_id)
    assert protected.status == "adopted" and protected.linked_goal_id == "goal-existing"


def test_longitudinal_feedback_can_create_only_a_reversible_style_proposal(tmp_path):
    store = IdentityAdaptationStore(tmp_path / "identity.db", owner_decisions=FakeOwnerDecisions())
    for index, feedback in enumerate(["not_helpful", "partially_helpful", "not_helpful"]):
        store.record_style_observation(
            trace_id=f"trace-feedback-{index}",
            evidence_ids=[f"feedback:{index}"],
            feedback=feedback,
        )
    suggestion = store.suggest_style_proposal_from_feedback(
        {"verbosity": "concise"},
        reason="owners requested shorter answers",
        trace_id="trace-suggestion",
        evidence_ids=["feedback:0", "feedback:1", "feedback:2"],
    )
    assert suggestion["status"] == "proposal_created"
    assert suggestion["requires_owner_decision"] is True
    assert suggestion["proposal"]["status"] == "proposed"
    assert store.style().style["verbosity"] == "standard"

    insufficient = IdentityAdaptationStore(tmp_path / "insufficient.db", owner_decisions=FakeOwnerDecisions())
    insufficient.record_style_observation(trace_id="trace-one", evidence_ids=["feedback:one"], feedback="not_helpful")
    result = insufficient.suggest_style_proposal_from_feedback(
        {"verbosity": "concise"}, reason="not enough data", trace_id="trace-insufficient", evidence_ids=["feedback:one"]
    )
    assert result["status"] == "insufficient_data"
    assert result["result_type"] == "UNKNOWN"


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
    linked = store.link_purpose_to_goal(
        proposal.proposal_id, "goal-purpose-1", trace_id="trace-link", evidence_ids=["e:goal-link"]
    )
    assert linked.linked_goal_id == "goal-purpose-1"
    with pytest.raises(IdentityAdaptationError, match="different goal"):
        store.link_purpose_to_goal(
            proposal.proposal_id, "goal-purpose-2", trace_id="trace-link-2", evidence_ids=["e:goal-link-2"]
        )

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


def test_adopted_purpose_bridge_creates_only_an_evaluated_goal(tmp_path):
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime(db_path=str(tmp_path / "runtime.db"))
    proposal = runtime.identity_adaptation.propose_purpose(
        title="Review recovery evidence",
        description="Inspect bounded recovery evidence without changing policy.",
        provenance="owner_requested",
        trace_id="trace-purpose-proposal",
        evidence_ids=["e:purpose"],
    )
    decision = runtime.owner_decisions.issue(
        "purpose_adoption",
        {"expected_change_types": [f"purpose_adoption:{proposal.proposal_id}"]},
    )
    runtime.identity_adaptation.adopt_purpose(
        proposal.proposal_id,
        owner_decision_id=decision.decision_id,
    )

    result = runtime.create_goal_from_adopted_purpose(
        proposal.proposal_id,
        trace_id="trace-purpose-goal",
        evidence_ids=["e:goal-bridge"],
    )

    assert result["created_now"] is True
    assert result["execution_authorized"] is False
    assert result["planning_approval_required"] is True
    assert result["goal"]["status"] == "evaluated"
    assert result["goal"]["source"] == "owner_directive"
    assert result["goal"]["max_action_level"] == 2
    assert runtime.goal_generator.get_next_goal() is None
    linked = runtime.identity_adaptation.get_purpose_proposal(proposal.proposal_id)
    assert linked.linked_goal_id == result["goal"]["goal_id"]

    repeated = runtime.create_goal_from_adopted_purpose(
        proposal.proposal_id,
        trace_id="trace-purpose-goal-repeat",
        evidence_ids=["e:goal-bridge-repeat"],
    )
    assert repeated["created_now"] is False
    assert repeated["goal"]["goal_id"] == result["goal"]["goal_id"]
    assert repeated["execution_authorized"] is False


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


def test_restart_restores_functional_style_without_changing_stable_identity(tmp_path):
    path = tmp_path / "identity-restart.db"
    decisions = FakeOwnerDecisions()
    first = IdentityAdaptationStore(path, owner_decisions=decisions)
    stable_digest = first.profile().content_digest
    proposal = first.propose_style_change(
        {"verbosity": "detailed"},
        reason="repeated request for fuller explanations",
        trace_id="trace-restart-style",
        evidence_ids=["feedback:restart"],
    )
    first.approve_style_change(proposal.proposal_id, owner_decision_id="owner-style-restart")

    restarted = IdentityAdaptationStore(path, owner_decisions=decisions)
    assert restarted.profile().content_digest == stable_digest
    assert restarted.profile().revision == 0
    assert restarted.style().revision == 1
    assert restarted.style().style["verbosity"] == "detailed"


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
