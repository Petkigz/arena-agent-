"""Post-roadmap growth (audit #25) — the devil's advocate.

"Is there a dedicated subroutine that actively tries to disprove its own
favorite conclusions? True intelligence doubts itself." Contracts pinned
here:
- counter-evidence comes ONLY from her own ledgers (verified failures,
  wrong reflections, refuted predictions, open gaps, admitted unknowns)
  — never invented;
- no overlapping counter-evidence → the conclusion SURVIVES, reported
  exactly as the absence of a counter-case — never proof;
- the evidence gate is real: unrelated history manufactures no doubt;
- the door runs the advocate on VERIFIED SUCCESSES (survivorship bias);
- scrutiny describes — acted is always False; it never vetoes.
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


# ── surviving is honest, never proof ────────────────────────────────────────
def test_clean_record_survives_with_an_honest_statement(setup):
    mind, _, _ = setup
    res = mind.scrutiny.scrutinize("the nightly sync will work")
    assert res["success"] is True and res["acted"] is False
    assert res["epistemic_kind"] == "scrutiny"
    assert res["survived"] is True and res["counter_evidence"] == []
    assert res["confidence_after"] == "uncontested"
    assert "never proof" in res["statement"]
    assert mind.scrutiny.doubts() == [], "survival is not a doubt"


def test_unrelated_history_manufactures_no_doubt(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "bake a chocolate cake",
                "source": "cycle:text", "success": False})
    res = mind.scrutiny.scrutinize("the nightly sync will work")
    assert res["survived"] is True and res["counter_evidence"] == []


# ── each counter-evidence family contests ───────────────────────────────────
def test_verified_failure_contests(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    res = mind.scrutiny.scrutinize("the nightly sync will work")
    assert res["survived"] is False and res["confidence_after"] == "contested"
    kinds = {c["kind"] for c in res["counter_evidence"]}
    assert "verified_failure" in kinds
    assert mind.scrutiny.doubts(), "contested conclusions enter the doubt ledger"


def test_wrong_reflection_contests(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "the export job",
                "source": "cycle:text", "success": False})
    mind.reflection.reflect_on({"kind": "action", "content": "the export job",
                                "success": False})
    res = mind.scrutiny.scrutinize("the export job succeeds")
    kinds = {c["kind"] for c in res["counter_evidence"]}
    assert res["survived"] is False and "was_wrong_before" in kinds


def test_refuted_prediction_contests(setup):
    mind, _, _ = setup
    mind.imagination.compare("delete_file", False, source="test")
    res = mind.scrutiny.scrutinize("delete_file will be fine")
    kinds = {c["kind"] for c in res["counter_evidence"]}
    assert res["survived"] is False and "refuted_prediction" in kinds


def test_open_gap_contests(setup):
    mind, _, _ = setup
    for _ in range(2):
        mind.learn({"kind": "action", "content": "the nightly sync",
                    "source": "cycle:text", "success": False})
    res = mind.scrutiny.scrutinize("the nightly sync will work")
    kinds = {c["kind"] for c in res["counter_evidence"]}
    assert res["survived"] is False and "open_gap" in kinds


def test_admitted_unknown_contests(setup):
    mind, _, _ = setup
    mind.curiosity.register("why does the nightly sync stall",
                            source="encounter")
    res = mind.scrutiny.scrutinize("the nightly sync will work")
    kinds = {c["kind"] for c in res["counter_evidence"]}
    assert res["survived"] is False and "admitted_unknown" in kinds


def test_empty_conclusion_is_refused(setup):
    mind, _, _ = setup
    res = mind.scrutiny.scrutinize("   ")
    assert res["success"] is False and "nothing to scrutinize" in res["reason"]


# ── the door: success is when survivorship bias bites ───────────────────────
class _VerifyingBrain(_Brain):
    def __init__(self, tmp_path, verified):
        super().__init__(tmp_path)
        self._verified = verified

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok",
                "goal_verified": self._verified,
                "goal_lifecycle_state": "completed"}


def test_door_scrutinizes_verified_success_with_contrary_history(
        tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    mind.process("the nightly sync", modality="text")
    doubts = mind.scrutiny.doubts()
    assert len(doubts) == 1, "success against contrary history is doubted"
    assert doubts[0]["source"] == "door"
    BeanieMind.reset_instance()


def test_door_records_clean_success_as_survived(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    mind.process("file the invoices", modality="text")
    assert mind.scrutiny.doubts() == []
    assert mind.scrutiny.scrutinies()[0]["survived"] is True
    BeanieMind.reset_instance()


def test_door_skips_verified_failures_and_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    from app.config import settings
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, False))
    mind.process("the nightly sync", modality="text")
    assert mind.scrutiny.scrutinies() == [], \
        "failures are already doubted by the verifier"
    monkeypatch.setattr(settings, "ARENA_SCRUTINY", "0")
    mind2_runtime = _VerifyingBrain(tmp_path, True)
    mind._runtime = mind2_runtime
    mind.process("file the invoices", modality="text")
    assert mind.scrutiny.scrutinies() == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_snapshot(setup):
    mind, _, _ = setup
    mind.scrutiny.scrutinize("a clean conclusion")
    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    mind.scrutiny.scrutinize("the nightly sync will work")
    stats = mind.scrutiny.stats()
    assert stats["scrutinies"] == 2
    assert stats["doubts"] == 1 and stats["survived"] == 1
    assert "never proof" in stats["policy"]
    snap = mind.scrutiny.snapshot()
    assert snap["organ"] == "scrutiny" and len(snap["doubts"]) == 1


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_scrutiny_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    mind.learn({"kind": "action", "content": "the nightly sync",
                "source": "cycle:text", "success": False})
    post = client.post("/mind/scrutiny/scrutinize",
                       json={"conclusion": "the nightly sync will work"})
    assert post.status_code == 200
    body = post.json()
    assert body["survived"] is False and body["acted"] is False
    assert body["confidence_after"] == "contested"

    page = client.get("/mind/scrutiny")
    payload = page.json()
    assert payload["success"] is True
    assert payload["doubts"] == 1 and len(payload["doubt_list"]) == 1
    assert payload["scrutinies"] == 1 and len(payload["stream"]) == 1
