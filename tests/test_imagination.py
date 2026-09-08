"""Phase 10 (Beanie AGI roadmap) — reasoning and imagination.

PERCEIVE → MODEL → HYPOTHESIZE → SIMULATE → ACT → OBSERVE
→ COMPARE PREDICTION vs REALITY → LEARN.

Contracts pinned here:
- simulate BEFORE acting: prediction + her own verified history + open
  unknowns + deterministic counsel (no LLM);
- reality is EVIDENCE: compare() rejects non-bool outcomes;
- confirmed/refuted verdicts are persisted AND submitted to the Phase-6
  loop as experiments — failures become training data;
- the runtime owns the calibrator: imagination must NOT double-count
  calibration records for cycle outcomes;
- cycles with a definite verdict auto-compare; waiting-for-evidence never
  does; broken imagination never breaks the door.
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
        self.result = {"success": True, "assistant_reply": "ok"}

    def process_cognitive_cycle(self, user_text, **kwargs):
        return self.result


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain
    BeanieMind.reset_instance()


# ── SIMULATE: before acting, run it in her head ────────────────────────────
def test_simulate_labels_prediction_and_counsel(setup):
    mind, _ = setup
    rec = mind.imagination.simulate("open_application")
    assert rec["success"] is True
    assert rec["epistemic_kind"] == "simulation"
    pred = rec["prediction"]
    assert pred["epistemic_kind"] == "prediction"
    assert pred["expected_changes"] and isinstance(pred["confidence"], float)
    # no history yet → counsel says so honestly
    assert "no verified experience" in rec["counsel"]
    assert rec["prior_evidence"] == {"successes": 0, "failures": 0}
    assert mind.imagination.simulate("")["success"] is False


def test_simulate_considers_her_own_history(setup):
    mind, brain = setup
    brain.memory.add("episodic", "copied the files to the backup drive",
                     importance=0.6, source="cycle:text", success=True)
    brain.memory.add("episodic", "copied the files but the disk was full",
                     importance=0.6, source="cycle:text", success=False)
    rec = mind.imagination.simulate("copy_files")
    assert rec["prior_evidence"] == {"successes": 1, "failures": 1}
    assert "mixed history" in rec["counsel"]


def test_simulate_flags_unknown_territory(setup):
    mind, _ = setup
    mind.curiosity.register("backup drive")
    rec = mind.imagination.simulate("copy_files_to_backup_drive")
    assert rec["open_unknowns"] == ["backup drive"]


# ── COMPARE: reality is evidence, verdicts become training data ────────────
def test_reality_must_be_evidence(setup):
    mind, _ = setup
    bad = mind.imagination.compare("search_files", None)
    assert bad["success"] is False and "bool evidence" in bad["reason"]
    assert mind.imagination.compare("search_files", "yes")["success"] is False
    assert mind.imagination.records() == []


def test_confirmed_and_refuted_become_training_data(setup):
    mind, brain = setup
    ok = mind.imagination.compare("search_files", True, surprisal=0.1)
    assert ok["verdict"] == "confirmed" and ok["learned"] is True
    bad = mind.imagination.compare("copy_files", False, surprisal=0.9)
    assert bad["verdict"] == "refuted" and bad["learned"] is True

    # the ledger remembers both
    stats = mind.imagination.stats()
    assert stats["comparisons"] == 2
    assert stats["confirmed"] == 1 and stats["refuted"] == 1
    assert stats["mean_surprisal"] == 0.5
    assert "simulate" in stats["loop"] and "reality" in stats["epistemic_kinds"]

    # and the Phase-6 ledger carries them as experiments with verdicts
    exps = [e for e in mind.learning.events() if e["kind"] == "experiment"]
    assert len(exps) == 2
    assert {e["verdict"] for e in exps} == {"confirmed", "refuted"}

    # the failure landed as a verified-failure episode — mistakes are data
    failures = [r for r in brain.memory.search("copy files failed", limit=10)
                if r.kind == "episodic" and r.success is False]
    assert failures


def test_imagination_never_double_counts_calibration(setup):
    mind, brain = setup
    before = len(brain.confidence_calibrator._records)
    mind.imagination.compare("search_files", True)
    # the runtime owns calibrator feeds for cycle outcomes; the organ's
    # learn() submission withholds predicted_confidence on purpose
    assert len(brain.confidence_calibrator._records) == before


# ── the door: verified cycles auto-compare ─────────────────────────────────
def test_verified_cycles_compare_prediction_with_reality(setup):
    mind, brain = setup
    brain.result = {"success": True, "assistant_reply": "done",
                    "goal_verified": True, "goal_lifecycle_state": "achieved",
                    "action_type": "search_files", "prediction_surprisal": 0.2}
    mind.process("find the invoices", modality="text")
    records = mind.imagination.records()
    assert len(records) == 1
    assert records[0]["verdict"] == "confirmed"
    assert records[0]["success"] is True
    assert records[0]["surprisal"] == 0.2
    # both experiences in the learning ledger: the action AND the experiment
    kinds = [e["kind"] for e in mind.learning.events()]
    assert "action" in kinds and "experiment" in kinds


def test_unverified_and_waiting_cycles_never_compare(setup):
    mind, brain = setup
    brain.result = {"success": True, "action_type": "search_files",
                    "verification_unknown": True, "goal_verified": False}
    mind.process("find the invoices", modality="text")
    assert mind.imagination.records() == []

    brain.result = {"success": True, "assistant_reply": "ok"}  # no verdict
    mind.process("hello", modality="text")
    assert mind.imagination.records() == []


def test_failed_verification_becomes_refuted_training(setup):
    mind, brain = setup
    brain.result = {"success": False, "goal_verified": False,
                    "goal_lifecycle_state": "failed",
                    "action_type": "copy_files", "prediction_surprisal": 1.0}
    mind.process("copy everything", modality="text")
    rec = mind.imagination.records()[0]
    assert rec["verdict"] == "refuted" and rec["success"] is False
    exps = [e for e in mind.learning.events() if e["kind"] == "experiment"]
    assert exps and exps[0]["verdict"] == "refuted"


def test_broken_imagination_never_breaks_the_door(setup, monkeypatch):
    mind, brain = setup
    brain.result = {"success": True, "goal_verified": True,
                    "action_type": "search_files"}
    monkeypatch.setattr(mind.imagination, "compare",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = mind.process("still works", modality="text")
    assert result["goal_verified"] is True


def test_imagination_kill_switch(setup, monkeypatch):
    mind, brain = setup
    from app.config import settings
    monkeypatch.setattr(settings, "ARENA_IMAGINATION", "0")
    brain.result = {"success": True, "goal_verified": True,
                    "action_type": "search_files"}
    mind.process("no comparing this turn", modality="text")
    assert mind.imagination.records() == []
    # the owner surface still works
    assert mind.imagination.simulate("search_files")["success"] is True


# ── API contract ────────────────────────────────────────────────────────────
def test_imagination_api(setup):
    mind, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router
    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    body = client.post("/mind/imagination/simulate",
                       json={"action_type": "open_application"}).json()
    assert body["success"] is True and body["epistemic_kind"] == "simulation"

    body = client.post("/mind/imagination/compare",
                       json={"action_type": "open_application",
                             "success": False, "surprisal": 0.8}).json()
    assert body["verdict"] == "refuted" and body["learned"] is True

    body = client.get("/mind/imagination").json()
    assert body["comparisons"] == 1 and body["refuted"] == 1
    assert body["records"][0]["action_type"] == "open_application"

    # success is REQUIRED evidence in the schema
    assert client.post("/mind/imagination/compare",
                       json={"action_type": "x"}).status_code == 422
