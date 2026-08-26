"""Owner Charter and owner model: the owner's values inform, never govern.

The charter is versioned, content-digested, owner-only, and consulted as
prompt context + goal alignment. The owner model counts real decisions
(approvals, question answers, active hours) with Wilson-bounded rates —
counted observations, not claims about intent.
"""
import json

import pytest

from app.cognition.owner_charter import (
    OwnerCharterStore,
    charter_priority_alignment,
)
from app.cognition.owner_model import OwnerModelStore


def make_charter_store(tmp_path):
    return OwnerCharterStore(tmp_path)


def test_charter_updates_are_versioned_and_digested(tmp_path):
    store = make_charter_store(tmp_path)
    first = store.update({"mission": "Serve the owner fully",
                          "priorities": ["hardware maintenance", "finances"]})
    assert first["success"] is True
    charter = store.get()
    assert charter.revision == 1 and len(charter.content_digest) == 64
    second = store.update({"mission": "Serve the owner fully and fast"})
    updated = store.get()
    assert updated.revision == 2
    assert updated.content_digest != charter.content_digest
    history = store.history()
    assert [h["revision"] for h in history] == [2, 1]  # append-only history
    # Unknown fields are rejected.
    with pytest.raises(ValueError):
        store.update({"ethics_override": True})


def test_tampered_charter_is_refused(tmp_path):
    store = make_charter_store(tmp_path)
    store.update({"mission": "original mission"})
    path = tmp_path / "owner_charter.json"
    raw = json.loads(path.read_text())
    raw["mission"] = "tampered mission"  # digest no longer matches
    path.write_text(json.dumps(raw))
    assert store.get().mission == ""  # refused; defaults returned


def test_priority_alignment_is_heuristic_and_absent_without_charter(tmp_path, monkeypatch):
    import app.cognition.owner_charter as oc
    monkeypatch.setattr(oc, "owner_charter_store", make_charter_store(tmp_path))
    assert charter_priority_alignment("anything") is None  # no charter → no signal
    oc.owner_charter_store.update({"priorities": ["server maintenance", "backup archive"]})
    high = charter_priority_alignment("run server maintenance now")
    low = charter_priority_alignment("cook lunch recipes")
    assert high is not None and high > 0
    assert low == 0.0


def test_owner_model_counts_decisions_with_wilson_bounds(tmp_path):
    store = OwnerModelStore(tmp_path / "om.db")
    for i in range(6):
        store.record_action_preference("browser_upload", True, f"q:approve{i}")
    for i in range(2):
        store.record_action_preference("browser_upload", False, f"q:deny{i}")
    for i in range(3):
        store.record_action_preference("delete_file", False, f"q:deny_x{i}")
    report = store.report()
    upload = next(p for p in report["counted_preferences"] if p["action_type"] == "browser_upload")
    assert upload["n"] == 8 and upload["approval_rate"] == 0.75
    assert 0.0 < upload["wilson_low"] < 0.75 < upload["wilson_high"] < 1.0
    assert "browser_upload" in report["consistently_approves"]  # 0.75 ≥ 0.7 with n≥3
    assert "delete_file" in report["consistently_denies"]
    assert "not claims about intent" in report["note"]


def test_owner_model_ingests_from_approval_and_question_stores(tmp_path):
    from app.cognition.approval_store import ApprovalStore
    from app.cognition.uncertainty_questions import OwnerQuestionStore

    approvals = ApprovalStore(tmp_path / "approvals.json")
    request_a = approvals.add("c1", "create_backup", {"sources": []}, "r")
    approvals.decide(request_a.action_id, True)
    request_b = approvals.add("c2", "delete_file", {"path": "/x"}, "r")
    approvals.decide(request_b.action_id, False)

    questions = OwnerQuestionStore(tmp_path / "q.db")
    question = questions.ask(proposal_id="p", action_type="browser_upload", payload={},
                             raw_confidence=0.5, calibrated_confidence=0.3, threshold=0.45, reason="low")
    questions.answer(question.question_id, "approve")

    store = OwnerModelStore(tmp_path / "om.db")
    imported = store.ingest_from_sources(approvals, questions)
    assert imported["approvals"] == 2 and imported["questions"] == 1
    # Idempotent re-ingest.
    again = store.ingest_from_sources(approvals, questions)
    assert again["approvals"] == 0 and again["questions"] == 0

    report = store.report()
    by_action = {p["action_type"]: p for p in report["counted_preferences"]}
    assert by_action["create_backup"]["approved"] == 1
    assert by_action["delete_file"]["denied"] == 1
    assert by_action["browser_upload"]["approved"] == 1
    assert report["peak_activity_hours_utc"]  # active hours counted


def test_owner_context_compact_rendering(tmp_path):
    store = OwnerModelStore(tmp_path / "om.db")
    assert store.compact_context() == ""  # nothing counted yet
    for i in range(4):
        store.record_action_preference("create_backup", True, f"e{i}")
    context = store.compact_context()
    assert "create_backup" in context


def test_charter_and_owner_model_endpoints(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.cognition.owner_charter as oc
    import app.cognition.owner_model as om

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    monkeypatch.setattr(oc, "owner_charter_store", OwnerCharterStore(tmp_path))
    monkeypatch.setattr(om, "owner_model_store", OwnerModelStore(tmp_path / "om.db"))
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    initial = client.get("/owner-control/charter", headers=headers).json()
    assert initial["success"] is True and initial["charter"]["revision"] == 0

    updated = client.put("/owner-control/charter", headers=headers, json={
        "mission": "full owner sovereignty",
        "priorities": ["stability", "speed"],
        "values": [{"name": "honesty", "description": "never fake evidence"}],
    }).json()
    assert updated["success"] is True and updated["charter"]["revision"] == 1

    bad_response = client.put("/owner-control/charter", headers=headers, json={"nope": 1})
    assert bad_response.status_code == 422  # unknown charter fields are rejected

    model = client.get("/owner-control/owner-model", headers=headers).json()
    assert model["success"] is True and model["counted_preferences"] == []
