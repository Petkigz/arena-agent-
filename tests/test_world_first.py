"""Phase 2 (Beanie AGI roadmap) — world-first thinking.

The order change under test: request → understand world → self state →
relevant memory → (then) capabilities. The brief is deterministic retrieval
with provenance, budget-bounded, delivered through the brain's working
memory — the channel the cognitive cycle already reads — and the attention
gate's decision is respected and recorded honestly. Fail-open always: a
broken brief path never breaks the door.
"""

from __future__ import annotations

import time

import pytest

from app.cognition.memory import MemoryStore
from app.cognition.working_memory import WorkingMemory
from app.cognition.world_model import WorldModel
from app.mind import BeanieMind

FAKE_CATALOG = {
    "open_application": {
        "name": "Open application", "category": "os_control", "safety_level": 1,
        "description": "open an application on the computer",
    },
    "search_files": {
        "name": "Search files", "category": "filesystem", "safety_level": 0,
        "description": "search files on the filesystem",
    },
}


class _Brain:
    """Stub brain with REAL world/memory/working-memory organs."""

    def __init__(self, tmp_path):
        self.world = WorldModel(db_path=str(tmp_path / "world.db"))
        self.memory = MemoryStore(tmp_path / "memory.db")
        self.working_memory = WorkingMemory()
        self.hardware_self_model = {}
        self.phase7_preferences = None
        self.calls = []

    def process_cognitive_cycle(self, user_text, **kwargs):
        self.calls.append({"user_text": user_text, **kwargs})
        return {"success": True, "assistant_reply": "ok"}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: FAKE_CATALOG)
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    # get_instance registers the singleton so the API endpoints (which call
    # get_instance() bare) see THIS mind — one brain, always.
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain
    BeanieMind.reset_instance()


def _seed(mind):
    """The roadmap's teaching: an app, a file, a proven state, a real memory."""
    mind.world.remember_entity("Blender", "application")
    mind.world.observe_state("Blender", "status", "running", source="os_process_probe")
    mind.world.remember_entity("project plan.docx", "file",
                               attributes={"aliases": ["the document"]})
    mind.memory.remember(
        "episodic", "organized the downloads folder into project groups; verified",
        importance=0.8, source="verified_cycle", success=True)


# ── brief assembly ──────────────────────────────────────────────────────────
def test_brief_assembles_world_then_self_then_memory(setup):
    mind, _ = setup
    _seed(mind)
    brief = mind.world_first.assemble_brief("open Blender and organize the downloads folder")
    # world: entity matched with provenance-tracked state
    names = [m["name"] for m in brief["world"]["matched"]]
    assert "Blender" in names
    blender = next(m for m in brief["world"]["matched"] if m["name"] == "Blender")
    assert blender["states"]["status"] == {"value": "running", "source": "os_process_probe"}
    # self: capability identified AFTER the world
    assert brief["self"]["knowledge"] in ("known", "partial")
    assert "open_application" in brief["self"]["capabilities"]
    # memory: remembered doing the downloads task
    assert brief["memory"]["status"] == "remembered_done"
    # rendering order = roadmap order: world before self, self before memory
    r = brief["rendered"]
    assert r.index("[WORLD CONTEXT]") < r.index("[SELF STATE]") < r.index("[WHAT I ALREADY KNOW]")
    assert "[os_process_probe]" in r  # provenance survives into the prompt text


def test_brief_keeps_gaps_visible(setup):
    mind, _ = setup
    _seed(mind)
    brief = mind.world_first.assemble_brief("open Blender and send the quarterly numbers")
    assert "numbers" in brief["world"]["gaps"]
    assert "not yet in world model" in brief["rendered"]


def test_empty_mind_produces_no_positive_content(setup):
    mind, _ = setup
    brief = mind.world_first.assemble_brief("do something completely novel")
    assert brief["has_positive_content"] is False
    delivery = mind.world_first.deliver("do something completely novel", brief)
    assert delivery["delivered"] is False
    assert "nothing relevant known" in delivery["reason"]


def test_budget_bounds_the_rendering(setup):
    mind, _ = setup
    for i in range(40):
        mind.world.remember_entity(f"entity-{i:02d}", "object")
    text = " ".join(f"entity-{i:02d}" for i in range(40))
    # structural limits already cap the sections; a tight budget must still
    # hold via truncation
    brief = mind.world_first.assemble_brief(text, char_budget=80)
    assert brief["chars"] <= 80 + 20  # truncation marker tolerance
    assert "[truncated]" in brief["rendered"]


def test_assembly_is_fast_and_deterministic(setup):
    mind, _ = setup
    _seed(mind)
    start = time.perf_counter()
    b1 = mind.world_first.assemble_brief("open Blender now")
    b2 = mind.world_first.assemble_brief("open Blender now")
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
    assert b1["rendered"] == b2["rendered"]  # deterministic, no vibes


# ── delivery through the brain's scratchpad ─────────────────────────────────
def test_deliver_encodes_into_working_memory(setup):
    mind, brain = setup
    _seed(mind)
    brief = mind.world_first.assemble_brief("open Blender")
    delivery = mind.world_first.deliver("open Blender", brief)
    assert delivery["delivered"] is True
    assert delivery["gate"]["accepted"] is True
    ctx = brain.working_memory.context_text(max_chars=2000)
    assert "WORLD CONTEXT" in ctx and "Blender" in ctx
    sources = [i["source"] for i in brain.working_memory.snapshot()]
    assert "beanie_world_brief" in sources


def test_gate_rejection_is_recorded_not_overridden(setup):
    mind, _ = setup
    _seed(mind)

    class _StrictRuntime:
        working_memory = WorkingMemory(attention_threshold=0.99)  # nothing gets in

    strict_mind = BeanieMind(db_path=mind.db_path, runtime=_StrictRuntime())
    brief = mind.world_first.assemble_brief("open Blender")
    delivery = strict_mind.world_first.deliver("open Blender", brief)
    assert delivery["delivered"] is False  # the gate decides, honestly
    assert delivery["gate"]["accepted"] is False


# ── the door wiring ─────────────────────────────────────────────────────────
def test_process_runs_world_first_before_the_cycle(setup):
    mind, brain = setup
    _seed(mind)
    result = mind.process("open Blender", modality="voice", conversation_id="c1")
    assert result["success"] is True and brain.calls  # cycle ran unchanged
    # the brief reached the scratchpad the cycle reads
    ctx = brain.working_memory.context_text(max_chars=2000)
    assert "Blender" in ctx
    # and the ledger shows the delivery decision
    records = mind.briefs()
    assert records[0]["delivered"] is True
    assert records[0]["modality"] == "voice"
    assert "WORLD CONTEXT" in records[0]["rendered"]


def test_brief_failure_never_breaks_the_door(setup, monkeypatch):
    mind, brain = setup
    def boom(text, char_budget=900):
        raise RuntimeError("brief exploded")
    monkeypatch.setattr(mind.world_first, "assemble_brief", boom)
    result = mind.process("hello", modality="text")
    assert result["success"] is True  # cycle ran anyway
    assert brain.calls and brain.calls[0]["user_text"] == "hello"
    record = mind.briefs()[0]
    assert record["delivered"] is False
    assert "brief failed" in record["delivery_reason"]


def test_kill_switch_disables_world_first(setup, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ARENA_WORLD_FIRST", "0")
    mind, brain = setup
    _seed(mind)
    mind.process("open Blender", modality="text")
    assert mind.briefs() == []  # nothing assembled, nothing encoded
    sources = [i["source"] for i in brain.working_memory.snapshot()]
    assert "beanie_world_brief" not in sources


# ── owner-visible surface ───────────────────────────────────────────────────
def test_brief_api_preview_and_ledger(setup, tmp_path):
    mind, _ = setup
    _seed(mind)
    mind.process("open Blender", modality="text")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    r = client.get("/mind/brief", params={"text": "open Blender"})
    body = r.json()
    assert body["success"] is True
    assert any(m["name"] == "Blender" for m in body["brief"]["world"]["matched"])

    r = client.get("/mind/briefs")
    briefs = r.json()["briefs"]
    assert briefs and briefs[0]["delivered"] is True
