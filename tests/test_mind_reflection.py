"""Phase 19 (Beanie AGI roadmap) — self-reflection.

"After important experiences: What happened? Why? What did I believe? Was
I correct? What surprised me? What did I learn? Should I change my model?
Should I remember this?" Contracts pinned here:
- every question is answered from REAL evidence — never narration;
- correctness is the verifier's word ONLY — an unverified outcome stays
  UNKNOWN (never guessed);
- beliefs come from the imagination ledger when she simulated; 'no
  simulation recorded' otherwise (nothing invented);
- surprise = a refuted prediction or declared surprisal;
- counsel is evidence-driven: refuted prediction -> change model; a
  REPEATED verified failure becomes an open unknown registered with
  curiosity; a single failure is data, not a pattern;
- the door reflects on VERIFIED cycles only (important experiences);
- reflecting performs nothing (acted: False).
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


# ── correctness is the verifier's word only ─────────────────────────────────
def test_verified_success_is_correct(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "sent the report",
                "source": "cycle:text", "success": True})
    r = mind.reflection.reflect_on({"kind": "action", "content": "sent the report",
                                    "success": True, "outcome": "completed"})
    assert r["success"] is True and r["acted"] is False
    assert r["epistemic_kind"] == "reflection"
    assert r["was_i_correct"]["verdict"] == "correct"
    assert "sent the report" in r["what_happened"]


def test_verified_failure_is_wrong(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "exported the csv",
                "source": "cycle:text", "success": False})
    r = mind.reflection.reflect_on({"kind": "action", "content": "exported the csv",
                                    "success": False})
    assert r["was_i_correct"]["verdict"] == "wrong"


def test_unverified_stays_unknown_never_guessed(setup):
    mind, _, _ = setup
    r = mind.reflection.reflect_on({"kind": "action", "content": "did a thing",
                                    "success": None})
    assert r["was_i_correct"]["verdict"] is None
    assert r["was_i_correct"]["known"] is False
    assert "UNKNOWN" in r["was_i_correct"]["statement"]


# ── beliefs only when she actually simulated ────────────────────────────────
def test_no_belief_invented_without_a_simulation(setup):
    mind, _, _ = setup
    r = mind.reflection.reflect_on({"kind": "action", "content": "did a thing",
                                    "success": True, "goal_type": "send_email"})
    assert r["what_i_believed"]["known"] is False
    assert "no simulation" in r["what_i_believed"]["statement"]


def test_belief_comes_from_the_imagination_ledger(setup):
    mind, _, _ = setup
    mind.imagination.compare("send_email", True, source="test")
    r = mind.reflection.reflect_on({"kind": "action", "content": "sent the email",
                                    "success": True, "goal_type": "send_email"})
    assert r["what_i_believed"]["known"] is True
    assert "expected" in r["what_i_believed"]["statement"].lower()


# ── surprise is reality against expectation ─────────────────────────────────
def test_refuted_prediction_is_a_surprise(setup):
    mind, _, _ = setup
    mind.imagination.compare("delete_file", False, source="test")
    r = mind.reflection.reflect_on({"kind": "action", "content": "deleted the file",
                                    "success": False, "goal_type": "delete_file"})
    assert r["what_surprised_me"]["surprised"] is True
    assert "refuted" in r["what_surprised_me"]["statement"]


def test_declared_surprisal_reads_as_surprise(setup):
    mind, _, _ = setup
    r = mind.reflection.reflect_on({"kind": "action", "content": "weird outcome",
                                    "success": True, "surprisal": 0.9})
    assert r["what_surprised_me"]["surprised"] is True
    assert "0.90" in r["what_surprised_me"]["statement"]


def test_confirmed_prediction_is_not_a_surprise(setup):
    mind, _, _ = setup
    mind.imagination.compare("send_email", True, source="test")
    r = mind.reflection.reflect_on({"kind": "action", "content": "sent the email",
                                    "success": True, "goal_type": "send_email"})
    assert r["what_surprised_me"]["surprised"] is False


# ── counsel: when to change the model ───────────────────────────────────────
def test_refuted_prediction_counsels_model_change(setup):
    mind, _, _ = setup
    mind.imagination.compare("delete_file", False, source="test")
    r = mind.reflection.reflect_on({"kind": "action", "content": "deleted the file",
                                    "success": False, "goal_type": "delete_file"})
    assert r["should_change_model"]["change"] is True
    assert "need updating" in r["should_change_model"]["statement"]


def test_single_failure_is_data_not_pattern(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "the export job",
                "source": "cycle:text", "success": False})
    r = mind.reflection.reflect_on({"kind": "action", "content": "the export job",
                                    "success": False})
    assert r["should_change_model"]["change"] is False
    assert "single verified failure" in r["should_change_model"]["statement"]


def test_repeated_failure_becomes_an_open_unknown(setup):
    mind, _, _ = setup
    for _ in range(2):
        mind.learn({"kind": "action", "content": "the nightly sync",
                    "source": "cycle:text", "success": False})
    r = mind.reflection.reflect_on({"kind": "action", "content": "the nightly sync",
                                    "success": False})
    assert r["should_change_model"]["change"] is True
    assert "open unknown" in r["should_change_model"]["statement"]
    unknowns = mind.curiosity.curiosities(limit=20)
    assert any("keeps failing" in str(u["topic"]).lower() or
               "keep failing" in str(u["topic"]).lower() for u in unknowns)


def test_verified_success_keeps_the_model(setup):
    mind, _, _ = setup
    r = mind.reflection.reflect_on({"kind": "action", "content": "a clean run",
                                    "success": True})
    assert r["should_change_model"]["change"] is False
    assert "model" in r["should_change_model"]["statement"]


# ── learning + memory decisions ─────────────────────────────────────────────
def test_learning_record_is_reported(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "organized the inbox",
                "source": "cycle:text", "success": True})
    r = mind.reflection.reflect_on({"kind": "action", "content": "organized the inbox",
                                    "success": True})
    assert r["what_i_learned"]["known"] is True
    assert "novelty" in r["what_i_learned"]["statement"]


def test_reflecting_on_nothing_fails_honestly(setup):
    mind, _, _ = setup
    res = mind.reflection.reflect_on({"kind": "action", "content": ""})
    assert res["success"] is False and "no experience" in res["reason"]


# ── the door: verified cycles are the important experiences ─────────────────
class _VerifyingBrain(_Brain):
    def __init__(self, tmp_path, verified):
        super().__init__(tmp_path)
        self._verified = verified

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok",
                "goal_verified": self._verified,
                "goal_lifecycle_state": "completed"}


def test_door_reflects_on_verified_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    brain = _VerifyingBrain(tmp_path, verified=True)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    mind.process("file the invoices", modality="text")
    refls = mind.reflection.reflections()
    assert refls and "file the invoices" in refls[0]["content"]
    assert refls[0]["was_i_correct"] == "correct"
    BeanieMind.reset_instance()


def test_door_skips_unverified_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()

    class _NoVerdict(_Brain):
        def process_cognitive_cycle(self, user_text, **kwargs):
            return {"success": True, "assistant_reply": "ok"}

    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_NoVerdict(tmp_path))
    mind.process("file the invoices", modality="text")
    assert mind.reflection.reflections() == []
    BeanieMind.reset_instance()


def test_kill_switch_stops_reflection(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    from app.config import settings
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_REFLECTION", "0")
    brain = _VerifyingBrain(tmp_path, verified=True)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    mind.process("file the invoices", modality="text")
    assert mind.reflection.reflections() == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_lessons(setup):
    mind, _, _ = setup
    mind.imagination.compare("delete_file", False, source="test")
    mind.reflection.reflect_on({"kind": "action", "content": "deleted the file",
                                "success": False, "goal_type": "delete_file"})
    stats = mind.reflection.stats()
    assert stats["reflections"] == 1
    assert stats["by_verdict"].get("wrong") == 1
    assert stats["model_changes"] >= 1
    assert mind.reflection.lessons(), "the model-change reflection is a lesson"


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_reflection_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    post = client.post("/mind/reflection/reflect",
                       json={"content": "sent the weekly digest",
                             "kind": "action", "success": True})
    assert post.status_code == 200
    body = post.json()
    assert body["success"] is True and body["acted"] is False
    assert body["was_i_correct"]["verdict"] == "correct"

    # success omitted -> UNKNOWN, never guessed
    post2 = client.post("/mind/reflection/reflect",
                        json={"content": "maybe worked", "kind": "action"})
    assert post2.json()["was_i_correct"]["verdict"] is None

    page = client.get("/mind/reflection")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True and payload["reflections"] == 2
    assert len(payload["stream"]) == 2
    assert payload["by_verdict"].get("correct") == 1
