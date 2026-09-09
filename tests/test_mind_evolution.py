"""Phase 21 (Beanie AGI roadmap) — model evolution.

"Fast learning: memory/world-model updates. Medium-term: skill/concept
consolidation. Long-term: dataset creation + evaluation + optional
adapter training. That prevents catastrophic forgetting and unnecessary
retraining." Contracts pinned here:
- the fast lane is ALREADY live at the door — evolution REPORTS its real
  wiring, never duplicates or fakes it;
- the medium lane delegates to the wired consolidation engine and claims
  only its telemetry; consolidation APPENDS — raw learning events are
  never deleted (the forgetting guard);
- the long lane exports ONLY verified ledger material (never padded),
  and sufficiency is arithmetic (volume floor + both outcome classes),
  never optimism;
- the adapter lane reports readiness — training runs on the owner's
  machine, and the organ never claims a trained model;
- the door consolidates when enough new learning accumulates.
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


def _verified_material(mind, n_success=3, n_failure=3):
    for i in range(n_success):
        mind.learn({"kind": "action", "content": f"task success {i}",
                    "source": "cycle:text", "success": True})
    for i in range(n_failure):
        mind.learn({"kind": "action", "content": f"task failure {i}",
                    "source": "cycle:text", "success": False})


# ── fast lane: report the live wiring, never fake it ────────────────────────
def test_fast_state_reports_real_wiring(setup):
    mind, _, _ = setup
    _verified_material(mind, 2, 1)
    fast = mind.evolution.fast_state()
    assert fast["lane"] == "fast"
    assert fast["learning_events"] == 3
    assert isinstance(fast["stored_memories"], int)
    for key in ("memory_counts", "world", "self_model"):
        assert key in fast, f"fast lane must report the {key} organ"


# ── medium lane: the engine's word, append-only ─────────────────────────────
def test_consolidate_claims_only_the_engine_telemetry(setup):
    mind, _, _ = setup
    _verified_material(mind)
    res = mind.evolution.consolidate(max_tasks=10)
    assert res["success"] is True and res["acted"] is True
    assert res["lane"] == "medium"
    summary = res["summary"]
    assert summary["status"] in ("completed", "completed_with_errors")
    assert "conflicts_replayed" in summary and "gists_created" in summary
    assert summary["events_total"] == 6
    runs = mind.evolution.consolidations()
    assert runs and runs[0]["lane"] == "medium"


def test_consolidation_never_deletes_raw_experience(setup):
    mind, _, _ = setup
    _verified_material(mind)
    before = len(mind.learning.events(limit=100))
    mind.evolution.consolidate(max_tasks=10)
    assert len(mind.learning.events(limit=100)) == before, \
        "consolidation appends — raw experience is the forgetting guard"


def test_consolidate_without_memory_store_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()

    class _NoMemory(_Brain):
        def __init__(self, p):
            super().__init__(p)
            self.memory = None

    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_NoMemory(tmp_path))
    res = mind.evolution.consolidate()
    assert res["success"] is False and res["acted"] is False
    assert "no memory store" in res["reason"]
    BeanieMind.reset_instance()


# ── long lane: dataset from her own verified ledger ─────────────────────────
def test_dataset_exports_verified_material_only(setup):
    mind, _, _ = setup
    _verified_material(mind, 4, 2)
    mind.learn({"kind": "observation", "content": "an unverified note",
                "source": "perception"})  # no success verdict
    ds = mind.evolution.dataset()
    assert ds["success"] is True and ds["acted"] is True
    assert ds["rows"] == 6, "unverified material never enters the dataset"
    assert ds["by_success"] == {"true": 4, "false": 2}
    assert ds["path"] and ds["sha256"]
    with open(ds["path"], encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln]
    assert len(lines) == 6
    assert all('"provenance": "beanie_learning_events"' in ln for ln in lines)


def test_dataset_empty_mind_exports_nothing(setup):
    mind, _, _ = setup
    ds = mind.evolution.dataset()
    assert ds["rows"] == 0 and ds["path"] is None and ds["acted"] is False
    assert "never" in ds["statement"]


def test_evaluate_is_arithmetic_never_optimism(setup):
    mind, _, _ = setup
    _verified_material(mind, 3, 3)  # 6 rows < 20 floor
    verdict = mind.evolution.evaluate_dataset()
    assert verdict["sufficient"] is False and verdict["acted"] is False
    assert verdict["rows"] == 6
    assert any("20" in g for g in verdict["gaps"])
    # sufficiency with an explicit adequate, balanced sample
    rows = ([{"success": True}] * 12) + ([{"success": False}] * 12)
    ok = mind.evolution.evaluate_dataset(rows)
    assert ok["sufficient"] is True and ok["gaps"] == []
    # volume ok but one-sided = still insufficient
    one_sided = [{"success": True}] * 30
    bad = mind.evolution.evaluate_dataset(one_sided)
    assert bad["sufficient"] is False
    assert any("failures" in g for g in bad["gaps"])


def test_adapter_status_reports_readiness_never_training(setup):
    mind, _, _ = setup
    status = mind.evolution.adapter_status()
    assert status["acted"] is False
    assert "lora_manager_available" in status
    assert status["training_script_present"] is True
    assert "owner's GPU machine" in status["policy"]


# ── threshold bookkeeping + the door ────────────────────────────────────────
def test_needs_consolidation_threshold(setup, monkeypatch):
    mind, _, _ = setup
    monkeypatch.setattr("app.mind.evolution.CONSOLIDATION_THRESHOLD", 3)
    _verified_material(mind, 2, 0)
    assert mind.evolution.needs_consolidation()["needed"] is False
    mind.learn({"kind": "action", "content": "one more verified thing",
                "source": "cycle:text", "success": True})
    need = mind.evolution.needs_consolidation()
    assert need["needed"] is True and need["since_last_consolidation"] == 3
    mind.evolution.consolidate(max_tasks=5)
    after = mind.evolution.needs_consolidation()
    assert after["needed"] is False, \
        "a run records the ledger size it covered"


class _VerifyingBrain(_Brain):
    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok",
                "goal_verified": True, "goal_lifecycle_state": "completed"}


def test_door_consolidates_when_the_threshold_is_reached(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    monkeypatch.setattr("app.mind.evolution.CONSOLIDATION_THRESHOLD", 2)
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path))
    mind.process("first verified cycle", modality="text")
    assert mind.evolution.consolidations() == [], "below threshold: no run"
    mind.process("second verified cycle", modality="text")
    runs = mind.evolution.consolidations()
    assert len(runs) == 1, "the door consolidates once the threshold is met"
    assert runs[0]["acted"] is True
    BeanieMind.reset_instance()


def test_kill_switch_stops_the_evolution_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    monkeypatch.setattr("app.mind.evolution.CONSOLIDATION_THRESHOLD", 1)
    from app.config import settings
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_EVOLUTION", "0")
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path))
    mind.process("a verified cycle", modality="text")
    assert mind.evolution.consolidations() == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_snapshot(setup):
    mind, _, _ = setup
    _verified_material(mind)
    mind.evolution.consolidate(max_tasks=5)
    mind.evolution.dataset()
    stats = mind.evolution.stats()
    assert stats["consolidations"] == 1
    assert stats["by_lane"].get("medium") == 1
    assert stats["by_lane"].get("long") >= 1
    snap = mind.evolution.snapshot()
    assert snap["organ"] == "evolution" and snap["fast"]["lane"] == "fast"


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_evolution_contract(setup):
    mind, _, _ = setup
    _verified_material(mind)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    page = client.get("/mind/evolution")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True and payload["fast"]["lane"] == "fast"

    cons = client.post("/mind/evolution/consolidate", json={"max_tasks": 5})
    assert cons.status_code == 200
    assert cons.json()["summary"]["status"] in ("completed",
                                                "completed_with_errors")

    ds = client.post("/mind/evolution/dataset", json={"limit": 100})
    assert ds.json()["rows"] == 6

    ev = client.post("/mind/evolution/evaluate")
    assert ev.status_code == 200
    body = ev.json()
    assert body["sufficient"] is False and body["acted"] is False
