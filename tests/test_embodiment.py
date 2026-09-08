"""Phase 11 (Beanie AGI roadmap) — embodied intelligence.

The existing capabilities become the motor system. The key change: Beanie
doesn't know "tool #73" — she knows "I need to interact with my phone" and
the capability layer figures out how. Contracts pinned here:
- concepts in, ranked motor pathways out, every candidate carrying its
  evidence (matched terms) — no vibes;
- authority ≠ intelligence: a pathway she understands but is not authorized
  for is surfaced as requires_owner_approval — not hidden, not refused;
- the organ PLANS, it NEVER executes — capability handlers must not be
  invoked by the motor system;
- a missing motor pathway is an honest None AND becomes an open unknown;
- the existing tool_matcher stays the primary resolver where it fires.
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind


def _explode(*args, **kwargs):
    raise AssertionError("the motor system must never execute a capability")


FAKE_MANIFEST = {
    "open_application": {
        "name": "open_application", "category": "applications",
        "safety_level": 1,
        "description": "open launch start an application program",
        "handler": _explode},
    "android_send_sms": {
        "name": "android_send_sms", "category": "android",
        "safety_level": 2,
        "description": "send sms text message via adb to the phone android device",
        "handler": _explode},
    "search_files": {
        "name": "search_files", "category": "files",
        "safety_level": 0,
        "description": "search find files and folders on disk",
        "handler": _explode},
    "wipe_system": {
        "name": "wipe_system", "category": "system",
        "safety_level": 3,
        "description": "destructive wipe erase the whole system",
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
    yield mind, brain, monkeypatch
    BeanieMind.reset_instance()


# ── concepts in, motor pathways out ────────────────────────────────────────
def test_concept_becomes_pathway(setup):
    mind, _, _ = setup
    rec = mind.embodiment.motor_plan("I need to interact with my phone")
    assert rec["success"] is True and rec["epistemic_kind"] == "plan"
    assert rec["motor_path"] == "android_send_sms"
    cand = rec["candidates"][0]
    assert cand["embodiment"] == "android"
    # evidence rides along — which concept terms actually matched
    assert set(cand["matched_terms"]) >= {"phone", "android"}


def test_concept_aliases_expand_the_body(setup):
    mind, _, _ = setup
    # 'documents' says nothing about files, but the concept vocabulary
    # knows they are the same body part
    rec = mind.embodiment.motor_plan("look through my documents")
    assert rec["success"] is True
    assert any(c["action_type"] == "search_files" for c in rec["candidates"])


def test_authority_is_surfaced_not_refused(setup):
    mind, _, _ = setup
    rec = mind.embodiment.motor_plan("wipe the whole system")
    assert rec["success"] is True
    wipe = next(c for c in rec["candidates"] if c["action_type"] == "wipe_system")
    # she UNDERSTANDS the pathway (authority ≠ intelligence) but it is
    # flagged for owner approval, never silently available
    assert wipe["requires_owner_approval"] is True
    assert wipe["safety_level"] == 3
    # and a safe pathway is not flagged
    safe = mind.embodiment.motor_plan("search for a file")
    sc = next(c for c in safe["candidates"] if c["action_type"] == "search_files")
    assert sc["requires_owner_approval"] is False


def test_missing_pathway_is_honest_and_becomes_unknown(setup):
    mind, _, _ = setup
    rec = mind.embodiment.motor_plan("teleport to mars")
    assert rec["success"] is True
    assert rec["motor_path"] is None and rec["candidates"] == []
    assert "no motor pathway" in rec["note"]
    # the motor gap is now an open unknown in the curiosity system
    unknowns = [u["topic"] for u in mind.curiosity.curiosities()]
    assert any("teleport to mars" in t for t in unknowns)


def test_the_organ_never_executes(setup):
    mind, _, _ = setup
    # exercising every pathway in the plan surface must not trip a handler
    for intent in ("open the application", "send a text on the phone",
                   "search for a file", "wipe the whole system"):
        assert mind.embodiment.motor_plan(intent)["success"] is True
    # (handlers all raise AssertionError if ever invoked)


# ── the existing tool_matcher stays primary where it fires ─────────────────
def test_primary_matcher_is_promoted(setup):
    mind, _, monkeypatch = setup
    from app.cognition import tool_matcher

    class _Match:
        action_type = "search_files"
        score = 0.91
        matched_terms = ("file",)

    monkeypatch.setattr(tool_matcher, "match_control_tool",
                        lambda intent, manifest=None: _Match())
    rec = mind.embodiment.motor_plan("please find the report file")
    assert rec["motor_path"] == "search_files"
    assert rec["candidates"][0].get("primary_match") is True
    assert rec["candidates"][0].get("primary_score") == 0.91


# ── body image ──────────────────────────────────────────────────────────────
def test_body_map_reads_the_whole_body(setup):
    mind, _, _ = setup
    body = mind.embodiment.body_map()
    assert body["success"] is True
    assert body["capabilities"] == len(FAKE_MANIFEST)
    assert set(body["by_category"]) == {"applications", "android", "files", "system"}
    filtered = mind.embodiment.body_map(concept="phone")
    assert filtered["success"] is True
    assert filtered["pathways"] == ["android_send_sms"]


# ── typed failures ──────────────────────────────────────────────────────────
def test_typed_failures(setup):
    mind, _, monkeypatch = setup
    assert mind.embodiment.motor_plan("")["success"] is False
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest",
                        lambda: (_ for _ in ()).throw(RuntimeError("no manifest")))
    assert "manifest unavailable" in mind.embodiment.motor_plan("open it")["reason"]


# ── API contract ────────────────────────────────────────────────────────────
def test_embodiment_api(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.post("/mind/embodiment/plan",
                       json={"intent": "interact with my phone"}).json()
    assert body["success"] is True and body["motor_path"] == "android_send_sms"

    body = client.get("/mind/embodiment").json()
    assert body["capabilities"] == len(FAKE_MANIFEST)

    body = client.get("/mind/embodiment", params={"concept": "phone"}).json()
    assert body["pathways"] == ["android_send_sms"]

    assert client.post("/mind/embodiment/plan",
                       json={"intent": ""}).status_code == 422
