"""Phase 20 (Beanie AGI roadmap) — self-improvement.

"Detect capability gaps → investigate → design improvement → implement →
test → measure → retain/revert." Contracts pinned here:
- gaps come ONLY from evidence — 2+ verified failures of the same thing;
  a single failure is data, not a gap;
- designs never execute; implementation runs the WIRED synthesis engine
  and claims only its typed word (offline/unverified = honest failure);
- measurement needs NEW verified evidence — success with no new failures
  retains; 2+ new failures reverts FOR REAL (registry entry popped);
  anything less is awaiting, never guessed;
- the door detects + proposes after a verified failure completes the
  pattern; it NEVER implements.
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


def _fail_twice(mind, content="the nightly sync"):
    for _ in range(2):
        mind.learn({"kind": "action", "content": content,
                    "source": "cycle:text", "success": False})


# ── detection is evidence, never narration ──────────────────────────────────
def test_no_gaps_on_empty_mind(setup):
    mind, _, _ = setup
    assert mind.improvement.detect_gaps() == []


def test_single_failure_is_not_a_gap(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    assert mind.improvement.detect_gaps() == []


def test_repeated_verified_failure_is_a_gap(setup):
    mind, _, _ = setup
    _fail_twice(mind)
    mind.curiosity.register("why does this keep failing: the nightly sync",
                            source="reflection", context="verified failure ×2")
    gaps = mind.improvement.detect_gaps()
    assert len(gaps) == 1
    assert gaps[0]["verified_failures"] == 2
    assert gaps[0]["source"] == "verified_failures"
    assert gaps[0]["unknown"] is not None, "the P19 unknown corroborates"


# ── investigation reports the record, nothing more ─────────────────────────
def test_investigate_bundle(setup):
    mind, _, _ = setup
    _fail_twice(mind)
    ev = mind.improvement.investigate("the nightly sync")
    assert ev["success"] is True
    assert ev["failure_count"] == 2 and ev["success_count"] == 0
    assert "2 verified failure" in ev["finding"]


def test_investigate_nothing_is_honest(setup):
    mind, _, _ = setup
    ev = mind.improvement.investigate("something never tried")
    assert ev["success"] is False and "no evidence" in ev["reason"]


# ── design records a proposal; never executes ───────────────────────────────
def test_design_records_a_proposal(setup):
    mind, _, _ = setup
    _fail_twice(mind)
    proposal = mind.improvement.design({"content": "the nightly sync",
                                        "verified_failures": 2})
    assert proposal["success"] is True and proposal["acted"] is False
    assert proposal["epistemic_kind"] == "improvement_proposal"
    assert proposal["mechanism"] == "capability_synthesis"
    assert proposal["baseline_fails"] == 2
    rows = mind.improvement.improvements()
    assert rows and rows[0]["status"] == "proposed" and rows[0]["acted"] is False


def test_design_single_failure_refused(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    res = mind.improvement.design({"content": "the nightly sync",
                                   "verified_failures": 1})
    assert res["success"] is False and "not a pattern" in res["reason"]


def test_design_duplicate_refused(setup):
    mind, _, _ = setup
    _fail_twice(mind)
    first = mind.improvement.design({"content": "the nightly sync",
                                     "verified_failures": 2})
    assert first["success"] is True
    second = mind.improvement.design({"content": "the nightly sync",
                                      "verified_failures": 2})
    assert second["success"] is False and "already has an improvement" in second["reason"]


# ── implementation claims only the mechanism's word ─────────────────────────
def _patch_engine(monkeypatch, result):
    from app.agents import self_evolving_agent as sea
    monkeypatch.setattr(sea.SelfEvolvingAgent, "synthesize_and_hotload_tool",
                        classmethod(lambda cls, task_objective,
                                    tool_name_query: result))


def test_implement_success_claims_only_the_engines_word(setup, monkeypatch):
    mind, _, _ = setup
    _fail_twice(mind)
    pid = mind.improvement.design({"content": "the nightly sync",
                                   "verified_failures": 2})["improvement_id"]
    _patch_engine(monkeypatch, {"success": True, "verified": True,
                                "installed": True, "attempts": 1,
                                "capability_name": "imp_nightly_sync"})
    res = mind.improvement.implement(pid)
    assert res["success"] is True and res["installed"] is True
    assert res["acted"] is True and res["status"] == "attempted"
    assert "verified AND installed" in res["statement"]


def test_implement_unverified_is_an_honest_failure(setup, monkeypatch):
    mind, _, _ = setup
    _fail_twice(mind)
    pid = mind.improvement.design({"content": "the nightly sync",
                                   "verified_failures": 2})["improvement_id"]
    _patch_engine(monkeypatch, {"success": False, "verified": False,
                                "installed": False, "attempts": 3,
                                "last_failure": "sandbox rejected the code"})
    res = mind.improvement.implement(pid)
    assert res["installed"] is False and res["acted"] is False
    assert res["status"] == "failed"
    assert "sandbox rejected the code" in res["statement"]
    assert mind.improvement.improvements()[0]["status"] == "failed"


def test_implement_exception_fails_open(setup, monkeypatch):
    mind, _, _ = setup
    _fail_twice(mind)
    pid = mind.improvement.design({"content": "the nightly sync",
                                   "verified_failures": 2})["improvement_id"]
    from app.agents import self_evolving_agent as sea
    monkeypatch.setattr(sea.SelfEvolvingAgent, "synthesize_and_hotload_tool",
                        classmethod(lambda cls, **kw: (_ for _ in ()).throw(
                            RuntimeError("engine down"))))
    res = mind.improvement.implement(pid)
    assert res["installed"] is False and res["status"] == "failed"
    assert "engine down" in res["statement"]


# ── measurement is later evidence against the baseline ──────────────────────
def _attempted(mind, monkeypatch):
    _fail_twice(mind)
    pid = mind.improvement.design({"content": "the nightly sync",
                                   "verified_failures": 2})["improvement_id"]
    _patch_engine(monkeypatch, {"success": True, "verified": True,
                                "installed": True, "attempts": 1})
    mind.improvement.implement(pid)
    return pid


def test_measure_improved_retains(setup, monkeypatch):
    mind, _, _ = setup
    pid = _attempted(mind, monkeypatch)
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": True})
    res = mind.improvement.measure(pid)
    assert res["status"] == "retained" and res["acted"] is False
    assert res["measurement"]["new_successes"] == 1
    assert mind.improvement.improvements()[0]["status"] == "retained"


def test_measure_regression_reverts_for_real(setup, monkeypatch):
    mind, _, _ = setup
    pid = _attempted(mind, monkeypatch)
    # the engine would have registered the capability live:
    from app.cognition.tool_registry import get_shared_registry
    registry = get_shared_registry()
    registry.register_tool("imp_nightly_sync", "plugin",
                           lambda payload: {"success": True},
                           description="test", safety_level=2,
                           provenance="dynamic")
    assert "imp_nightly_sync" in registry._registry
    for _ in range(2):
        mind.learn({"kind": "action", "content": "the nightly sync",
                    "source": "cycle:text", "success": False})
    res = mind.improvement.measure(pid)
    assert res["status"] == "reverted" and res["acted"] is True
    assert res["measurement"]["verdict"] == "regressed"
    assert res["measurement"]["revert"]["unregistered"] is True
    assert "imp_nightly_sync" not in registry._registry, \
        "revert must pop the live registry entry"


def test_measure_without_new_evidence_awaits(setup, monkeypatch):
    mind, _, _ = setup
    pid = _attempted(mind, monkeypatch)
    res = mind.improvement.measure(pid)
    assert res["status"] == "awaiting_evidence" and res["acted"] is False
    assert "never guessed" in res["statement"]


def test_measure_before_attempt_is_refused(setup):
    mind, _, _ = setup
    _fail_twice(mind)
    pid = mind.improvement.design({"content": "the nightly sync",
                                   "verified_failures": 2})["improvement_id"]
    res = mind.improvement.measure(pid)
    assert res["success"] is False and "nothing was attempted" in res["reason"]


# ── the door: detect + propose, never implement ─────────────────────────────
class _FailBrain(_Brain):
    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": False, "assistant_reply": "failed",
                "goal_verified": False, "goal_lifecycle_state": "failed"}


def test_door_proposes_when_the_pattern_completes(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_FailBrain(tmp_path))
    mind.process("the nightly sync", modality="text")
    assert mind.improvement.improvements() == [], \
        "one failure is data — no proposal yet"
    mind.process("the nightly sync", modality="text")
    rows = mind.improvement.improvements()
    assert len(rows) == 1 and rows[0]["status"] == "proposed"
    assert rows[0]["acted"] is False, "the door never implements"
    BeanieMind.reset_instance()


def test_kill_switch_stops_the_improvement_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    from app.config import settings
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_IMPROVEMENT", "0")
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_FailBrain(tmp_path))
    mind.process("the nightly sync", modality="text")
    mind.process("the nightly sync", modality="text")
    assert mind.improvement.improvements() == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_snapshot(setup):
    mind, _, _ = setup
    _fail_twice(mind)
    mind.improvement.design({"content": "the nightly sync",
                             "verified_failures": 2})
    stats = mind.improvement.stats()
    assert stats["improvements"] == 1
    assert stats["by_status"]["proposed"] == 1
    assert stats["gaps_detected"] == 1
    snap = mind.improvement.snapshot()
    assert snap["organ"] == "improvement" and snap["gaps"]


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_improvement_contract(setup, monkeypatch):
    mind, _, _ = setup
    _fail_twice(mind)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    page = client.get("/mind/improvement")
    assert page.status_code == 200
    assert page.json()["gaps_detected"] == 1

    prop = client.post("/mind/improvement/propose",
                       json={"content": "the nightly sync"})
    assert prop.status_code == 200
    body = prop.json()
    assert body["success"] is True and body["status"] == "proposed"
    pid = body["improvement_id"]

    _patch_engine(monkeypatch, {"success": True, "verified": True,
                                "installed": True, "attempts": 1})
    impl = client.post("/mind/improvement/implement",
                       json={"improvement_id": pid})
    assert impl.json()["installed"] is True

    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": True})
    meas = client.post("/mind/improvement/measure",
                       json={"improvement_id": pid})
    assert meas.json()["status"] == "retained"

    stream = client.get("/mind/improvement").json()
    assert stream["improvements"] == 1 and len(stream["stream"]) == 1
