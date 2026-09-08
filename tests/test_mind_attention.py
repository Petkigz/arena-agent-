"""Phase 14 (Beanie AGI roadmap) — attention (M8 attention significance).

perception → ATTENTION → significance. Contracts pinned here:
- attention classifies each perception onto the roadmap ladder
  (owner_speaking / important_change / anomaly / unfinished_goal /
  learned_curiosity / background_observation) from EVIDENCE on the record,
  never vibes;
- repeats of already-attended content are demoted to background with a
  reason — "don't react to everything" applies to thought too;
- review() attends only perceptions newer than its watermark (no
  re-attendance), and surfaces ONE open unknown as learned curiosity only
  when nothing more pressing is pending (with cooldown);
- an anomaly/important change overlapping the current task raises an
  advisory ("may interfere with what you're doing");
- attention DECIDES WHAT DESERVES THOUGHT — acted is False on every
  verdict; attention never breaks the task (kill switch honored, fail-open).
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind
from app.mind.attention import LADDER


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
    yield mind, brain, monkeypatch
    BeanieMind.reset_instance()


def _perc(content, modality="screen", novelty="novel", reasons=None, pid=None):
    return {"content": content, "modality": modality, "novelty": novelty,
            "reasons": reasons or [], "perception_id": pid}


# ── the ladder is evidence-based ────────────────────────────────────────────
def test_owner_speech_outranks_the_environment(setup):
    mind, _, _ = setup
    v = mind.attention.notice(_perc("please send the report", modality="owner"))
    assert v["level"] == "owner_speaking"
    assert v["rank"] == LADDER["owner_speaking"]
    assert v["acted"] is False


def test_urgent_probe_is_an_important_change(setup):
    mind, _, _ = setup
    v = mind.attention.notice(_perc(
        "process crashed: editor is now unresponsive",
        novelty="reinforces", reasons=["the probe declared it urgent"]))
    assert v["level"] == "important_change"
    assert any("urgent" in r for r in v["reasons"])


def test_novel_perception_is_an_anomaly(setup):
    mind, _, _ = setup
    v = mind.attention.notice(_perc("a popup appeared over the editor"))
    assert v["level"] == "anomaly"
    assert any("novel" in r for r in v["reasons"])
    assert v["acted"] is False


def test_unknown_touch_is_an_unfinished_goal(setup):
    mind, _, _ = setup
    v = mind.attention.notice(_perc(
        "printer spooler restarted", novelty="reinforces",
        reasons=["touches open unknown(s): printer offline"]))
    assert v["level"] == "unfinished_goal"


def test_plain_known_perception_is_background(setup):
    mind, _, _ = setup
    v = mind.attention.notice(_perc("the clock ticks", novelty="reinforces"))
    assert v["level"] == "background_observation"
    assert v["rank"] == LADDER["background_observation"]


# ── repeats are demoted, not re-thought ─────────────────────────────────────
def test_repeat_is_demoted_to_background(setup):
    mind, _, _ = setup
    first = mind.attention.notice(_perc("popup over the editor"))
    second = mind.attention.notice(_perc("popup over the editor"))
    assert first["level"] == "anomaly"
    assert second["level"] == "background_observation"
    assert any("repeat" in r for r in second["reasons"])


# ── the roadmap scenario: may interfere with what you're doing ──────────────
def test_advisory_raised_when_change_overlaps_current_task(setup):
    mind, _, _ = setup
    mind.attention.set_task("editing the quarterly report")
    v = mind.attention.notice(_perc("popup appeared over the quarterly report"))
    assert v["advisory"] is not None
    assert "quarterly report" in v["advisory"]
    assert "interfere" in v["advisory"]
    assert any("current task" in r for r in v["reasons"])
    assert v["acted"] is False
    assert mind.attention.advisories()[-1]["advisory"] == v["advisory"]


def test_no_advisory_when_change_is_unrelated_to_task(setup):
    mind, _, _ = setup
    mind.attention.set_task("editing the quarterly report")
    v = mind.attention.notice(_perc("a new moon phase wallpaper appeared"))
    assert v["level"] == "anomaly"
    assert v["advisory"] is None


# ── review: watermark + curiosity surfacing ─────────────────────────────────
def test_review_attends_each_perception_exactly_once(setup):
    mind, _, _ = setup
    mind.perception.perceive("screen", "a dialog opened on screen one")
    mind.perception.perceive("network", "the wifi switched networks again")
    r1 = mind.attention.review(task="writing notes")
    assert r1["success"] is True and r1["attended"] == 2
    assert r1["current_task"] == "writing notes"
    r2 = mind.attention.review()
    assert r2["attended"] == 0  # watermark: nothing new, nothing re-thought


def test_review_surfaces_one_open_unknown_only_when_quiet(setup):
    mind, _, _ = setup
    mind.curiosity.register("why does the printer drop offline",
                            source="test", context="")
    r1 = mind.attention.review()
    levels = r1["by_level"]
    assert levels.get("learned_curiosity") == 1
    verdict = r1["verdicts"][0]
    assert "printer" in verdict["content"] and verdict["acted"] is False
    # cooldown: the same unknown is not re-surfaced every review
    r2 = mind.attention.review()
    assert r2["attended"] == 0
    assert r2["by_level"].get("learned_curiosity", 0) == 0


def test_current_focus_is_the_highest_rung(setup):
    mind, _, _ = setup
    mind.perception.perceive("screen", "the clock widget refreshed")
    mind.perception.perceive(
        "environment", "editor crashed and is now unresponsive", urgent=True)
    r = mind.attention.review(task="editing the quarterly report")
    assert r["current_focus"]["level"] == "important_change"
    assert r["by_level"].get("important_change") == 1


# ── surfaces + state room ───────────────────────────────────────────────────
def test_snapshot_and_stats_are_honest(setup):
    mind, _, _ = setup
    mind.attention.set_task("reviewing invoices")
    mind.perception.perceive("screen", "an unknown toolbar appeared")
    mind.attention.review()
    snap = mind.attention.snapshot()
    assert snap["current_task"] == "reviewing invoices"
    assert snap["last_focus"]["level"] in LADDER
    stats = mind.attention.stats()
    assert stats["verdicts"] >= 1 and stats["current_task"] == "reviewing invoices"
    assert stats["policy"].startswith("attention decides")
    # the Phase-3/4 state skeleton's attention room now lights up from the mind
    room = mind.state()["attention"]
    assert room["status"] == "ok"
    assert room["component"] == "Attention"


# ── the door: process() anchors the task + arbitrates; kill switch honored ──
def test_process_runs_attention_with_the_owner_message_as_anchor(setup):
    mind, _, _ = setup
    mind.perception.perceive("screen", "a save dialog appeared")
    mind.process("file the invoice away", modality="text")
    snap = mind.attention.snapshot()
    assert snap["current_task"] == "file the invoice away"
    assert mind.attention.stats()["verdicts"] >= 1


def test_kill_switch_disables_door_arbitration(setup):
    mind, _, monkeypatch = setup
    from app.config import settings
    monkeypatch.setattr(settings, "ARENA_ATTENTION", "0")
    mind.process("file the invoice away", modality="text")
    assert mind.attention.snapshot()["current_task"] == ""
    assert mind.attention.stats()["verdicts"] == 0


def test_observe_lane_carries_the_attention_verdict(setup):
    mind, _, _ = setup
    res = mind.observe("watchdog", {"summary": "backup finished overnight",
                                     "modality": "desktop"})
    assert res["perception"]["success"] is True
    assert res["attention"]["success"] is True
    assert res["attention"]["epistemic_kind"] == "attention_verdict"
    assert res["attention"]["acted"] is False


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_attention_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    task = client.post("/mind/attention/task",
                       json={"text": "editing the quarterly report"})
    assert task.status_code == 200 and task.json()["success"] is True

    mind.perception.perceive("screen", "popup over the quarterly report")
    review = client.post("/mind/attention/review")
    assert review.status_code == 200
    body = review.json()
    assert body["success"] is True and body["attended"] >= 1
    assert any("interfere" in a for a in body["advisories"])

    got = client.get("/mind/attention")
    assert got.status_code == 200
    payload = got.json()
    assert payload["success"] is True
    assert payload["snapshot"]["current_task"] == "editing the quarterly report"
    assert payload["by_level"] and payload["history"]
    assert payload["ladder"]["current_task"] == LADDER["current_task"]
