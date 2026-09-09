"""Phase 22 (Beanie AGI roadmap) — voice-first Beanie.

"Voice: primary. Text: backup. Visual UI: contextual window into the
mind. The complicated information exists when needed, not permanently."
Contracts pinned here:
- the presence vocabulary IS the design system's state machine
  (design/tokens.json → beanie.states); states outside it are refused —
  never invented;
- with no activity on record she reports idle honestly (never pretends
  to be busy);
- the context window is bounded and drawn from real ledgers —
  conversation, open asks, goals, unknowns, lessons;
- the voice turn enters the ONE mind like any modality, and the settled
  state is the verifier's word (success / error / nothing claimed);
- the door settles presence only on a definite verdict.
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


# ── the vocabulary is the design system's own ───────────────────────────────
def test_vocabulary_is_the_design_state_machine(setup):
    mind, _, _ = setup
    vocab = mind.presence.vocabulary
    for state in ("idle", "listening", "thinking", "speaking",
                  "success", "error"):
        assert state in vocab, f"the design machine defines {state}"
        assert vocab[state].get("label") and vocab[state].get("color")


def test_unknown_states_are_refused_never_invented(setup):
    mind, _, _ = setup
    res = mind.presence.note("levitating")
    assert res["success"] is False
    assert "never invented" in res["reason"]
    assert mind.presence.history() == []


# ── current state: real transitions, honest idle ────────────────────────────
def test_idle_is_honest_not_a_mask(setup):
    mind, _, _ = setup
    cur = mind.presence.current()
    assert cur["state"] == "idle" and cur["since"] is None
    assert "honestly" in cur["statement"]


def test_note_records_a_real_transition(setup):
    mind, _, _ = setup
    res = mind.presence.note("listening", detail="owner speaking")
    assert res["success"] is True and res["acted"] is False
    assert res["label"] == "Listening" and res["color"]
    cur = mind.presence.current()
    assert cur["state"] == "listening" and cur["since"] is not None
    assert len(mind.presence.history()) == 1


# ── the contextual window into the mind ─────────────────────────────────────
def test_context_window_shows_the_real_conversation(setup):
    mind, _, _ = setup
    mind.process("hello beanie", modality="text")
    window = mind.presence.context_window()
    conv = window["conversation"]
    assert isinstance(conv, list) and conv
    assert any("hello beanie" in str(e.get("summary")) for e in conv)
    assert "when needed" in window["policy"]


def test_context_window_shows_open_asks(setup):
    mind, _, _ = setup
    mind.authority.note("ask before sending emails")
    check = mind.authority.check("send an email to the team")
    assert check.get("lane") == "ask_first"
    window = mind.presence.context_window()
    assert window["open_asks"], "an open ask must surface when needed"


def test_context_window_shows_unknowns_and_lessons(setup):
    mind, _, _ = setup
    mind.curiosity.register("why does the sync stall", source="encounter")
    mind.imagination.compare("delete_file", False, source="test")
    mind.reflection.reflect_on({"kind": "action", "content": "deleted the file",
                                "success": False, "goal_type": "delete_file"})
    window = mind.presence.context_window()
    assert any("sync stall" in str(u.get("topic")) for u in window["unknowns"])
    assert window["lessons"], "a model-changing reflection is a lesson"


# ── the voice-primary door ──────────────────────────────────────────────────
class _VerifyingBrain(_Brain):
    def __init__(self, tmp_path, verified):
        super().__init__(tmp_path)
        self._verified = verified

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "done with it",
                "goal_verified": self._verified,
                "goal_lifecycle_state": "completed"}


def test_voice_turn_verified_success(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    turn = mind.presence.voice_turn("file the invoices")
    assert turn["success"] is True and turn["modality"] == "voice"
    assert turn["reply"] == "done with it"
    assert turn["state"] == "success" and turn["goal_verified"] is True
    # the transcript entered the ONE mind as a voice entry
    assert any(e["modality"] == "voice" for e in mind.entries(limit=5))
    BeanieMind.reset_instance()


def test_voice_turn_verified_failure_settles_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, False))
    turn = mind.presence.voice_turn("the nightly sync")
    assert turn["state"] == "error" and turn["goal_verified"] is False
    BeanieMind.reset_instance()


def test_voice_turn_no_verdict_claims_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_Brain(tmp_path))
    turn = mind.presence.voice_turn("what time is it")
    assert turn["state"] == "idle" and turn["goal_verified"] is None
    assert "nothing claimed" in turn["detail"]
    BeanieMind.reset_instance()


def test_voice_turn_empty_is_refused(setup):
    mind, _, _ = setup
    res = mind.presence.voice_turn("   ")
    assert res["success"] is False and "nothing was said" in res["reason"]


# ── the door settles presence only on a definite verdict ────────────────────
def test_door_settles_success_on_verified_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    mind.process("file the invoices", modality="text")
    states = [h["state"] for h in mind.presence.history()]
    assert states == ["success"] and mind.presence.current()["state"] == "success"
    BeanieMind.reset_instance()


def test_door_and_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    from app.config import settings
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_PRESENCE", "0")
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    mind.process("file the invoices", modality="text")
    assert mind.presence.history() == [], "kill switch stops the door pass"
    BeanieMind.reset_instance()
    # unverified cycles settle nothing even with the switch on
    monkeypatch.setattr(settings, "ARENA_PRESENCE", "1")
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_Brain(tmp_path))
    mind.process("what time is it", modality="text")
    assert mind.presence.history() == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_snapshot(setup):
    mind, _, _ = setup
    mind.presence.note("listening")
    mind.presence.note("speaking")
    stats = mind.presence.stats()
    assert stats["transitions"] == 2
    assert stats["by_state"] == {"listening": 1, "speaking": 1}
    assert stats["current"] == "speaking"
    snap = mind.presence.snapshot()
    assert snap["organ"] == "presence" and snap["context_window"]


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_presence_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    page = client.get("/mind/presence")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True
    assert payload["current"]["state"] == "idle"
    assert "context_window" in payload and "vocabulary" in payload

    note = client.post("/mind/presence/note",
                       json={"state": "listening", "detail": "owner"})
    assert note.json()["label"] == "Listening"

    bad = client.post("/mind/presence/note", json={"state": "floating"})
    assert bad.json()["success"] is False

    voice = client.post("/mind/presence/voice",
                        json={"text": "hello beanie"})
    body = voice.json()
    assert body["success"] is True and body["modality"] == "voice"
    assert body["state"] == "idle"  # no verifier verdict — nothing claimed
