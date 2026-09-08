"""Phase 7 (Beanie AGI roadmap) — learning from the owner via conversation.

"Beanie, watch this." Conversation is the teaching interface: no forms, no
JSON. Contracts pinned here:
- conservative markers ("watch this video..." cannot open a lesson);
- steps are gathered, then she PROPOSES her understanding and stores nothing
  until the owner says it is correct;
- confirmed procedures land in THREE places honestly: cognitive procedural
  memory, the existing taught-skills store, and the Phase-6 learning ledger
  (as a verified demonstration experience);
- a rejected proposal never fabricates knowledge — two misreadings and she
  stops and says so;
- teaching never breaks the chat flow (kill switch + fail-open router hook).
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
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    # point the legacy db singleton at a scratch file so the taught-skills
    # store integration stays hermetic
    from app.database import db as app_db
    monkeypatch.setattr(app_db, "db_path", str(tmp_path / "legacy.db"))
    app_db._init_db()
    yield mind, brain
    BeanieMind.reset_instance()


def teach(mind, cid, *messages):
    replies = []
    for m in messages:
        replies.append(mind.teaching.handle_message(cid, m))
    return replies


# ── markers are conservative ────────────────────────────────────────────────
def test_ordinary_messages_do_not_open_lessons(setup):
    mind, _ = setup
    for msg in ["hello", "what's on my calendar?", "watch this video and "
                "summarize the plot for me please"]:
        assert mind.teaching.handle_message("c1", msg) is None, msg
    assert mind.teaching.sessions() == []


def test_opening_markers_start_a_lesson(setup):
    mind, _ = setup
    reply = mind.teaching.handle_message("c1", "Beanie, watch this")
    assert reply and "watching" in reply
    assert mind.teaching.sessions()[0]["conversation_id"] == "c1"


def test_goal_is_captured_from_the_opening(setup):
    mind, _ = setup
    reply = mind.teaching.handle_message("c1", "this is how I organize files")
    assert "organize files" in reply
    assert mind.teaching.sessions()[0]["goal"] == "organize files"


# ── gathering ───────────────────────────────────────────────────────────────
def test_steps_are_gathered_and_cleaned(setup):
    mind, _ = setup
    replies = teach(mind, "c1", "watch this", "1. open the downloads folder",
                    "- then group by project", "finally, group by type")
    assert "Step 1 noted: open the downloads folder" in replies[1]
    assert "Step 2 noted: group by project" in replies[2]
    assert "Step 3 noted: group by type" in replies[3]


def test_end_without_steps_is_an_honest_pause(setup):
    mind, _ = setup
    teach(mind, "c1", "watch this")
    reply = mind.teaching.handle_message("c1", "that's it")
    assert "haven't caught any steps" in reply
    assert mind.teaching.sessions()[0]["state"] == "gathering"


def test_end_proposes_her_understanding(setup):
    mind, _ = setup
    teach(mind, "c1", "this is how I organize files", "group by project",
          "group by type")
    proposal = mind.teaching.handle_message("c1", "that's it")
    assert "So to organize files, you:" in proposal
    assert "1. group by project" in proposal and "2. group by type" in proposal
    assert "Is that correct?" in proposal
    assert mind.teaching.sessions()[0]["state"] == "proposed"


# ── confirmation: stored in three places, honestly ─────────────────────────
def test_confirmation_stores_everywhere(setup):
    mind, brain = setup
    teach(mind, "c1", "this is how I organize files", "group by project",
          "group by type", "that's it")
    reply = mind.teaching.handle_message("c1", "yes")
    assert "organize-files" in reply and "verified by you" in reply

    # 1. cognitive memory: a PROCEDURAL record, owner-confirmed
    procs = [r for r in brain.memory.search("organize files", limit=10)
             if r.kind == "procedural"]
    assert procs and procs[0].success is True
    assert "owner_taught" in procs[0].tags

    # 2. the existing taught-skills store (integration, not a new table)
    from app.tools.skill_teaching_engine import SkillTeachingEngine
    skills = SkillTeachingEngine.list_taught_skills(category="owner_taught_procedure")
    assert skills and skills[0]["skill_name"] == "organize-files"

    # 3. the Phase-6 ledger: a VERIFIED demonstration experience; the
    #    procedural record stored first means the loop rehearses, not
    #    duplicates
    event = mind.learning.events()[0]
    assert event["kind"] == "demonstration" and event["success"] is True

    # session is over
    assert mind.teaching.sessions() == []


# ── rejection: nothing fabricated ──────────────────────────────────────────
def test_rejection_goes_back_to_gathering(setup):
    mind, brain = setup
    teach(mind, "c1", "watch this", "step one", "that's it")
    reply = mind.teaching.handle_message("c1", "no")
    assert "wrong" in reply.lower() and "nothing saved" in reply.lower()
    session = mind.teaching.sessions()[0]
    assert session["state"] == "gathering" and session["steps"] == []


def test_two_misreadings_stop_honestly_and_save_nothing(setup):
    mind, brain = setup
    teach(mind, "c1", "watch this", "a step", "that's it", "no",
          "another step", "that's it")
    reply = mind.teaching.handle_message("c1", "no")
    assert "rather stop" in reply and "Nothing was saved" in reply
    assert mind.teaching.sessions() == []
    assert [r for r in brain.memory.search("step", limit=10)
            if r.kind == "procedural"] == []


def test_confirm_word_boundaries_are_strict(setup):
    mind, _ = setup
    teach(mind, "c1", "watch this", "a step", "that's it")
    # "correct me if I'm wrong" is NOT a confirmation
    reply = mind.teaching.handle_message("c1", "correct me if I'm wrong")
    assert "yes" in reply.lower() and "no" in reply.lower()
    assert mind.teaching.sessions()[0]["state"] == "proposed"


# ── control ─────────────────────────────────────────────────────────────────
def test_cancel_and_restart(setup):
    mind, _ = setup
    teach(mind, "c1", "watch this", "a step")
    reply = mind.teaching.handle_message("c1", "cancel")
    assert "cancelled" in reply and "haven't stored anything" in reply
    assert mind.teaching.sessions() == []


def test_goal_can_be_named_after_the_opener(setup):
    """The roadmap scene: 'watch this', THEN 'this is how I...' names it."""
    mind, _ = setup
    teach(mind, "c1", "Beanie, watch this")
    reply = mind.teaching.handle_message("c1", "This is how I organize files.")
    assert "organize files" in reply
    assert mind.teaching.sessions()[0]["goal"] == "organize files"
    teach(mind, "c1", "group by project", "group by type", "that's it")
    final = mind.teaching.handle_message("c1", "yes")
    assert "organize-files" in final


def test_double_start_is_honest(setup):
    mind, _ = setup
    teach(mind, "c1", "watch this", "a first step")
    reply = mind.teaching.handle_message("c1", "let me show you something else")
    assert "already mid-lesson" in reply


def test_abandoned_sessions_expire(setup):
    mind, _ = setup
    from app.mind.teaching import SESSION_TTL_SECONDS
    teach(mind, "c1", "watch this")
    mind.teaching._sessions["c1"].last_activity -= SESSION_TTL_SECONDS + 1
    assert mind.teaching.sessions() == []
    assert mind.teaching.handle_message("c1", "a step") is None  # lesson gone


# ── router wiring + kill switch ─────────────────────────────────────────────
def test_router_consumes_lesson_turns_only(setup):
    mind, brain = setup
    from backend.message_router import MessageRouter
    router = MessageRouter(runtime=brain)
    # ordinary message → cycle runs as always
    assert router._try_teaching_turn("c1", "hello there") is None
    # opener → lesson reply consumes the turn
    reply = router._try_teaching_turn("c1", "beanie, watch this")
    assert reply and "watching" in reply
    # follow-up step is also consumed by the lesson
    assert "Step 1 noted" in router._try_teaching_turn("c1", "open the app")


def test_teaching_kill_switch(setup, monkeypatch):
    mind, brain = setup
    from app.config import settings
    from backend.message_router import MessageRouter
    router = MessageRouter(runtime=brain)
    monkeypatch.setattr(settings, "ARENA_TEACHING", "0")
    assert router._try_teaching_turn("c1", "beanie, watch this") is None
    assert mind.teaching.sessions() == []


# ── inspection API ──────────────────────────────────────────────────────────
def test_procedures_and_sessions_api(setup):
    mind, _ = setup
    teach(mind, "c1", "this is how I organize files", "group by project",
          "that's it", "yes")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.get("/mind/procedures").json()
    assert body["success"] is True
    assert body["procedures"][0]["skill_name"] == "organize-files"
    assert "watch this" in body["how_to_teach"]

    # a live session shows up in the inspection window
    teach(mind, "c2", "watch this", "open the app")
    sessions = client.get("/mind/teaching/sessions").json()["sessions"]
    assert sessions and sessions[0]["conversation_id"] == "c2"
