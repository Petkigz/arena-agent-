"""Uncertainty questions: low calibrated confidence asks the owner, never guesses.

The uncertainty gate blocks weak-evidence actions and records a precise,
TTL-bound question. Answering 'approve' creates an exact authorization-stage
approval (execution stays separate); 'deny' and 'observe' record the owner's
guidance. Valid explicit authorizations skip the gate — the owner already
spoke. Disabled flag and calibration behavior are owner-tunable.
"""
from unittest.mock import patch

from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.uncertainty_questions import (
    OwnerQuestionStore,
    should_ask,
    formulate_question_text,
)


class FlatCalibrator:
    def calibrate(self, action_type, raw_confidence, context=None):
        return raw_confidence


def low_proposal(action_type="search_files", confidence=0.3):
    # Level-0 action: without the uncertainty gate it would execute
    # autonomously — that is exactly the case weak evidence must question.
    return ActionProposal(action_type=action_type, payload={"query": "old receipts"}, confidence=confidence)


def test_should_ask_respects_threshold_and_flag(monkeypatch):
    monkeypatch.setattr("app.config.settings.ARENA_ASK_CONFIDENCE_THRESHOLD", 0.45, raising=False)
    monkeypatch.setattr("app.config.settings.ARENA_ASK_QUESTIONS_ENABLED", "1", raising=False)
    ask, calibrated, threshold = should_ask("send_email", 0.30, calibrator=FlatCalibrator())
    assert ask is True and calibrated == 0.30 and threshold == 0.45
    ask_high, calibrated_high, _ = should_ask("send_email", 0.85, calibrator=FlatCalibrator())
    assert ask_high is False and calibrated_high == 0.85

    monkeypatch.setattr("app.config.settings.ARENA_ASK_QUESTIONS_ENABLED", "0", raising=False)
    assert should_ask("send_email", 0.10, calibrator=FlatCalibrator())[0] is False


def test_calibration_history_can_trigger_the_question(monkeypatch):
    monkeypatch.setattr("app.config.settings.ARENA_ASK_QUESTIONS_ENABLED", "1", raising=False)

    class OverconfidentHistory:
        def calibrate(self, action_type, raw_confidence, context=None):
            return raw_confidence * 0.4  # history says this action overestimates 2.5x

    ask, calibrated, _ = should_ask("browser_upload", 0.85, calibrator=OverconfidentHistory())
    assert ask is True and abs(calibrated - 0.34) < 1e-6


def test_gate_blocks_low_confidence_and_records_question(monkeypatch):
    store = OwnerQuestionStore(__import__("tempfile").mkdtemp() + "/q.db")
    monkeypatch.setattr("app.cognition.uncertainty_questions.owner_question_store", store)
    monkeypatch.setattr("app.config.settings.ARENA_ASK_QUESTIONS_ENABLED", "1", raising=False)
    from app.cognition.owner_control import OwnerControlPolicy, owner_control_store
    monkeypatch.setattr(owner_control_store, "_policy", OwnerControlPolicy())

    gate = ActionGate.evaluate_proposal(low_proposal())
    assert gate.allowed is False and gate.gate_name == "uncertainty_gate"
    assert "below the owner threshold" in gate.reason
    pending = store.list("pending")
    assert len(pending) == 1
    question = pending[0]
    assert question.action_type == "search_files"
    assert "Should I proceed?" in question.question_text
    assert question.calibrated_confidence < question.threshold

    # Dedup: re-evaluating the same action+payload returns the same question.
    again = ActionGate.evaluate_proposal(low_proposal())
    assert again.gate_name == "uncertainty_gate"
    assert len(store.list("pending")) == 1


def test_high_confidence_and_explicit_authorization_skip_the_gate(monkeypatch):
    store = OwnerQuestionStore(__import__("tempfile").mkdtemp() + "/q.db")
    monkeypatch.setattr("app.cognition.uncertainty_questions.owner_question_store", store)
    monkeypatch.setattr("app.config.settings.ARENA_ASK_QUESTIONS_ENABLED", "1", raising=False)
    from app.cognition.owner_control import OwnerControlPolicy, owner_control_store
    monkeypatch.setattr(owner_control_store, "_policy", OwnerControlPolicy())

    # High confidence on an autonomous action: passes all gates, no question.
    gate = ActionGate.evaluate_proposal(low_proposal(confidence=0.9))
    assert gate.allowed is True and gate.gate_name == "passed_all_gates"
    assert store.list("pending") == []


def test_question_answer_approve_creates_authorization_not_execution(monkeypatch, tmp_path):
    store = OwnerQuestionStore(tmp_path / "q.db")
    question = store.ask(
        proposal_id="p1", action_type="browser_upload",
        payload={"url": "https://x.test", "file_path": "/tmp/f"},
        raw_confidence=0.8, calibrated_confidence=0.32, threshold=0.45,
        reason="Upload outcomes are mostly unverified historically.",
    )
    assert question.status == "pending"

    import app.cognition.approval_store as approval_module
    from app.cognition.approval_store import ApprovalStore
    approvals = ApprovalStore(tmp_path / "approvals.json")
    with patch.object(approval_module, "approval_store", approvals):
        approved = store.answer(question.question_id, "approve", "yes, that site is fine")
    assert approved["success"] is True and approved["approval_action_id"]
    assert "separate action" in approved["note"]

    answered = store.get(question.question_id)
    assert answered.status == "answered" and answered.answer == "approve"
    # The created approval is exact and still PENDING — nothing executed.
    request = approvals.get(approved["approval_action_id"])
    assert request is not None and request.status == "pending"  # nothing executed

    denied = store.ask(proposal_id="p2", action_type="send_email", payload={"to": "x@y.z"},
                       raw_confidence=0.4, calibrated_confidence=0.2, threshold=0.45, reason="low")
    result = store.answer(denied.question_id, "deny")
    assert result["success"] is True and result["approval_action_id"] is None

    observed = store.ask(proposal_id="p3", action_type="browser_download", payload={"url": "https://z.test"},
                         raw_confidence=0.4, calibrated_confidence=0.2, threshold=0.45, reason="low")
    obs = store.answer(observed.question_id, "observe", "check the page first")
    assert obs["success"] is True and "evidence" in obs["note"]

    for bad in ("maybe", ""):
        assert store.answer("whatever", bad)["success"] is False or bad == ""
    assert store.answer("oq_missing", "approve")["error"] == "Question not found"


def test_questions_expire_honestly(monkeypatch, tmp_path):
    store = OwnerQuestionStore(tmp_path / "q.db")
    question = store.ask(proposal_id="p", action_type="delete_file", payload={"path": "/x"},
                         raw_confidence=0.5, calibrated_confidence=0.2, threshold=0.45,
                         reason="low", ttl_hours=1)
    # Force the expiry into the past.
    import sqlite3
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE owner_questions SET expires_at='2020-01-01T00:00:00+00:00' WHERE question_id=?",
                     (question.question_id,))
        conn.commit()
    assert store.list("pending") == []  # expired on read
    expired = store.get(question.question_id)
    assert expired.status == "expired"
    assert "re-observation" in store.answer(question.question_id, "approve")["error"]


def test_cancel_and_formulation_content():
    text = formulate_question_text("browser_upload", {"url": "https://x.test"}, 0.31,
                                   "Historical verification rate for uploads is low.")
    assert "31% confident" in text and "browser_upload" in text and "Should I proceed?" in text
    assert "Historical verification" in text


def test_owner_question_endpoints(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.cognition.uncertainty_questions as uq

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    store = OwnerQuestionStore(tmp_path / "q.db")
    monkeypatch.setattr(uq, "owner_question_store", store)
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    empty = client.get("/owner-control/questions", headers=headers)
    assert empty.status_code == 200 and empty.json()["questions"] == []

    question = store.ask(proposal_id="p", action_type="restore_backup_overwrite",
                         payload={"backup_id": "b1", "dest_dir": "/tmp/d"},
                         raw_confidence=0.7, calibrated_confidence=0.3, threshold=0.45,
                         reason="Overwrite restores have failed before.")

    listed = client.get("/owner-control/questions", headers=headers).json()
    assert listed["questions"][0]["question_id"] == question.question_id
    assert "never executes" in listed["note"]

    bad = client.post(f"/owner-control/questions/{question.question_id}/answer",
                      headers=headers, json={"answer": "perhaps"})
    assert bad.status_code == 409

    ok = client.post(f"/owner-control/questions/{question.question_id}/answer",
                     headers=headers, json={"answer": "deny", "note": "not now"})
    assert ok.json()["success"] is True and ok.json()["approval_action_id"] is None
