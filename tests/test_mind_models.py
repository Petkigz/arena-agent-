"""Phases 3–5 (Beanie AGI roadmap) — world model, self model, unified memory.

Built on the REAL stores (WorldModel, MemoryStore) over isolated DBs, with
fake capability catalogs so tests never build the 184-entry manifest.

Phase 3 — the world is something Beanie reasons about (ontology, teaching,
          provenance-tracked state, pre-action understanding with visible gaps).
Phase 4 — 'I don't know' is a genuine internal state (the roadmap's exact
          acceptance example: knowledge unknown / confidence 0.08 /
          possible_actions investigate-ask-observe-search).
Phase 5 — one memory over eight kinds, incl. NEW social memory and
          meta-memory ('I remember doing this' vs 'I think I know how').
"""

from __future__ import annotations

import pytest

from app.cognition.memory import MemoryStore
from app.cognition.world_model import WorldModel
from app.mind.memory_facade import MetaMemory, SocialMemoryStore, UnifiedMemory
from app.mind.self_facade import SelfModelFacade
from app.mind.world_facade import WORLD_ENTITY_TYPES, WorldModelFacade

FAKE_CATALOG = {
    "search_files": {
        "name": "Search files", "category": "filesystem", "safety_level": 0,
        "description": "search files on the filesystem by name or content",
    },
    "send_encrypted_message": {
        "name": "Send encrypted message", "category": "messaging", "safety_level": 3,
        "description": "send an encrypted message to a contact",
    },
}


@pytest.fixture()
def world(tmp_path):
    return WorldModelFacade(WorldModel(db_path=str(tmp_path / "world.db")))


@pytest.fixture()
def store(tmp_path):
    return MemoryStore(tmp_path / "memory.db")


# ── PHASE 3: WORLD MODEL ────────────────────────────────────────────────────
def test_world_ontology_matches_roadmap_categories():
    assert set(WORLD_ENTITY_TYPES) == {
        "person", "place", "device", "application", "file", "website",
        "account", "object", "concept", "event", "process",
    }


def test_remember_entity_and_landscape(world):
    out = world.remember_entity("Blender", "application", {"vendor": "blender.org"})
    assert out["success"] is True
    out = world.remember_entity("project plan.docx", "file")
    assert out["success"] is True
    stats = world.stats()
    assert stats["entity_count"] == 2
    assert stats["by_type"] == {"application": 1, "file": 1}
    assert stats["ontology_size"] == len(WORLD_ENTITY_TYPES)
    assert world.entity("Blender")["entity_type"] == "application"


def test_unknown_entity_type_rejected_typed(world):
    out = world.remember_entity("ghost", "spirit")
    assert out["success"] is False
    assert "spirit" in out["reason"]
    assert set(out["valid_types"]) == set(WORLD_ENTITY_TYPES)


def test_state_fields_never_stored_in_attributes(world):
    out = world.remember_entity("Arena", "application",
                                attributes={"status": "running", "version": "1.0"})
    assert out["success"] is True
    assert out["state_fields_belong_in_observations"] == ["status"]
    assert world.entity("Arena")["attributes"] == {"version": "1.0"}


def test_relate_requires_known_entities_then_links(world):
    out = world.relate("owner", "uses", "Blender")
    assert out["success"] is False and "unknown entities" in out["reason"]
    world.remember_entity("owner", "person")
    world.remember_entity("Blender", "application")
    out = world.relate("owner", "uses", "Blender")
    assert out["success"] is True
    known = world.what_do_i_know_about("owner")
    assert known["known"] is True
    assert any(r["predicate"] == "uses" and r["object"] == "Blender"
               for r in known["relationships"])


def test_observe_state_requires_provenance_and_appears(world):
    world.remember_entity("Blender", "application")
    out = world.observe_state("Blender", "status", "running", source="")
    assert out["success"] is False and "provenance" in out["reason"]
    out = world.observe_state("Blender", "status", "running", source="os_process_probe")
    assert out["success"] is True
    known = world.what_do_i_know_about("Blender")
    assert known["recent_observations"][0]["predicate"] == "status"
    assert known["recent_observations"][0]["source"] == "os_process_probe"


def test_understand_matches_entities_and_keeps_gaps_visible(world):
    world.remember_entity("Blender", "application")
    world.remember_entity("report.pdf", "file", {"aliases": ["quarterly"]})
    world.observe_state("Blender", "status", "running", source="os_process_probe")
    u = world.understand("open Blender and send the quarterly numbers")
    matched = {m["entity"]["name"] for m in u["matched_entities"]}
    assert matched == {"Blender", "report.pdf"}  # alias matched too
    blender = next(m for m in u["matched_entities"] if m["entity"]["name"] == "Blender")
    assert blender["latest_states"]["status"]["source"] == "os_process_probe"
    assert "Blender" not in u["gaps"]
    assert "numbers" in u["gaps"]  # unknown stays UNKNOWN — Phase 9 investigates


def test_world_facade_unwired_is_honest():
    bare = WorldModelFacade(None)
    assert bare.understand("anything")["reason"] == "world model not wired"
    assert bare.remember_entity("x", "file")["success"] is False
    assert bare.what_do_i_know_about("x")["known"] is False


# ── PHASE 4: SELF MODEL ─────────────────────────────────────────────────────
def test_assess_unknown_task_is_genuine_ignorance(store):
    facade = SelfModelFacade(manifest_getter=lambda: FAKE_CATALOG, memory=store)
    state = facade.assess("configure the warp drive")
    assert state["knowledge"] == "unknown"
    assert state["confidence"] == 0.08  # the roadmap's number, exactly
    assert set(state["possible_actions"]) == {
        "investigate", "ask_owner", "observe_demonstration", "search"}
    assert state["evidence"]["capability_matches"] == []
    assert state["evidence"]["memory_hits"] == []


def test_assess_capability_match_is_partial_without_experience(store):
    facade = SelfModelFacade(manifest_getter=lambda: FAKE_CATALOG, memory=store)
    state = facade.assess("search my files")
    assert state["knowledge"] == "partial"
    assert state["confidence"] >= 0.35
    assert state["evidence"]["capability_matches"][0]["action_type"] == "search_files"


def test_assess_known_with_successful_experience(store):
    store.add("episodic", "searched files for the owner, results verified",
              importance=0.7, source="verified_cycle", success=True)
    facade = SelfModelFacade(manifest_getter=lambda: FAKE_CATALOG, memory=store)
    state = facade.assess("search my files")
    assert state["knowledge"] == "known"
    assert state["confidence"] >= 0.75
    assert state["evidence"]["successful_experience_count"] == 1
    assert state["possible_actions"][0] == "execute"


def test_authority_is_not_intelligence_level3_still_understood(store):
    facade = SelfModelFacade(manifest_getter=lambda: FAKE_CATALOG, memory=store)
    caps = facade.capabilities()
    assert caps["count"] == 2
    assert caps["by_safety_level"]["L3"] == 1  # understood, not authorized
    assert "understanding" in caps["note"]


def test_limitations_honest_without_hardware_model():
    facade = SelfModelFacade(manifest_getter=lambda: {})
    lim = facade.limitations()
    assert lim["hardware_self_model"] == {"status": "unavailable"}


def test_profile_shape():
    facade = SelfModelFacade(manifest_getter=lambda: FAKE_CATALOG)
    profile = facade.profile(memory_counts={"episodic": 3})
    assert profile["success"] is True
    assert profile["capabilities"]["count"] == 2
    assert profile["experiences"] == {"episodic": 3}
    assert "Phase 17" in profile["personality"]


# ── PHASE 5: UNIFIED MEMORY ─────────────────────────────────────────────────
def test_counts_cover_every_kind(tmp_path, store):
    social = SocialMemoryStore(tmp_path / "arena.db")
    mem = UnifiedMemory(memory=store, social=social, identity=None, preferences=None)
    store.add("episodic", "helped organize downloads", importance=0.6, success=True)
    store.add("semantic", "owner keeps projects in ~/projects", importance=0.5)
    social.remember("Alice", relationship="owner's sister")
    counts = mem.counts()
    for key in ("episodic", "semantic", "procedural", "lesson",
                "working_items", "social", "preference", "autobiographical_milestones"):
        assert key in counts
    assert counts["episodic"] == 1
    assert counts["semantic"] == 1
    assert counts["social"] == 1
    assert counts["preference"] == "unwired"


def test_remember_is_typed(tmp_path, store):
    mem = UnifiedMemory(memory=store, social=SocialMemoryStore(tmp_path / "arena.db"))
    assert mem.remember("semantic", "the sky is blue")["success"] is True
    bad = mem.remember("nonsense", "x")
    assert bad["success"] is False and "unsupported memory kind" in bad["reason"]


def test_social_memory_lifecycle(tmp_path):
    social = SocialMemoryStore(tmp_path / "arena.db")
    assert social.remember("Alice", relationship="owner's sister")["success"] is True
    assert social.remember("", )["success"] is False
    assert social.remember("Bob", kind="robot")["success"] is False
    rec = social.recall("Alice")
    assert rec["relationship"] == "owner's sister" and rec["interactions"] == 0
    assert social.record_interaction("Alice")["success"] is True
    assert social.record_interaction("stranger")["success"] is False
    assert social.recall("Alice")["interactions"] == 1
    assert social.forget("Alice")["success"] is False  # needs owner confirmation
    assert social.forget("Alice", confirm_owner=True)["success"] is True
    assert social.recall("Alice") is None


def test_unified_remember_routes_social_kind(tmp_path, store):
    mem = UnifiedMemory(memory=store, social=SocialMemoryStore(tmp_path / "arena.db"))
    out = mem.remember("social", "Carol", source="owner_taught")
    assert out["success"] is True
    assert mem.social.recall("Carol") is not None


def test_meta_memory_the_roadmap_distinction(store):
    meta = MetaMemory(store)
    # nothing yet — honest unknown
    first = meta.ask("organize the downloads folder")
    assert first["status"] == "unknown" and first["statement"] == "I don't know."
    # semantic only — heard of it
    store.add("semantic", "organizing downloads means grouping files by project then type",
              importance=0.5)
    assert meta.ask("organize the downloads folder")["status"] == "heard_about"
    # procedural — thinks she knows how, never did
    store.add("procedural", "to organize downloads: list files, group by project, then type",
              importance=0.6)
    assert meta.ask("organize the downloads folder")["status"] == "knows_how"
    # episodic success — genuinely remembers doing it
    store.add("episodic", "organized the downloads folder into project groups; verified",
              importance=0.8, success=True, source="verified_cycle")
    final = meta.ask("organize the downloads folder")
    assert final["status"] == "remembered_done"
    assert final["statement"] == "I remember doing this."
    assert final["evidence"]  # classification cites its evidence
    assert final["counts"]["episodic_success"] == 1


def test_meta_memory_unwired_is_honest():
    assert MetaMemory(None).ask("anything")["status"] == "unknown"


# ── MIND INTEGRATION: facades as organs of BeanieMind ───────────────────────
def test_mind_wires_world_self_memory_organs(tmp_path, store, monkeypatch):
    from app.mind import BeanieMind

    class _StubBrain:
        def __init__(self):
            self.world = WorldModel(db_path=str(tmp_path / "world.db"))
            self.memory = store
            self.working_memory = None
            self.hardware_self_model = {}
            self.phase7_preferences = None

        def process_cognitive_cycle(self, user_text, **kw):
            return {"success": True}

    fake_catalog = {"open_application": {"name": "Open application",
                                          "category": "os_control", "safety_level": 1,
                                          "description": "open an application"}}
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: fake_catalog)
    BeanieMind.reset_instance()
    brain = _StubBrain()
    mind = BeanieMind(db_path=tmp_path / "arena.db", runtime=brain)

    # world organ
    assert mind.world.remember_entity("owner", "person")["success"] is True
    assert mind.world.stats()["entity_count"] == 1
    # self organ — assesses against the fake catalog + real memory store
    assessment = mind.self_model.assess("configure the warp drive")
    assert assessment["knowledge"] == "unknown"
    assert assessment["confidence"] == 0.08
    # memory organ
    assert mind.memory.remember("semantic", "owner prefers voice")["success"] is True
    assert mind.memory.counts()["semantic"] == 1
    assert mind.memory.meta.ask("owner prefers voice")["status"] == "heard_about"

    # the state snapshot deepens through the facades
    state = mind.state()
    assert state["world"]["data"]["by_type"] == {"person": 1}
    assert state["world"]["data"]["ontology_size"] == len(WORLD_ENTITY_TYPES)
    assert state["self"]["data"]["capabilities_count"] == 1
    assert state["learned_knowledge"]["data"]["unified_memory_counts"]["semantic"] == 1
    BeanieMind.reset_instance()


def test_mind_api_phases_3_to_5(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    from app.mind import BeanieMind

    class _StubBrain:
        def __init__(self):
            self.world = WorldModel(db_path=str(tmp_path / "world.db"))
            self.memory = MemoryStore(tmp_path / "memory.db")
            self.working_memory = None
            self.hardware_self_model = {}
            self.phase7_preferences = None

        def process_cognitive_cycle(self, user_text, **kw):
            return {"success": True}

    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: FAKE_CATALOG)
    BeanieMind.reset_instance()
    BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=_StubBrain())

    app = FastAPI()
    app.include_router(mind_router)
    c = TestClient(app)

    # world
    assert c.get("/mind/world").json()["ontology"]["entity_types"]["file"]
    r = c.post("/mind/world/entities",
               json={"name": "Blender", "entity_type": "application"})
    assert r.json()["success"] is True
    r = c.post("/mind/world/entities", json={"name": "x", "entity_type": "bogus"})
    assert r.status_code == 200 and r.json()["success"] is False  # typed, not 500
    r = c.post("/mind/world/observations",
               json={"subject": "Blender", "predicate": "status",
                     "value": "running", "source": "os_process_probe"})
    assert r.json()["success"] is True
    about = c.get("/mind/world/about", params={"name": "Blender"}).json()
    assert about["known"] is True
    u = c.get("/mind/world/understand",
              params={"text": "open Blender and continue editing"}).json()
    assert any(m["entity"]["name"] == "Blender" for m in u["matched_entities"])

    # self — the roadmap's acceptance example, over HTTP
    r = c.get("/mind/self/assess", params={"task": "configure the warp drive"})
    body = r.json()
    assert body["knowledge"] == "unknown"
    assert body["confidence"] == 0.08
    assert "observe_demonstration" in body["possible_actions"]
    assert c.get("/mind/self").json()["capabilities"]["count"] == 2

    # memory + meta-memory + social
    assert c.get("/mind/memory").json()["counts"]["episodic"] == 0
    r = c.post("/mind/memory", json={"kind": "episodic",
                                     "content": "searched files for the owner, verified",
                                     "success": True, "source": "verified_cycle"})
    assert r.json()["success"] is True
    r = c.get("/mind/memory/meta", params={"q": "searched files for the owner"})
    assert r.json()["status"] == "remembered_done"
    r = c.post("/mind/memory/social",
               json={"name": "Alice", "relationship": "owner's sister"})
    assert r.json()["success"] is True
    social = c.get("/mind/memory/social").json()
    assert social["count"] == 1 and social["people"][0]["name"] == "Alice"
    BeanieMind.reset_instance()
