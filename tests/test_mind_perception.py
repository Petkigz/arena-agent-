"""Phase 13 (Beanie AGI roadmap) — continuous perception.

screen/camera/audio/phone/desktop/network/environment → perception →
significance. Contracts pinned here:
- perceptions are TYPED statements about sense channels; unknown channels
  rejected;
- novelty comes from the Phase-6 loop: novel perceptions store knowledge,
  repeated ones rehearse — "don't react to everything" is the dedupe;
- significance is evidence with REASONS (urgency / novelty / touches an
  open unknown) — inspectable, not vibes;
- perceptions touching open unknowns close them (curiosity integration);
- the silent watcher's buffered changes ingest through the same door;
- perception NEVER acts; perception never breaks the task.
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


class _Change:
    def __init__(self, change_type, subject, current_state, source, priority="normal"):
        self.change_type = change_type
        self.subject = subject
        self.previous_state = None
        self.current_state = current_state
        self.source = source
        self.priority = priority


class _Observer:
    def __init__(self, changes):
        self._changes = changes
        self.drains = []

    def get_changes(self, clear=True):
        self.drains.append(clear)
        out, self._changes = self._changes, []
        return out


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain, monkeypatch
    BeanieMind.reset_instance()


# ── typed perceptions ───────────────────────────────────────────────────────
def test_perception_is_typed(setup):
    mind, _, _ = setup
    bad = mind.perception.perceive("telepathy", "something")
    assert bad["success"] is False and "unknown sense channel" in bad["reason"]
    assert "screen" in bad["modalities"]
    assert mind.perception.perceive("screen", "")["success"] is False


def test_novel_perception_is_significant_and_stored(setup):
    mind, brain, _ = setup
    rec = mind.perception.perceive(
        "screen", "a popup appeared over the document editor", source="probe")
    assert rec["success"] is True and rec["epistemic_kind"] == "perception"
    assert rec["novelty"] == "novel" and rec["significant"] is True
    assert any("novel" in r for r in rec["reasons"])
    assert rec["acted"] is False
    assert rec["stored_memory_id"]  # novel observations become knowledge
    assert mind.memory.counts()["semantic"] == 1


def test_repeated_perception_is_background_not_noise(setup):
    mind, brain, _ = setup
    content = "the wifi network switched to guest"
    first = mind.perception.perceive("network", content)
    second = mind.perception.perceive("network", content)
    assert first["novelty"] == "novel" and first["significant"] is True
    assert second["novelty"] == "reinforces" and second["significant"] is False
    assert any("background" in r for r in second["reasons"])
    assert mind.memory.counts()["semantic"] == 1  # rehearsed, not duplicated
    stats = mind.perception.stats()
    assert stats["perceptions"] == 2
    assert stats["significant"] == 1 and stats["background"] == 1


def test_urgency_makes_a_perception_significant(setup):
    mind, _, _ = setup
    content = "battery dropped below five percent"
    mind.perception.perceive("desktop", content)          # first: novel
    urgent = mind.perception.perceive("desktop", content, urgent=True)
    # repeated, but the probe declared urgency → still significant
    assert urgent["novelty"] == "reinforces"
    assert urgent["significant"] is True
    assert any("urgent" in r for r in urgent["reasons"])


# ── curiosity integration ───────────────────────────────────────────────────
def test_perception_touching_an_unknown_closes_it(setup):
    mind, _, _ = setup
    mind.curiosity.register("printer driver")
    rec = mind.perception.perceive(
        "environment", "the printer driver updated itself overnight")
    assert rec["significant"] is True
    assert any("open unknown" in r for r in rec["reasons"])
    # and the learning door closed the unknown via the knowledge path
    assert mind.curiosity.stats()["resolved_by"].get("knowledge") == 1


def test_buried_unknowns_are_still_noticed(setup):
    """Priority order must not hide an unknown from a perception — buried
    unknowns are exactly the ones perceptions should surface."""
    mind, _, _ = setup
    for i in range(30):  # bury the target under higher-priority unknowns
        mind.curiosity.register(f"unknown topic number {i}")
        mind.curiosity.register(f"unknown topic number {i}")  # compounding
    mind.curiosity.register("zanzibar ferry schedule")
    rec = mind.perception.perceive(
        "environment", "the zanzibar ferry schedule changed to hourly")
    assert rec["significant"] is True
    assert any("zanzibar ferry schedule" in r for r in rec["reasons"])


# ── the silent watcher feeds the sense ─────────────────────────────────────
def test_drain_ingests_environment_changes(setup):
    mind, _, monkeypatch = setup
    import app.perception.background_observer as bo
    obs = _Observer([
        _Change("process_started", "blender", "running", "process_probe"),
        _Change("device_connected", "usb-drive", "mounted", "device_probe",
                priority="urgent"),
    ])
    monkeypatch.setattr(bo, "observer_instance", obs)
    res = mind.perception.drain_background_observer()
    assert res["success"] is True and res["ingested"] == 2
    assert obs.drains == [True]  # drained, not peeked
    stream = mind.perception.stream()
    assert stream[0]["modality"] == "environment"
    assert stream[0]["significant"] is True          # the urgent one
    assert any("urgent" in r for r in stream[0]["reasons"])


def test_drain_without_watcher_is_honest(setup):
    mind, _, monkeypatch = setup
    import app.perception.background_observer as bo
    monkeypatch.setattr(bo, "observer_instance", None)
    res = mind.perception.drain_background_observer()
    assert res["success"] is True and res["ingested"] == 0
    assert "not running" in res["note"]


def test_process_drains_perceptions_each_turn(setup):
    mind, _, monkeypatch = setup
    import app.perception.background_observer as bo
    obs = _Observer([_Change("file_changed", "report.docx", "modified", "fs_probe")])
    monkeypatch.setattr(bo, "observer_instance", obs)
    mind.process("hello", modality="text")
    assert obs.drains == [True]
    assert mind.perception.stream()[0]["content"].startswith("file_changed")


def test_perception_kill_switch(setup):
    mind, _, monkeypatch = setup
    from app.config import settings
    import app.perception.background_observer as bo
    obs = _Observer([_Change("file_changed", "x.txt", "modified", "fs_probe")])
    monkeypatch.setattr(bo, "observer_instance", obs)
    monkeypatch.setattr(settings, "ARENA_PERCEPTION", "0")
    mind.process("hello", modality="text")
    assert obs.drains == []  # the door stopped draining
    # the owner surface still works
    assert mind.perception.perceive("screen", "still works")["success"] is True


# ── the existing observe() lane gains the perception pass ───────────────────
def test_observe_lane_feeds_perception(setup):
    mind, _, _ = setup
    res = mind.observe("voice", {"summary": "owner asked about the invoice",
                                 "modality": "audio"})
    assert res["recorded"] is True and res["acted"] is False
    assert res["perception"]["success"] is True
    assert res["perception"]["modality"] == "audio"
    # default channel when none declared
    res = mind.observe("chat", {"summary": "hello"})
    assert res["perception"]["modality"] == "owner"


# ── API contract ────────────────────────────────────────────────────────────
def test_perception_api(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.post("/mind/perception", json={
        "modality": "screen", "content": "a dialog appeared"}).json()
    assert body["success"] is True and body["novelty"] == "novel"

    body = client.post("/mind/perception", json={
        "modality": "sixth-sense", "content": "x"}).json()
    assert body["success"] is False  # typed, not 500

    body = client.post("/mind/perception/drain").json()
    assert body["success"] is True

    body = client.get("/mind/perception").json()
    assert body["perceptions"] == 1 and body["significant"] == 1
    assert body["stream"][0]["modality"] == "screen"

    assert client.post("/mind/perception",
                       json={"modality": "screen", "content": ""}).status_code == 422
