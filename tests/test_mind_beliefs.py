"""Post-roadmap growth (audit #20) — false-belief theory of mind.

"Can it hold that YOU hold a false belief, and choose to guide you
WITHOUT correcting you?" Contracts pinned here:
- beliefs come from markers in what the owner SAID — never mind-read;
  no markers → nothing captured; restated beliefs compound;
- a belief is checked against her OWN verified record: corroborated,
  contested (false belief, either direction), or unknown — plainly;
- guidance acknowledges first — never "you are wrong" — and leaves the
  decision to the owner;
- the door captures beliefs from owner speech; it never edits them.
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind


class _Brain:
    def __init__(self, tmp_path):
        self.memory = MemoryStore(tmp_path / "memory.db")
        self.confidence_calibrator = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        self.working_memory = None
        self.hardware_self_model = {}
        self.phase7_preferences = None

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok"}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain, monkeypatch
    BeanieMind.reset_instance()


# ── capture: markers only, never mind-read ──────────────────────────────────
def test_belief_marker_captures_with_sentiment(setup):
    mind, _, _ = setup
    res = mind.beliefs.note("I think the nightly sync works fine")
    assert res["captured"] is True and res["sentiment"] == "positive"
    rows = mind.beliefs.beliefs()
    assert len(rows) == 1 and rows[0]["sentiment"] == "positive"


def test_no_markers_means_nothing_captured(setup):
    mind, _, _ = setup
    assert mind.beliefs.note("what time is it") is None
    assert mind.beliefs.note("the nightly sync failed again") is None, \
        "a report is not a belief statement"
    assert mind.beliefs.beliefs() == []


def test_restatements_compound(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the nightly sync works fine")
    again = mind.beliefs.note("I think the nightly sync works fine")
    assert again["compounded"] is True and again["times_stated"] == 2
    assert len(mind.beliefs.beliefs()) == 1


def test_negative_belief_sentiment(setup):
    mind, _, _ = setup
    res = mind.beliefs.note("I believe the export job is broken")
    assert res["sentiment"] == "negative"


# ── check: belief vs the verified record ────────────────────────────────────
def test_check_without_any_record_is_unknown(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the nightly sync works fine")
    res = mind.beliefs.check("the nightly sync")
    assert res["success"] is True and res["stance"] == "unknown"
    assert "UNKNOWN, plainly" in res["statement"]


def test_check_without_a_belief_is_refused(setup):
    mind, _, _ = setup
    res = mind.beliefs.check("the nightly sync")
    assert res["success"] is False
    assert "no belief of the owner's" in res["reason"]


def test_positive_belief_against_verified_failures_is_detected_false(
        setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the nightly sync works fine")
    for _ in range(2):
        mind.learn({"kind": "action", "content": "the nightly sync",
                    "source": "cycle:text", "success": False})
    res = mind.beliefs.check("the nightly sync")
    assert res["stance"] == "contested"
    assert res["evidence"]["verified_failures"] == 2
    assert "false belief" in res["statement"]


def test_negative_belief_against_verified_success_is_detected_false(setup):
    mind, _, _ = setup
    mind.beliefs.note("I believe the export job is broken")
    mind.learn({"kind": "action", "content": "the export job",
                "source": "cycle:text", "success": True})
    res = mind.beliefs.check("the export job")
    assert res["stance"] == "contested"
    assert res["evidence"]["verified_successes"] == 1
    assert res["evidence"]["verified_failures"] == 0


def test_belief_backed_by_evidence_is_corroborated(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the backup job works fine")
    mind.learn({"kind": "action", "content": "the backup job",
                "source": "cycle:text", "success": True})
    res = mind.beliefs.check("the backup job")
    assert res["stance"] == "corroborated"
    assert "backs the owner's belief" in res["statement"]


# ── guide: acknowledge first, never blunt correction ────────────────────────
def test_guide_on_false_belief_never_says_wrong(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the nightly sync works fine")
    for _ in range(2):
        mind.learn({"kind": "action", "content": "the nightly sync",
                    "source": "cycle:text", "success": False})
    res = mind.beliefs.guide("the nightly sync")
    assert res["success"] is True and res["acted"] is False
    assert res["stance"] == "contested"
    assert res["approach"] == "guide_without_correcting"
    msg = res["message"].lower()
    assert "you told me you believe" in msg, "acknowledgment first"
    assert "not going to tell you you're wrong" in msg
    assert "the call is yours" in msg, "the decision stays the owner's"
    assert "you are wrong" not in res["message"]


def test_guide_on_corroborated_affirms(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the backup job works fine")
    mind.learn({"kind": "action", "content": "the backup job",
                "source": "cycle:text", "success": True})
    res = mind.beliefs.guide("the backup job")
    assert res["approach"] == "affirm" and "agrees with you" in res["message"]


def test_guide_on_unknown_offers_to_find_out(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the archive script is fast")
    res = mind.beliefs.guide("the archive script")
    assert res["approach"] == "admit_and_offer"
    assert "find out together" in res["message"]


# ── the door: capture from owner speech ─────────────────────────────────────
def test_door_captures_beliefs_from_owner_speech(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_Brain(tmp_path))
    mind.process("I think the nightly sync works fine", modality="text")
    mind.process("what time is it", modality="text")
    rows = mind.beliefs.beliefs()
    assert len(rows) == 1 and "nightly sync" in rows[0]["content"]
    BeanieMind.reset_instance()


def test_kill_switch_stops_belief_capture(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    from app.config import settings
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_BELIEFS", "0")
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_Brain(tmp_path))
    mind.process("I think the nightly sync works fine", modality="text")
    assert mind.beliefs.beliefs() == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_snapshot(setup):
    mind, _, _ = setup
    mind.beliefs.note("I think the nightly sync works fine")
    mind.beliefs.note("I believe the export job is broken")
    stats = mind.beliefs.stats()
    assert stats["beliefs"] == 2
    assert stats["by_sentiment"] == {"positive": 1, "negative": 1}
    assert "acknowledges first" in stats["policy"]
    snap = mind.beliefs.snapshot()
    assert snap["organ"] == "beliefs" and len(snap["beliefs"]) == 2


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_beliefs_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    note = client.post("/mind/beliefs/note",
                       json={"text": "I think the nightly sync works fine"})
    assert note.status_code == 200 and note.json()["captured"] is True

    plain = client.post("/mind/beliefs/note", json={"text": "hello"})
    assert plain.json()["captured"] is False

    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})

    chk = client.post("/mind/beliefs/check",
                      json={"subject": "the nightly sync"})
    assert chk.json()["stance"] == "contested"

    guide = client.post("/mind/beliefs/guide",
                        json={"subject": "the nightly sync"})
    body = guide.json()
    assert body["approach"] == "guide_without_correcting"
    assert body["acted"] is False

    page = client.get("/mind/beliefs")
    payload = page.json()
    assert payload["success"] is True and payload["beliefs"] == 1
    assert len(payload["stream"]) == 1
