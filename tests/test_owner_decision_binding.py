"""Expected identity changes must be bound to signed owner decisions.

Declaring a change "expected" suppresses discontinuity findings, so it is an
authority claim: it fails closed without a valid, unused, unrevoked,
content-digested owner decision that authorizes exactly the claimed change
types. Decisions are single-use by default.
"""
import json
import sqlite3

from app.cognition.identity_continuity import IdentityContinuityLedger
from app.cognition.owner_decisions import OwnerDecisionStore


def state(**kw):
    d = {"claim_predicates": ["authority.owner_policy"], "active_commitment_sources": ["project:p1"],
         "interface_ids": ["desktop_screen"], "tool_count": 150, "owner_policy_revision": 4}
    d.update(kw)
    return d


def make(tmp_path):
    decisions = OwnerDecisionStore(tmp_path / "od.db")
    ledger = IdentityContinuityLedger(tmp_path / "id.db", owner_decisions=decisions)
    return decisions, ledger


def test_decision_is_single_use(tmp_path):
    decisions, _ = make(tmp_path)
    decision = decisions.issue("expected_identity_change", {"expected_change_types": ["provider_model_changed"]})
    first = decisions.validate(decision.decision_id, decision_type="expected_identity_change",
                               claimed_change_types=["provider_model_changed"])
    assert first["valid"] is True and first["single_use_consumed"] is True
    second = decisions.validate(decision.decision_id, decision_type="expected_identity_change",
                                claimed_change_types=["provider_model_changed"])
    assert second["valid"] is False and "decision_already_used" in second["reasons"]


def test_revoked_or_unknown_or_unauthorized_decisions_are_invalid(tmp_path):
    decisions, _ = make(tmp_path)
    decision = decisions.issue("expected_identity_change", {"expected_change_types": ["provider_model_changed"]})
    decisions.revoke(decision.decision_id)
    revoked = decisions.validate(decision.decision_id, decision_type="expected_identity_change",
                                 claimed_change_types=["provider_model_changed"])
    assert revoked["valid"] is False and "decision_revoked" in revoked["reasons"]

    unknown = decisions.validate("od_missing", decision_type="expected_identity_change")
    assert unknown["valid"] is False and "unknown_decision" in unknown["reasons"]

    other = decisions.issue("expected_identity_change", {"expected_change_types": ["provider_model_changed"]})
    overreach = decisions.validate(other.decision_id, decision_type="expected_identity_change",
                                   claimed_change_types=["capability_count_decreased"])
    assert overreach["valid"] is False
    assert "change_type_not_authorized:capability_count_decreased" in overreach["reasons"]


def test_tampered_decision_content_fails_digest(tmp_path):
    decisions, _ = make(tmp_path)
    decision = decisions.issue("expected_identity_change", {"expected_change_types": ["provider_model_changed"]})
    with sqlite3.connect(decisions.db_path) as conn:
        conn.execute("UPDATE owner_decisions SET payload_json=? WHERE decision_id=?",
                     (json.dumps({"expected_change_types": ["missing_self_claims", "capability_count_decreased"]}), decision.decision_id))
        conn.commit()
    tampered = decisions.validate(decision.decision_id, decision_type="expected_identity_change",
                                  claimed_change_types=["missing_self_claims"])
    assert tampered["valid"] is False and "content_digest_mismatch" in tampered["reasons"]


def test_expected_changes_fail_closed_without_a_decision(tmp_path):
    decisions, ledger = make(tmp_path)
    ledger.checkpoint(state(), "boot-1")
    report = ledger.checkpoint(state(tool_count=100), "boot-2",
                               expected_change_types=["capability_count_decreased"])  # no decision id
    assert report["continuous"] is False  # the change stays a finding
    assert report["expected_changes"] == []
    assert "missing_owner_decision" in report["expected_change_validation"]["reasons"]
    assert report["owner_decision_id"] is None


def test_expected_changes_fail_closed_without_a_decision_store(tmp_path):
    ledger = IdentityContinuityLedger(tmp_path / "bare.db")  # no store configured
    ledger.checkpoint(state(), "boot-1")
    report = ledger.checkpoint(state(tool_count=100), "boot-2",
                               expected_change_types=["capability_count_decreased"],
                               owner_decision_id="od_whatever")
    assert report["continuous"] is False
    assert "decision_store_unavailable" in report["expected_change_validation"]["reasons"]


def test_valid_decision_honors_expected_change_once(tmp_path):
    decisions, ledger = make(tmp_path)
    ledger.checkpoint(state(), "boot-1")
    decision = decisions.issue("expected_identity_change", {"expected_change_types": ["capability_count_decreased"]})
    report = ledger.checkpoint(state(tool_count=100), "boot-2",
                               expected_change_types=["capability_count_decreased"],
                               owner_decision_id=decision.decision_id)
    assert report["continuous"] is True and report["issues"] == []
    assert report["expected_changes"][0]["type"] == "capability_count_decreased"
    assert report["owner_decision_id"] == decision.decision_id
    # The decision is consumed: a second checkpoint expecting another change
    # with the same decision id fails closed.
    again = ledger.checkpoint(state(tool_count=90), "boot-3",
                              expected_change_types=["capability_count_decreased"],
                              owner_decision_id=decision.decision_id)
    assert again["continuous"] is False
    assert "decision_already_used" in again["expected_change_validation"]["reasons"]


def test_checkpoint_row_records_the_bound_decision(tmp_path):
    decisions, ledger = make(tmp_path)
    ledger.checkpoint(state(), "boot-1")
    decision = decisions.issue("expected_identity_change", {"expected_change_types": ["provider_model_changed"]})
    ledger.checkpoint(state(provider_model="model-b"), "boot-2",
                      expected_change_types=["provider_model_changed"],
                      owner_decision_id=decision.decision_id)
    with sqlite3.connect(ledger.path) as conn:
        rows = conn.execute(
            "SELECT boot_id, owner_decision_id FROM identity_checkpoints WHERE owner_decision_id IS NOT NULL"
        ).fetchall()
    assert rows == [("boot-2", decision.decision_id)]


def test_owner_decision_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.cognition.runtime import CognitiveRuntime
    import app.cognition.owner_decisions as od_module

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    runtime = CognitiveRuntime.get_instance()
    monkeypatch.setattr(runtime, "owner_decisions", OwnerDecisionStore(tmp_path / "od.db"))
    monkeypatch.setattr(od_module, "owner_decision_store", runtime.owner_decisions)
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    bad = client.post("/owner-control/owner-decisions", headers=headers,
                      json={"decision_type": "promote_self_awareness", "expected_change_types": ["x"]})
    assert bad.status_code == 200 and bad.json()["success"] is False

    empty = client.post("/owner-control/owner-decisions", headers=headers,
                        json={"expected_change_types": []})
    assert empty.json()["success"] is False

    issued = client.post("/owner-control/owner-decisions", headers=headers,
                         json={"expected_change_types": ["provider_model_changed"], "note": "switching to 14B"})
    body = issued.json()
    assert body["success"] is True
    decision_id = body["decision"]["decision_id"]
    assert body["decision"]["status"] == "active" and len(body["decision"]["content_digest"]) == 64

    listed = client.get("/owner-control/owner-decisions", headers=headers)
    assert any(d["decision_id"] == decision_id for d in listed.json()["decisions"])

    revoked = client.post(f"/owner-control/owner-decisions/{decision_id}/revoke", headers=headers)
    assert revoked.json()["decision"]["status"] == "revoked"

    missing = client.post("/owner-control/owner-decisions/od_none/revoke", headers=headers)
    assert missing.status_code == 404
