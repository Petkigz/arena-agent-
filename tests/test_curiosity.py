"""Phase 9 (Beanie AGI roadmap) — curiosity / the internal UNKNOWN system.

Contracts pinned here:
- ignorance becomes a RECORD: topics normalize, encounters compound;
- knowledge arriving through the learning door closes matching unknowns
  (uncertainty ↓ measured as ledger state);
- investigate = search her own memory FIRST; real evidence closes it, no
  evidence keeps it OPEN and names the next honest step (ask the owner);
- an unknown is never wished away; resolved topics that recur reopen;
- resolution paths are counted separately (knowledge / investigation / owner);
- curiosity bookkeeping never breaks learning or the brief.
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
    yield mind, brain
    BeanieMind.reset_instance()


# ── registration: ignorance becomes a record ───────────────────────────────
def test_registration_is_typed_and_normalizes(setup):
    mind, _ = setup
    assert mind.curiosity.register("")["success"] is False
    assert mind.curiosity.register("  ")["success"] is False
    # filler words are noise, not curiosity (gap extraction can emit them)
    assert mind.curiosity.register("really")["success"] is False
    assert "noise is not curiosity" in mind.curiosity.register("really")["reason"]

    first = mind.curiosity.register("The Document", source="world_first_gap")
    assert first["success"] is True and first["registered"] is True
    # same topic, different surface form → ONE unknown, encounter compounding
    again = mind.curiosity.register("the document!", source="world_first_gap")
    assert again["registered"] is False and again["encounter"] is True
    assert again["times_encountered"] == 2
    assert len(mind.curiosity.curiosities()) == 1


def test_encounters_drive_priority(setup):
    mind, _ = setup
    mind.curiosity.register("invoice folder")
    for _ in range(3):
        mind.curiosity.register("blender renders")
    top = mind.curiosity.curiosities()
    assert top[0]["topic"] == "blender renders"
    assert top[0]["times_encountered"] == 3
    assert top[1]["topic"] == "invoice folder"


# ── knowledge through the learning door closes unknowns ────────────────────
def test_learned_knowledge_closes_matching_unknowns(setup):
    mind, _ = setup
    mind.curiosity.register("invoice folder", source="world_first_gap")
    mind.curiosity.register("blender renders", source="world_first_gap")

    # an unrelated lesson leaves both open
    mind.learn({"kind": "conversation", "content": "the owner drinks coffee",
                "source": "chat"})
    assert mind.curiosity.stats()["open"] == 2

    # knowledge that actually overlaps closes exactly the matching unknown
    mind.learn({"kind": "conversation",
                "content": "the invoice folder lives on the scratch disk",
                "source": "owner_taught"})
    stats = mind.curiosity.stats()
    assert stats["open"] == 1 and stats["resolved"] == 1
    assert stats["resolved_by"] == {"knowledge": 1}
    assert mind.curiosity.curiosities()[0]["topic"] == "blender renders"


def test_broken_curiosity_never_breaks_learning(setup, monkeypatch):
    mind, _ = setup
    mind.curiosity.register("anything")

    def _boom(content):
        raise RuntimeError("ledger melted")
    monkeypatch.setattr(mind.curiosity, "notify_knowledge", _boom)
    rec = mind.learn({"kind": "conversation", "content": "anything new here",
                      "source": "chat"})
    assert rec["success"] is True  # learning unaffected


# ── investigate: her own memory first ──────────────────────────────────────
def test_investigate_with_memory_evidence_resolves(setup):
    mind, brain = setup
    brain.memory.add("semantic", "the blender renders folder is on the "
                     "scratch disk", importance=0.6, source="owner_taught")
    mind.curiosity.register("blender renders", source="world_first_gap")

    rec = mind.curiosity.investigate()  # top open unknown by priority
    assert rec["success"] is True and rec["resolved"] is True
    assert rec["path"] == "investigation"
    assert rec["evidence"] and "scratch disk" in rec["evidence"][0]["content"]
    assert mind.curiosity.stats()["resolved_by"]["investigation"] == 1


def test_investigate_without_evidence_stays_honestly_open(setup):
    mind, _ = setup
    mind.curiosity.register("invoice folder", source="world_first_gap")
    rec = mind.curiosity.investigate("invoice folder")
    assert rec["success"] is True and rec["resolved"] is False
    assert rec["evidence"] == []
    assert "ask the owner" in rec["next_honest_step"]
    assert mind.curiosity.stats()["open"] == 1  # not wished away
    assert mind.curiosity.investigate("never heard of it")["success"] is False


# ── owner answers ───────────────────────────────────────────────────────────
def test_owner_resolution(setup):
    mind, _ = setup
    mind.curiosity.register("invoice folder", source="world_first_gap")
    assert mind.curiosity.resolve("invoice folder", "")["success"] is False
    assert mind.curiosity.resolve("unknown topic", "somewhere")["success"] is False

    rec = mind.curiosity.resolve("invoice folder", "it's in ~/Documents/invoices")
    assert rec["success"] is True and rec["path"] == "owner"
    stats = mind.curiosity.stats()
    assert stats["open"] == 0 and stats["resolved_by"]["owner"] == 1


def test_reencountering_a_resolved_unknown_reopens_it(setup):
    mind, _ = setup
    mind.curiosity.register("invoice folder")
    mind.curiosity.resolve("invoice folder", "in documents")
    rec = mind.curiosity.register("invoice folder")
    assert rec["reopened"] is True
    assert mind.curiosity.stats()["open"] == 1


# ── brief gaps feed the system automatically ────────────────────────────────
def test_brief_gaps_become_unknowns(setup):
    mind, _ = setup
    mind._feed_gaps_to_curiosity(["blender", "renders"], "where are my renders")
    tops = mind.curiosity.curiosities()
    assert {t["topic"] for t in tops} == {"blender", "renders"}
    assert tops[0]["source"] == "world_first_gap"


def test_curiosity_kill_switch(setup, monkeypatch):
    mind, _ = setup
    from app.config import settings
    monkeypatch.setattr(settings, "ARENA_CURIOSITY", "0")
    mind._feed_gaps_to_curiosity(["blender"], "where is blender")
    mind._close_unknowns_from_knowledge("blender lives in /opt")
    assert mind.curiosity.stats()["total_unknowns"] == 0


# ── API contract ────────────────────────────────────────────────────────────
def test_curiosity_api(setup):
    mind, brain = setup
    brain.memory.add("semantic", "the invoice folder is archived monthly",
                     importance=0.6, source="owner_taught")
    mind.curiosity.register("invoice folder", source="world_first_gap")
    mind.curiosity.register("blender renders", source="world_first_gap")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.get("/mind/curiosity").json()
    assert body["success"] is True and body["open"] == 2
    assert body["top"][0]["topic"] in ("invoice folder", "blender renders")

    body = client.post("/mind/curiosity/investigate",
                       json={"topic": "invoice folder"}).json()
    assert body["resolved"] is True and body["path"] == "investigation"

    body = client.post("/mind/curiosity/resolve",
                       json={"topic": "blender renders",
                             "answer": "they are on the scratch disk"}).json()
    assert body["success"] is True and body["path"] == "owner"

    body = client.get("/mind/curiosity").json()
    assert body["open"] == 0 and body["resolved"] == 2
    assert body["resolved_by"] == {"investigation": 1, "owner": 1}

    assert client.post("/mind/curiosity/resolve",
                       json={"topic": "x", "answer": ""}).status_code == 422
