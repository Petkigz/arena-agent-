"""Phase 12 (Beanie AGI roadmap) — true OS-level generalization (M10).

One platform-free concept layer over all bodies; no per-OS intelligence.
Contracts pinned here:
- intents express as CONCEPTS (open/copy/search/...) with per-body maps
  derived from the live manifest by evidence — no hand-catalogued platform
  tables;
- synonyms resolve to the same concept; non-concept utterances fail typed;
- coverage decides generalization (one body only → does not generalize);
- transfer re-expresses procedures on a target body: resolved capability or
  VISIBLE gap — never a fabricated embodiment;
- taught procedures (Phase 7) are transferable by name;
- the layer expresses and maps; it never executes.
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind


def _explode(*args, **kwargs):
    raise AssertionError("the concept layer must never execute a capability")


FAKE_MANIFEST = {
    "open_file": {
        "name": "open_file", "category": "files", "safety_level": 0,
        "description": "open a file or document on the computer",
        "handler": _explode},
    "android_open_app": {
        "name": "android_open_app", "category": "android", "safety_level": 1,
        "description": "open launch an app on the android phone",
        "handler": _explode},
    "browser_navigate": {
        "name": "browser_navigate", "category": "web", "safety_level": 0,
        "description": "navigate open a url website in the web browser",
        "handler": _explode},
    "copy_file": {
        "name": "copy_file", "category": "files", "safety_level": 0,
        "description": "copy duplicate a file to a destination folder",
        "handler": _explode},
    "search_files": {
        "name": "search_files", "category": "files", "safety_level": 0,
        "description": "search find files and folders on disk",
        "handler": _explode},
    "android_send_sms": {
        "name": "android_send_sms", "category": "android", "safety_level": 2,
        "description": "send sms message communicate via android phone",
        "handler": _explode},
}


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
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest",
                        lambda: dict(FAKE_MANIFEST))
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain, tmp_path, monkeypatch
    BeanieMind.reset_instance()


# ── express: platform-free concepts with per-body evidence ─────────────────
def test_express_maps_one_concept_onto_three_bodies(setup):
    mind, _, _, _ = setup
    rec = mind.os_concepts.express("open the report")
    assert rec["success"] is True and rec["epistemic_kind"] == "concept"
    assert rec["concept"] == "open" and rec["target"] == "report"
    assert [c["action_type"] for c in rec["mapping"]["pc"]] == ["open_file"]
    assert [c["action_type"] for c in rec["mapping"]["android"]] == ["android_open_app"]
    assert [c["action_type"] for c in rec["mapping"]["web"]] == ["browser_navigate"]
    # evidence rides along on every mapping
    assert "open" in rec["mapping"]["pc"][0]["matched_terms"]
    assert rec["generalizes"] is True  # doable on more than one body


def test_synonyms_collapse_to_one_concept(setup):
    mind, _, _, _ = setup
    assert mind.os_concepts.express("launch the report")["concept"] == "open"
    assert mind.os_concepts.express("find my invoices")["concept"] == "search"
    assert mind.os_concepts.express("duplicate the report")["concept"] == "copy"


def test_single_body_coverage_does_not_generalize(setup):
    mind, _, _, _ = setup
    rec = mind.os_concepts.express("copy the report")
    assert rec["concept"] == "copy"
    assert rec["bodies"] == ["pc"]  # only the pc body can copy here
    assert rec["generalizes"] is False


def test_non_concept_is_typed_not_guessed(setup):
    mind, _, _, _ = setup
    rec = mind.os_concepts.express("teleport the file")
    assert rec["success"] is False
    assert "no OS concept verb" in rec["reason"]
    assert "open" in rec["concept_verbs"]
    assert mind.os_concepts.express("")["success"] is False


# ── transfer: learned on one body, generalized to another ──────────────────
def test_transfer_resolves_or_flags_every_step(setup):
    mind, _, _, _ = setup
    rec = mind.os_concepts.transfer(
        "android",
        steps=["open the settings app", "copy the report", "teleport it"])
    assert rec["success"] is True and rec["to_platform"] == "android"
    s_open, s_copy, s_tele = rec["steps"]
    assert s_open["capability"] == "android_open_app"
    assert s_open["status"] == "resolved on target body"
    assert s_copy["capability"] is None
    assert "visible gap" in s_copy["status"]          # no fabricated embodiment
    assert s_tele["concept"] is None and "cannot transfer" in s_tele["status"]
    assert rec["resolved"] == 1 and rec["gaps"] == 2
    assert rec["generalized"] is False


def test_transfer_fully_generalizes_when_the_body_can_do_it_all(setup):
    mind, _, _, _ = setup
    rec = mind.os_concepts.transfer(
        "pc", steps=["open the report", "copy the report", "search for invoices"])
    assert rec["resolved"] == 3 and rec["gaps"] == 0
    assert rec["generalized"] is True
    assert [s["capability"] for s in rec["steps"]] == \
        ["open_file", "copy_file", "search_files"]


def test_transfer_validation_is_typed(setup):
    mind, _, _, _ = setup
    assert mind.os_concepts.transfer("starship", steps=["open it"])["success"] is False
    assert mind.os_concepts.transfer("pc")["success"] is False
    assert mind.os_concepts.transfer("pc", procedure="no-such-procedure")["success"] is False


def test_taught_procedures_transfer_by_name(setup):
    mind, _, tmp_path, monkeypatch = setup
    # teach a procedure through the Phase-7 conversation, hermetically
    from app.database import db as app_db
    monkeypatch.setattr(app_db, "db_path", str(tmp_path / "legacy.db"))
    app_db._init_db()
    teach = mind.teaching
    cid = "c-teach"
    teach.handle_message(cid, "watch this")
    teach.handle_message(cid, "this is how I move my reports")
    teach.handle_message(cid, "open the report")
    teach.handle_message(cid, "copy the report")
    teach.handle_message(cid, "that's it")
    reply = teach.handle_message(cid, "yes")
    assert "move-reports" in reply
    name = "move-reports"

    rec = mind.os_concepts.transfer("android", procedure=name)
    assert rec["success"] is True
    assert "taught procedure" in rec["source"] and name in rec["source"]
    assert rec["steps"][0]["capability"] == "android_open_app"  # generalized!
    assert rec["steps"][1]["capability"] is None                # honest gap
    assert rec["resolved"] == 1 and rec["gaps"] == 1


# ── the vocabulary surface ──────────────────────────────────────────────────
def test_concepts_surface_shows_coverage(setup):
    mind, _, _, _ = setup
    rec = mind.os_concepts.concepts()
    assert rec["success"] is True
    assert rec["current_body"] in ("linux", "macos", "windows")
    verbs = rec["concept_verbs"]
    assert verbs["open"]["generalizes"] is True    # three bodies can open
    assert verbs["copy"]["generalizes"] is False   # only the pc body here
    assert verbs["copy"]["coverage"] == {"pc": 1, "android": 0, "web": 0}
    assert set(verbs) >= {"open", "close", "move", "copy", "rename", "search",
                          "install", "configure", "read", "write", "observe",
                          "click", "type", "navigate", "communicate"}


# ── API contract ────────────────────────────────────────────────────────────
def test_os_concepts_api(setup):
    mind, _, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.post("/mind/os/express", json={"intent": "open the report"}).json()
    assert body["concept"] == "open" and body["generalizes"] is True

    body = client.post("/mind/os/transfer", json={
        "to_platform": "android",
        "steps": ["open the report", "copy the report"]}).json()
    assert body["resolved"] == 1 and body["gaps"] == 1

    body = client.get("/mind/os/concepts").json()
    assert body["concept_verbs"]["open"]["generalizes"] is True

    assert client.post("/mind/os/express", json={"intent": ""}).status_code == 422
