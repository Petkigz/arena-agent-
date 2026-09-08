"""Phase 6 (Beanie AGI roadmap) — the general learning engine.

One loop every experience passes through: observe → interpret → compare →
novelty → hypothesis → test → outcome → update model → store → confidence.

Honesty contracts pinned here:
- success is EVIDENCE: True / False / None(UNKNOWN) — never guessed;
- reinforcement rehearses, it does not duplicate;
- contradictions become explicit hypotheses + lessons, never silent overwrites;
- learning is best-effort: it never fails the task that produced it.
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
        self.calls = []

    def process_cognitive_cycle(self, user_text, **kwargs):
        self.calls.append({"user_text": user_text, **kwargs})
        return self.result


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    brain.result = {"success": True, "assistant_reply": "ok"}
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain
    BeanieMind.reset_instance()


# ── stage 1: typed intake ───────────────────────────────────────────────────
def test_intake_is_typed_and_requires_provenance(setup):
    mind, _ = setup
    assert "unknown experience kind" in mind.learn({"kind": "vibe", "content": "x", "source": "s"})["reason"]
    assert mind.learn({"kind": "action", "content": "", "source": "s"})["success"] is False
    assert "source" in mind.learn({"kind": "action", "content": "x"})["reason"]
    assert "bool evidence" in mind.learn(
        {"kind": "action", "content": "x", "source": "s", "success": "yes"})["reason"]


def test_success_is_never_guessed(setup):
    mind, _ = setup
    rec = mind.learn({"kind": "action", "content": "tried the new export flow",
                      "source": "test"})  # no success evidence at all
    assert rec["success"] is True
    assert rec["success_evidence"] is None  # UNKNOWN stays unknown
    assert "nothing durable to store" in rec["store_note"]


# ── stages 3-4: compare + novelty ───────────────────────────────────────────
def test_novel_conversation_becomes_semantic_knowledge(setup):
    mind, _ = setup
    rec = mind.learn({"kind": "conversation",
                      "content": "the owner keeps invoices in the archive folder",
                      "source": "owner_taught"})
    assert rec["novelty"] == "novel"
    assert rec["stored_memory_id"] is not None
    assert rec["related_knowledge"] == []


def test_reinforcement_rehearses_not_duplicates(setup):
    mind, _ = setup
    content = "the owner prefers voice replies in the morning"
    first = mind.learn({"kind": "conversation", "content": content, "source": "chat"})
    second = mind.learn({"kind": "conversation", "content": content, "source": "chat"})
    assert first["novelty"] == "novel"
    assert second["novelty"] == "reinforces"
    assert second["store_note"] == "already known — rehearsed, not duplicated"
    counts = mind.memory.counts()
    assert counts["semantic"] == 1  # ONE record, not two


def test_contradiction_becomes_hypothesis_and_lesson(setup):
    mind, brain = setup
    # prior verified knowledge: the export worked
    brain.memory.add("episodic", "exported the report to pdf successfully",
                     importance=0.7, source="verified_cycle", success=True)
    # new experience contradicts it
    rec = mind.learn({"kind": "action",
                      "content": "exported the report to pdf but it failed",
                      "source": "cycle:text", "success": False})
    assert rec["novelty"] == "contradicts"
    assert rec["hypothesis"] is not None and "investigate" in rec["hypothesis"]
    assert rec["store_note"] == "contradiction stored as lesson"
    lessons = [r for r in brain.memory.search("exported report pdf", limit=10)
               if r.kind == "lesson"]
    assert lessons and "Contradiction learned" in lessons[0].content


# ── stages 5-6: hypothesis + test (experiments) ─────────────────────────────
def test_experiment_predictions_get_verdicts(setup):
    mind, _ = setup
    confirmed = mind.learn({"kind": "experiment", "prediction": "clearing cache fixes it",
                            "content": "cleared cache and the error stopped",
                            "source": "self_test", "success": True})
    assert confirmed["verdict"] == "confirmed"
    refuted = mind.learn({"kind": "experiment", "prediction": "reboot fixes it",
                          "content": "rebooted and the error stayed",
                          "source": "self_test", "success": False})
    assert refuted["verdict"] == "refuted"
    no_pred = mind.learn({"kind": "experiment", "content": "poked the service",
                          "source": "self_test", "success": True})
    assert no_pred["verdict"] is None


# ── verified outcomes stored as episodes (mistakes are data) ────────────────
def test_verified_outcomes_land_in_episodic_memory(setup):
    mind, brain = setup
    ok = mind.learn({"kind": "action", "content": "organized downloads by project",
                     "source": "cycle:text", "success": True, "outcome": "achieved"})
    assert ok["store_note"] == "verified success stored as episode"
    bad = mind.learn({"kind": "action", "content": "renamed the wrong folder",
                      "source": "cycle:text", "success": False, "outcome": "failed"})
    assert bad["store_note"] == "verified failure stored as episode (mistakes are data)"
    episodes = [r for r in brain.memory.search("organized downloads", limit=5)
                if r.kind == "episodic"]
    assert any(r.success is True for r in episodes)


# ── stage 10: confidence calibration ────────────────────────────────────────
def test_confidence_updates_only_with_real_evidence(setup):
    mind, brain = setup
    before = len(brain.confidence_calibrator._records)
    # evidence present → recorded
    mind.learn({"kind": "action", "content": "searched files for invoices",
                "source": "cycle:text", "success": True,
                "predicted_confidence": 0.7, "action_type": "search_files"})
    assert len(brain.confidence_calibrator._records) == before + 1
    # UNKNOWN outcome → NOT a negative sample
    mind.learn({"kind": "action", "content": "tried the new thing",
                "source": "cycle:text", "predicted_confidence": 0.6})
    assert len(brain.confidence_calibrator._records) == before + 1


# ── the door: cycles become experiences automatically ───────────────────────
def test_process_turns_verified_cycles_into_experiences(setup):
    mind, brain = setup
    brain.result = {"success": True, "assistant_reply": "done",
                    "goal_verified": True, "goal_lifecycle_state": "achieved"}
    mind.process("organize my downloads", modality="voice")
    events = mind.learning.events()
    assert events[0]["kind"] == "action"
    assert events[0]["success"] is True  # the VERIFIER said so
    assert events[0]["novelty"] == "novel"
    assert events[0]["outcome"] == "achieved"


def test_unverified_cycles_stay_unknown(setup):
    mind, brain = setup
    brain.result = {"success": True, "assistant_reply": "ok"}  # no verdict
    mind.process("hello", modality="text")
    assert mind.learning.events()[0]["success"] is None  # never guessed


def test_failed_verification_is_learned_as_failure(setup):
    mind, brain = setup
    brain.result = {"success": False, "goal_verified": False,
                    "goal_lifecycle_state": "failed", "reason": "blocked"}
    mind.process("open the vault", modality="text")
    event = mind.learning.events()[0]
    assert event["success"] is False and event["outcome"] == "failed"


def test_learning_failure_never_breaks_the_door(setup, monkeypatch):
    mind, brain = setup
    brain.result = {"success": True, "goal_verified": True}
    monkeypatch.setattr(mind.learning, "learn", lambda exp: (_ for _ in ()).throw(RuntimeError("boom")))
    result = mind.process("still works", modality="text")
    assert result["goal_verified"] is True and brain.calls  # cycle unaffected


def test_learning_kill_switch(setup, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ARENA_LEARNING_LOOP", "0")
    mind, brain = setup
    brain.result = {"success": True, "goal_verified": True}
    mind.process("no learning this turn", modality="text")
    assert mind.learning.events() == []


# ── owner corrections feed the loop ─────────────────────────────────────────
def test_correction_feed_routes_to_the_loop(setup, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(setup[0].db_path))
    mind, brain = setup
    from backend.message_router import MessageRouter
    router = MessageRouter(runtime=brain)
    router._feed_correction_to_mind({"correction_type": "factual"},
                                    "no, search the whole pc not just downloads")
    events = mind.learning.events()
    assert events[0]["kind"] == "correction"
    assert "whole pc" in events[0]["content"]
    lessons = [r for r in brain.memory.search("whole pc", limit=5) if r.kind == "lesson"]
    assert lessons and "Owner correction" in lessons[0].content
    # duplicates never re-learn
    router._feed_correction_to_mind({"duplicate": True}, "no, search the whole pc not just downloads")
    assert len(mind.learning.events()) == 1


# ── stats + API ─────────────────────────────────────────────────────────────
def test_stats_count_the_landscape(setup):
    mind, _ = setup
    mind.learn({"kind": "conversation", "content": "fact one about the owner", "source": "chat"})
    mind.learn({"kind": "action", "content": "did the thing successfully",
                "source": "cycle:text", "success": True})
    stats = mind.learning.stats()
    assert stats["total_experiences"] == 2
    assert stats["by_kind"] == {"conversation": 1, "action": 1}
    assert stats["by_novelty"]["novel"] == 2
    assert "experience" in stats["loop"] and "confidence" in stats["loop"]


def test_learning_api_contract(setup):
    mind, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    r = client.post("/mind/learn", json={
        "kind": "demonstration", "content": "owner grouped files by project then type",
        "source": "owner_taught"})
    assert r.json()["success"] is True and r.json()["novelty"] == "novel"

    r = client.post("/mind/learn", json={"kind": "telepathy", "content": "x", "source": "s"})
    body = r.json()
    assert body["success"] is False and "telepathy" in body["reason"]  # typed, not 500

    r = client.get("/mind/learning")
    assert r.json()["total_experiences"] == 1
    r = client.get("/mind/learning/events")
    assert r.json()["events"][0]["kind"] == "demonstration"
