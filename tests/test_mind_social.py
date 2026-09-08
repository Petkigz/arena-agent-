"""Phase 16 (Beanie AGI roadmap) — social intelligence: the owner model.

preferences, habits, communication style, goals, routines, interests,
relationships, boundaries, emotional/contextual cues, history with Beanie.
Contracts pinned here:
- facets come from what the owner SAID (markers) — never cold-read;
- repeated observations compound, never duplicate;
- routines / style / history are MEASURED from the real door ledger and
  claimed only with enough evidence (>=10 interactions);
- people mentioned are registered in the Phase-5 social store with
  provenance;
- listening never acts; an empty history yields an empty model.
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


# ── facets from what was said ───────────────────────────────────────────────
def test_preference_is_extracted_with_evidence(setup):
    mind, _, _ = setup
    res = mind.social.note("I love dark mode in every app")
    assert res["success"] is True and res["acted"] is False
    assert res["facets"] == ["preference"]
    note = res["notes"][0]
    assert note["content"] == "I love dark mode in every app"
    assert note["times_observed"] == 1


def test_boundary_is_recorded_exactly_as_said(setup):
    mind, _, _ = setup
    res = mind.social.note("Never delete anything from my desktop")
    assert res["facets"] == ["boundary"]
    stored = mind.social.model()["facets"]["boundary"][0]
    assert stored["content"].startswith("Never delete")


def test_emotion_cue_is_noted(setup):
    mind, _, _ = setup
    res = mind.social.note("I'm so frustrated with this printer today")
    assert "emotion_cue" in res["facets"]
    note = next(n for n in res["notes"] if n["facet"] == "emotion_cue")
    assert note["key"] == "frustrated"


def test_person_mention_registers_in_the_phase5_social_store(setup):
    mind, _, _ = setup
    res = mind.social.note("Pick up my wife Ana at six")
    assert "person" in res["facets"]
    person = mind.memory.social.recall("Ana")
    assert person is not None
    assert person["relationship"] == "owner's wife"
    assert person["provenance"] == "owner_conversation"


def test_interest_terms_are_candidate_interests(setup):
    mind, _, _ = setup
    res = mind.social.note("the hydroponics harvest schedule slipped again")
    assert "interest" in res["facets"]
    keys = [n["key"] for n in res["notes"] if n["facet"] == "interest"]
    assert any("hydroponics" in k for k in keys)


def test_repeated_observation_compounds_not_duplicates(setup):
    mind, _, _ = setup
    mind.social.note("I prefer everything in markdown format")
    mind.social.note("I prefer everything in markdown format")
    prefs = mind.social.model()["facets"]["preference"]
    assert len(prefs) == 1 and prefs[0]["times_observed"] == 2


# ── honesty: nothing observed, nothing claimed ──────────────────────────────
def test_empty_history_yields_an_empty_model(setup):
    mind, _, _ = setup
    model = mind.social.model()
    assert model["facet_counts"] == {}
    assert model["routines"]["known"] is False
    assert model["communication_style"]["known"] is False
    assert model["history"]["known"] is False
    assert "not" in model["policy"].lower() or "never" in model["policy"].lower()


def test_unmarked_speech_yields_no_facets(setup):
    mind, _, _ = setup
    res = mind.social.note("ok")
    assert res["success"] is True and res["facets"] == []


# ── measured routines / style / history ─────────────────────────────────────
def test_routines_measured_from_the_door_ledger(setup):
    mind, _, _ = setup
    assert mind.social.routines()["known"] is False
    for i in range(12):
        mind._record_entry("text", None, f"task number {i}")
    r = mind.social.routines()
    assert r["known"] is True and r["measured"] == 12
    assert isinstance(r["most_active_hour"], int)


def test_style_measured_with_enough_evidence(setup):
    mind, _, _ = setup
    for i in range(12):
        mind._record_entry("text", None, "quick one please?")
    s = mind.social.style()
    assert s["known"] is True and s["measured"] == 12
    assert s["summary"] == "terse"          # ~19 chars each
    assert s["question_rate"] == 1.0 and s["politeness_rate"] == 1.0
    # the observation lane never pollutes the owner's style
    mind.observe("watchdog", {"summary": "an extremely long automated observation report"})
    assert mind.social.style()["measured"] == 12


def test_history_tracks_the_relationship(setup):
    mind, _, _ = setup
    mind._record_entry("text", None, "hello")
    h = mind.social.history()
    assert h["known"] is True and h["interactions"] == 1
    assert h["days_together"] >= 0 and h["first_contact"]


# ── the door + kill switch + state room ─────────────────────────────────────
def test_door_process_feeds_the_owner_model(setup):
    mind, _, _ = setup
    mind.process("I really love jazz playlists while working", modality="text")
    prefs = mind.social.model()["facets"].get("preference", [])
    assert any("jazz" in p["content"] for p in prefs)


def test_kill_switch_stops_the_social_pass(setup):
    mind, _, monkeypatch = setup
    from app.config import settings
    from pathlib import Path
    db_path = Path(mind.db_path)
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_SOCIAL", "0")
    mind2 = BeanieMind.get_instance(db_path=db_path, runtime=_Brain(db_path.parent))
    mind2.process("I hate loud notifications forever", modality="text")
    assert mind2.social.model()["facet_counts"] == {}
    BeanieMind.reset_instance()


def test_state_owner_room_lights_up_from_the_social_organ(setup):
    mind, _, _ = setup
    mind.social.note("I prefer my coffee black")
    room = mind.state()["owner"]
    assert room["status"] == "ok"
    assert room["component"] == "Social"
    assert room["data"]["relationship"]["facet_counts"].get("preference") == 1


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_social_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    note = client.post("/mind/social/note",
                       json={"text": "Never wake me before seven, please"})
    assert note.status_code == 200
    assert note.json()["success"] is True
    assert "boundary" in note.json()["facets"]

    page = client.get("/mind/social")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True
    assert payload["facet_counts"]["boundary"] == 1
    assert payload["history"]["known"] is False  # nothing claimed without it
