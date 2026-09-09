"""Phase 24 (Beanie AGI roadmap) — AGI evaluation.

"Stop measuring primarily 'How many tests pass?' Measure
GENERALIZATION." Contracts pinned here:
- seven task families (A–G), each a DETERMINISTIC proxy against the
  REAL organs — never an LLM jury, never a staged pass;
- A: adaptation scores on real term evidence between the taught
  procedure and the variation;
- B: steps performed come from what was actually LEARNED (ledger
  recovery), never hidden knowledge;
- C: an unfamiliar error becomes a registered UNKNOWN — investigation
  starts with honest ignorance;
- D: an environment change advances the registry revision and drops
  stale availability — re-probe, never dead facts;
- E: an incomplete instruction keeps correctness UNKNOWN — never
  fabricated completion;
- F: a verified failure is called WRONG with counsel — failure becomes
  material;
- G: transfer resolves on the target body or flags VISIBLE gaps, never
  fabricated capabilities;
- the overall number is labeled a proxy, never proof.
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


# ── the run: seven families, honest aggregate ───────────────────────────────
def test_run_all_scores_seven_families(setup):
    mind, _, _ = setup
    profile = mind.evaluation.run_all()
    assert profile["success"] is True and profile["acted"] is False
    assert profile["epistemic_kind"] == "agi_evaluation"
    tasks = profile["tasks"]
    assert [t["task"] for t in tasks] == ["A", "B", "C", "D", "E", "F", "G"]
    for t in tasks:
        assert 0.0 <= t["score"] <= 1.0 and t["verdict"], t["task"]
    assert profile["overall"] == round(
        sum(t["score"] for t in tasks) / 7, 3)
    assert "proxies, never as proof" in profile["policy"]


# ── A: teach once, adapt to a variation ─────────────────────────────────────
def test_task_a_adapts_on_real_term_evidence(setup):
    mind, _, _ = setup
    res = mind.evaluation.task_a_teach_then_variation(
        "open the settings app and search for display brightness",
        "open settings and search for the display brightness")
    assert res["score"] >= 0.5 and "adapts" in res["verdict"]
    weak = mind.evaluation.task_a_teach_then_variation(
        "open the settings app", "bake a chocolate cake slowly")
    assert weak["score"] < 0.3 and "not demonstrated" in weak["verdict"]


# ── B: tutorial without a hard-coded workflow ───────────────────────────────
def test_task_b_recovers_steps_from_the_ledger(setup):
    mind, _, _ = setup
    tutorial = ("How to export a report:\n1. open the reports app\n"
                "2. choose the monthly summary\n3. press export")
    res = mind.evaluation.task_b_tutorial(tutorial)
    assert res["evidence"]["expected_steps"] == 3
    assert res["evidence"]["recovered_steps"] == 3
    assert res["evidence"]["from_ledger"] is True
    assert "no hard-coded workflow" in res["verdict"]


# ── C: unfamiliar error → registered unknown ────────────────────────────────
def test_task_c_registers_the_unknown(setup):
    mind, _, _ = setup
    res = mind.evaluation.task_c_unfamiliar_error(
        "WeirdFault: splines reticulating backwards")
    assert res["score"] == 1.0 and res["evidence"]["registered_unknown"]
    assert any("unfamiliar error" in str(u["topic"])
               for u in mind.curiosity.curiosities(limit=20))
    assert "honest ignorance" in res["verdict"]


# ── D: environment change → re-probe, never dead facts ──────────────────────
def test_task_d_environment_change_advances_revision(setup):
    mind, _, _ = setup
    from app.cognition.tool_registry import get_shared_registry
    before = get_shared_registry().environment_revision
    res = mind.evaluation.task_d_environment_change("open_application")
    assert res["score"] == 1.0
    assert res["evidence"]["environment_revision"][0] == before
    assert res["evidence"]["environment_revision"][1] > before
    assert "dead" in res["verdict"]


# ── E: incomplete instruction → UNKNOWN, never fabricated ───────────────────
def test_task_e_keeps_correctness_unknown(setup):
    mind, _, _ = setup
    res = mind.evaluation.task_e_incomplete_instruction("back it up")
    assert res["score"] == 1.0
    assert res["evidence"]["verdict"] is None
    assert "fabricating" in res["verdict"]


# ── F: fail → learn from the failure ────────────────────────────────────────
def test_task_f_failure_becomes_material(setup):
    mind, _, _ = setup
    res = mind.evaluation.task_f_learn_from_failure("the nightly export")
    assert res["score"] == 1.0
    assert res["evidence"]["verdict"] == "wrong"
    assert res["evidence"]["counsel"]
    assert "material" in res["verdict"]


# ── G: teach on one body, transfer the concept ──────────────────────────────
def test_task_g_empty_manifest_shows_visible_gaps(setup):
    mind, _, _ = setup
    res = mind.evaluation.task_g_transfer(["open the browser",
                                           "copy the link"])
    assert res["evidence"]["resolved"] == 0
    assert res["evidence"]["gaps"] == 2
    assert "VISIBLE" in res["verdict"], "gaps are shown, never fabricated"


def test_task_g_transfers_when_the_target_body_has_the_concept(setup):
    mind, _, _ = setup
    manifest = {
        "open_app_android": {"name": "open app android",
                             "description": "open or launch an application on android",
                             "category": "android"},
        "copy_clip_android": {"name": "copy android",
                              "description": "copy text to the android clipboard",
                              "category": "android"},
    }
    mind.os_concepts._manifest = lambda: manifest
    res = mind.evaluation.task_g_transfer(["open the browser",
                                           "copy the link"],
                                          to_platform="android")
    assert res["score"] == 1.0
    assert res["evidence"]["resolved"] == 2 and res["evidence"]["gaps"] == 0
    assert res["evidence"]["generalized"] is True
    assert "generalized to the other body" in res["verdict"]


# ── ledger + surfaces ───────────────────────────────────────────────────────
def test_runs_are_recorded(setup):
    mind, _, _ = setup
    mind.evaluation.run_all()
    mind.evaluation.run_all()
    runs = mind.evaluation.runs()
    assert len(runs) == 2 and all("tasks" in r["profile"] for r in runs)
    stats = mind.evaluation.stats()
    assert stats["runs"] == 2 and stats["latest_overall"] is not None
    assert "never proof" in stats["policy"] or "proxies" in stats["policy"]
    snap = mind.evaluation.snapshot()
    assert snap["organ"] == "evaluation"


# ── owner surface + kill switch ─────────────────────────────────────────────
def test_api_evaluation_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    run = client.post("/mind/evaluation/run")
    assert run.status_code == 200
    body = run.json()
    assert body["success"] is True and len(body["tasks"]) == 7

    page = client.get("/mind/evaluation")
    payload = page.json()
    assert payload["success"] is True and payload["runs"] == 1
    assert len(payload["stream"]) == 1
    assert payload["latest_overall"] == body["overall"]


def test_kill_switch_disables_the_surface(setup, monkeypatch):
    mind, _, _ = setup
    from app.config import settings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)
    monkeypatch.setattr(settings, "ARENA_EVALUATION", "0")
    run = client.post("/mind/evaluation/run")
    assert run.json()["success"] is False
    assert "ARENA_EVALUATION" in run.json()["reason"]
