"""Phase 1 (AGI roadmap) — BeanieMind, the one canonical door.

Guards the Phase-1 deliverable: every input (voice, WS text, REST) enters
the SAME mind — BeanieMind.process — which wraps the one brain
(CognitiveRuntime; never a second runtime) and adds the persisted identity
("I am Beanie", M1) and the BeanieState skeleton (M2).

Invariants pinned here:
- the door returns the brain's typed result UNCHANGED (honesty lives below);
- recording is best-effort — a storage failure never fails a cycle;
- state rooms are honestly marked, never fabricated;
- one brain, always: a different runtime gets a bound view, never a second
  shared mind.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from app.mind import BeanieMind, MODALITIES
from app.mind.state import STATE_FIELDS


class _StubBrain:
    """Minimal brain double: returns the given cycle result verbatim."""

    def __init__(self, result=None, raise_exc=None):
        self._result = result if result is not None else {
            "success": True,
            "assistant_reply": "ok",
            "goal_lifecycle_state": "achieved",
        }
        self._raise = raise_exc
        self.calls = []

    def process_cognitive_cycle(self, user_text, **kwargs):
        self.calls.append({"user_text": user_text, **kwargs})
        if self._raise:
            raise self._raise
        return self._result


@pytest.fixture()
def mind(tmp_path, monkeypatch):
    """A fresh mind bound to a stub brain with an isolated ledger DB."""
    BeanieMind.reset_instance()
    brain = _StubBrain()
    m = BeanieMind(db_path=tmp_path / "arena.db", runtime=brain)
    m._brain = brain  # handle for assertions
    yield m
    BeanieMind.reset_instance()


# ── THE DOOR ────────────────────────────────────────────────────────────────
def test_process_returns_the_brains_result_unchanged(mind):
    result = mind.process("open the file", modality="text", conversation_id="c1")
    assert result == mind._brain._result  # untouched, no manufactured fields
    assert mind._brain.calls[0]["user_text"] == "open the file"
    assert mind._brain.calls[0]["session_id"] == "c1"  # conversation → session


def test_process_forwards_cycle_kwargs(mind):
    mind.process(
        "look at this", modality="text", conversation_id="c2",
        complexity="main", image_path="/tmp/x.png",
        attachments=[{"name": "a.pdf"}],
        recent_user_messages=["earlier"],
    )
    call = mind._brain.calls[0]
    assert call["complexity"] == "main"
    assert call["image_path"] == "/tmp/x.png"
    assert call["attachments"] == [{"name": "a.pdf"}]
    assert call["recent_user_messages"] == ["earlier"]


def test_entry_ledger_records_modality_in_order(mind):
    mind.process("a", modality="voice", conversation_id="c")
    mind.process("b", modality="text", conversation_id="c")
    mind.process("c", modality="rest")
    entries = mind.entries()
    assert [e["modality"] for e in entries] == ["rest", "text", "voice"]
    assert all(e["known_modality"] for e in entries)
    assert entries[2]["conversation_id"] == "c"
    stats = mind.entry_stats()
    assert stats["total_entries"] == 3
    assert stats["per_modality"] == {"voice": 1, "text": 1, "rest": 1}


def test_unknown_modality_is_accepted_but_flagged(mind):
    mind.process("hello", modality="carrier_pigeon")
    entry = mind.entries(limit=1)[0]
    assert entry["modality"] == "carrier_pigeon"
    assert entry["known_modality"] is False  # honest, not refused


def test_ledger_failure_never_fails_the_cycle(mind):
    """Recording is best-effort (AGENT_INVARIANTS §1): with storage gone the
    cycle still succeeds, and stats degrade to the in-process counter."""
    with patch("app.mind.beanie_mind.sqlite3.connect", side_effect=OSError("disk gone")):
        result = mind.process("still works", modality="text")
        assert result["success"] is True
        stats = mind.entry_stats()  # reads also fail → honest fallback
    assert stats["total_entries"] >= 1


def test_observe_records_and_never_acts(mind):
    out = mind.observe("screen_watcher", {"event": "popup appeared"})
    # the Phase-1 contract is preserved exactly; Phase 13 adds the
    # perception pass on top (judged, never acted)
    assert out["success"] is True and out["recorded"] is True
    assert out["source"] == "screen_watcher" and out["acted"] is False
    assert out["perception"]["acted"] is False
    assert out["perception"]["epistemic_kind"] == "perception"
    entry = mind.entries(limit=1)[0]
    assert entry["modality"] == "observation"
    assert "popup appeared" in entry["summary"]


def test_modalities_vocabulary_matches_roadmap_doors():
    # voice primary, text backup, plus the reserved future lanes
    assert {"voice", "text", "rest", "observation", "autonomous"} <= MODALITIES


# ── IDENTITY (M1) ───────────────────────────────────────────────────────────
def test_identity_seed_is_beanie(mind):
    rec = mind.identity.to_dict()
    assert rec["name"] == "Beanie"
    assert rec["born"] == "2026-09-08"
    assert rec["charter"] == "docs/OWNER_VISION_CHARTER.md"
    assert rec["roadmap"] == "docs/AGI_ROADMAP.md"
    assert len(rec["milestones"]) >= 1  # Phase-1 creation milestone
    assert rec["milestones"][0]["phase"] == "phase1"


def test_identity_statement_names_her(mind):
    stmt = mind.identity.identity_statement()
    assert stmt.startswith("I am Beanie")
    assert "voice primary, text backup" in stmt


def test_identity_persists_across_restart(mind):
    mind.identity.update("interfaces", "voice only, owner is testing")
    db = mind.db_path
    reborn = BeanieMind(db_path=db, runtime=mind._brain)
    assert reborn.identity.get("interfaces") == "voice only, owner is testing"
    assert reborn.identity.get("name") == "Beanie"


def test_milestones_are_append_only_development_history(mind):
    mind.identity.record_milestone("phase1", "test event", "detail")
    ms = mind.identity.milestones()
    events = [m["event"] for m in ms]
    assert "test event" in events
    assert "identity record created" in events


# ── BEANIESTATE (M2) ────────────────────────────────────────────────────────
def test_state_has_exactly_the_roadmap_rooms(mind):
    state = mind.state()
    assert tuple(state.keys()) == STATE_FIELDS


def test_state_is_json_safe_and_honest_on_a_bare_stub(mind):
    state = mind.state()
    json.dumps(state)  # must serialize
    for room in state.values():
        assert room["status"] in {"ok", "wired", "unavailable"}
    # a bare stub has no organs — nothing may be fabricated as 'ok' data
    assert state["world"]["status"] == "unavailable"
    assert state["working_memory"]["status"] == "unavailable"


def test_state_reads_real_organs_when_present(tmp_path):
    class _WM:
        def snapshot(self, limit=None):
            return [{"item": "goal: organize files", "salience": 0.9}]

    class _World:
        def find_entities(self, name=None, entity_type=None):
            return ["e1", "e2", "e3"]

        def recent_observations(self, subject=None, limit=50):
            return ["o1"]

    class _UserState:
        def snapshot(self, include_expired=False):
            return {"preferences": {"voice": "primary"}}

    class _RichBrain(_StubBrain):
        def __init__(self):
            super().__init__()
            self.working_memory = _WM()
            self.world = _World()
            self.user_state = _UserState()

    BeanieMind.reset_instance()
    brain = _RichBrain()
    m = BeanieMind(db_path=tmp_path / "arena.db", runtime=brain)
    state = m.state()
    assert state["working_memory"]["status"] == "ok"
    assert state["working_memory"]["data"]["items"][0]["item"].startswith("goal:")
    assert state["world"]["data"]["entity_count"] == 3
    assert state["world"]["data"]["recent_observations"] == 1
    assert state["owner"]["data"]["snapshot"]["preferences"]["voice"] == "primary"
    assert state["self"]["data"]["identity"]["name"] == "Beanie"
    BeanieMind.reset_instance()


# ── ONE BRAIN, ALWAYS ───────────────────────────────────────────────────────
def test_get_instance_binds_the_first_explicit_brain(tmp_path):
    BeanieMind.reset_instance()
    brain_a = _StubBrain()
    shared = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain_a)
    assert shared.runtime is brain_a
    assert BeanieMind.get_instance(runtime=brain_a) is shared
    BeanieMind.reset_instance()


def test_a_different_brain_gets_a_bound_view_not_a_second_shared_mind(tmp_path):
    BeanieMind.reset_instance()
    brain_a = _StubBrain()
    brain_b = _StubBrain()
    shared = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain_a)
    other = BeanieMind.get_instance(runtime=brain_b)
    assert other is not shared
    assert other.runtime is brain_b
    assert shared.runtime is brain_a  # singleton untouched
    # the shared mind remains THE instance
    assert BeanieMind.get_instance(runtime=brain_a) is shared
    BeanieMind.reset_instance()


# ── ENTRY CONVERGENCE: the three real doors ─────────────────────────────────
def test_ws_door_enters_through_the_mind_tagged_voice(tmp_path, monkeypatch):
    """Voice transcripts arrive source='voice' and must reach the brain via
    BeanieMind.process with modality 'voice'."""
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "arena.db"))
    BeanieMind.reset_instance()

    brain = _StubBrain({"success": True, "assistant_reply": "done",
                        "goal_lifecycle_state": "achieved"})
    from backend.message_router import MessageRouter
    router = MessageRouter(runtime=brain)

    reply = asyncio.run(router._call_cognitive_runtime(
        "organize my downloads", conversation_id="conv-9", message_source="voice"))
    assert reply == "done"
    assert brain.calls and brain.calls[0]["session_id"] == "conv-9"
    entries = BeanieMind.get_instance(runtime=brain).entries()
    assert entries[0]["modality"] == "voice"
    assert entries[0]["conversation_id"] == "conv-9"
    BeanieMind.reset_instance()


def test_ws_door_defaults_to_text_modality(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "arena.db"))
    BeanieMind.reset_instance()

    brain = _StubBrain({"success": True, "assistant_reply": "ok",
                        "goal_lifecycle_state": "achieved"})
    from backend.message_router import MessageRouter
    router = MessageRouter(runtime=brain)
    asyncio.run(router._call_cognitive_runtime("hi", conversation_id="c"))
    entries = BeanieMind.get_instance(runtime=brain).entries()
    assert entries[0]["modality"] == "text"
    BeanieMind.reset_instance()


def test_rest_door_enters_through_the_mind_tagged_rest(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "arena.db"))
    BeanieMind.reset_instance()

    fake = _StubBrain({"success": True, "assistant_reply": "done",
                       "goal_lifecycle_state": "achieved",
                       "reason": "verified"})
    from app.cognition import cognitive_pipeline as cp_mod
    from app.cognition.cognitive_pipeline import CognitivePipeline
    with patch.object(cp_mod.CognitiveRuntime, "get_instance",
                      staticmethod(lambda: fake)):
        res = CognitivePipeline.process_request("open notepad", session_id="sess_r")
    assert res["success"] is True
    assert res["assistant_reply"] == "done"
    entries = BeanieMind.get_instance(runtime=fake).entries()
    assert entries[0]["modality"] == "rest"
    assert entries[0]["conversation_id"] == "sess_r"
    BeanieMind.reset_instance()


def test_rest_door_keeps_honest_failure_when_brain_raises(tmp_path, monkeypatch):
    """The door must not swallow the crash contract: CognitivePipeline still
    converts a raising brain into a structured honest failure."""
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "arena.db"))
    BeanieMind.reset_instance()

    fake = _StubBrain(raise_exc=RuntimeError("boom"))
    from app.cognition import cognitive_pipeline as cp_mod
    from app.cognition.cognitive_pipeline import CognitivePipeline
    with patch.object(cp_mod.CognitiveRuntime, "get_instance",
                      staticmethod(lambda: fake)):
        res = CognitivePipeline.process_request("do the thing")
    assert res["success"] is False
    assert "boom" in res["reason"]
    assert res["goal_lifecycle_state"] == "failed"
    BeanieMind.reset_instance()


# ── API surface ─────────────────────────────────────────────────────────────
def test_mind_api_endpoints_serve_identity_state_entries(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "arena.db"))
    BeanieMind.reset_instance()
    brain = _StubBrain()
    mind = BeanieMind.get_instance(runtime=brain)
    mind.process("hello", modality="voice", conversation_id="c")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    r = client.get("/mind/identity")
    assert r.status_code == 200
    body = r.json()
    assert body["identity"]["name"] == "Beanie"
    assert body["identity_statement"].startswith("I am Beanie")

    r = client.get("/mind/state")
    assert r.status_code == 200
    state = r.json()["state"]
    assert tuple(state.keys()) == STATE_FIELDS

    r = client.get("/mind/entries")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert entries[0]["modality"] == "voice"
    assert r.json()["stats"]["total_entries"] == 1
    BeanieMind.reset_instance()
