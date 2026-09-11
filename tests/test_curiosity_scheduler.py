"""Phase 7 — information-gain-based continuous cognition (owner plan 2026-09-10).

Pins the owner's exit criteria:
  * no re-running vague, stale, or superseded questions;
  * no investigation merely because something is unknown;
  * expected information gain is explainable;
  * the owner can pause, inspect, approve, reject, or delete every
    autonomous question;
  * probes are read-only by construction; the seven-question contract is
    enforced at admission; kill switch + fail-open.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.cognition.curiosity import (
    MAX_OPEN_QUESTIONS,
    CuriosityQuestion,
    CuriosityScheduler,
    default_ttl_expiry,
)
from app.cognition.world_model import Observation, WorldModel
from uuid import uuid4


@pytest.fixture
def world(tmp_path):
    return WorldModel(db_path=str(tmp_path / "world.sqlite3"))


@pytest.fixture
def scheduler(tmp_path):
    return CuriosityScheduler(db_path=str(tmp_path / "cur.sqlite3"))


def _valid_question(**over):
    q = CuriosityQuestion(
        subject="RichST TV", predicate="process_state",
        uncertainty="is RichST TV actually running right now?",
        rationale="an active goal depends on the process state",
        resolving_evidence="one fresh psutil process scan",
        cost_risk="none — read-only, milliseconds",
        read_only=True, decision_impact="goal 'open RichST TV' acts on this",
        expires_at=default_ttl_expiry(), probe_kind="process_state",
        information_gain=0.9, source="test",
    )
    for k, v in over.items():
        setattr(q, k, v)
    return q


# ── generation: real signals only, never mere unknownness ────────────────


class TestGeneration:
    def test_contradiction_generates_a_full_contract_question(self, world, scheduler):
        world.observe(Observation(id=uuid4().hex, subject="RichST TV",
                                  predicate="process_state", value="running",
                                  source="psutil_scan"))
        world.observe(Observation(id=uuid4().hex, subject="RichST TV",
                                  predicate="process_state", value="not_running",
                                  source="execution_receipt"))
        qs = scheduler.generate_candidates(world)
        assert qs, "a sourced contradiction must generate a question"
        q = qs[0]
        assert q.missing_contract_fields() == []
        assert q.information_gain >= 0.7
        assert "conflict" in q.gain_explanation.lower()
        assert q.read_only is True

    def test_staleness_alone_generates_nothing(self, world, scheduler):
        # Exit criterion: it does not investigate merely because a task is
        # unknown. An old fact with no dependent decision is not a reason.
        old = (Observation(id=uuid4().hex, subject="SomeApp", predicate="process_state",
                           value="running", source="psutil_scan"))
        from datetime import datetime, timezone
        old.observed_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        world.observe(old)
        assert scheduler.generate_candidates(world) == []

    def test_staleness_with_dependent_goal_generates(self, world, scheduler):
        from datetime import datetime, timezone
        old = Observation(id=uuid4().hex, subject="RichST TV", predicate="process_state",
                          value="running", source="psutil_scan")
        old.observed_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        world.observe(old)
        qs = scheduler.generate_candidates(world, active_goals=["open RichST TV for me"])
        assert len(qs) == 1
        assert "open RichST TV" in qs[0].decision_impact
        assert qs[0].probe_kind == "process_state"


# ── the seven-question admission gate ─────────────────────────────────────


class TestAdmission:
    def test_incomplete_contract_is_rejected(self, scheduler):
        q = _valid_question(decision_impact="")
        v = scheduler.admit(q)
        assert v["admitted"] is False
        assert "decision_impact" in v["reason"]

    def test_non_read_only_is_refused(self, scheduler):
        v = scheduler.admit(_valid_question(read_only=False))
        assert v["admitted"] is False
        assert "read-only" in v["reason"]

    def test_no_whitelisted_probe_is_refused(self, scheduler):
        v = scheduler.admit(_valid_question(probe_kind="launch_app"))
        assert v["admitted"] is False
        assert "no read-only probe" in v["reason"]

    def test_expired_question_is_refused(self, scheduler):
        v = scheduler.admit(_valid_question(expires_at="2020-01-01T00:00:00+00:00"))
        assert v["admitted"] is False
        assert "expired" in v["reason"]

    def test_low_gain_is_refused(self, scheduler):
        v = scheduler.admit(_valid_question(information_gain=0.1))
        assert v["admitted"] is False
        assert "resolves no decision" in v["reason"]

    def test_valid_question_is_admitted_and_inspectable(self, scheduler):
        v = scheduler.admit(_valid_question())
        assert v["admitted"] is True
        listed = scheduler.inspect(status="open")
        assert [q["id"] for q in listed] == [v["question_id"]]
        assert listed[0]["read_only"] is True

    def test_open_cap_bounds_the_engine(self, scheduler):
        for i in range(MAX_OPEN_QUESTIONS):
            assert scheduler.admit(_valid_question(subject=f"App{i}"))["admitted"]
        v = scheduler.admit(_valid_question(subject="OneTooMany"))
        assert v["admitted"] is False
        assert "cap" in v["reason"]


# ── no re-running vague, stale, or superseded ─────────────────────────────


class TestNoReRuns:
    def test_duplicate_of_open_question_is_superseded(self, scheduler):
        assert scheduler.admit(_valid_question())["admitted"]
        v = scheduler.admit(_valid_question())
        assert v["admitted"] is False
        assert "superseded" in v["reason"]

    def test_answered_question_is_not_re_asked(self, scheduler, world, monkeypatch):
        v = scheduler.admit(_valid_question())
        monkeypatch.setattr(
            "app.tools.app_inventory.SystemAppInventory.verify_app_running",
            classmethod(lambda cls, q, e="", **k: {"process_verified": True, "pid": 9}))
        assert scheduler.run_probe(v["question_id"], world=world)["success"]
        again = scheduler.admit(_valid_question())
        assert again["admitted"] is False
        assert "answered" in again["reason"]

    def test_expiry_frees_the_fact_for_a_new_question(self, scheduler):
        q1 = _valid_question()
        assert scheduler.admit(q1)["admitted"]
        assert scheduler.expire_due(now="2999-01-01T00:00:00+00:00") == 1
        assert scheduler.admit(_valid_question())["admitted"]


# ── probes: read-only, honest, whitelisted ────────────────────────────────


class TestProbes:
    def test_process_probe_answers_with_evidence_and_teaches_world(
            self, scheduler, world, monkeypatch):
        v = scheduler.admit(_valid_question())
        monkeypatch.setattr(
            "app.tools.app_inventory.SystemAppInventory.verify_app_running",
            classmethod(lambda cls, q, e="", **k: {
                "process_verified": True, "pid": 4242, "process_name": "RichSTTV.exe"}))
        res = scheduler.run_probe(v["question_id"], world=world)
        assert res["success"] is True
        assert res["answer"]["value"] == "running"
        assert res["answer"]["evidence"]["pid"] == 4242
        # the answer became a provenance-tracked world observation
        obs = world.latest_observation("RichST TV", "process_state")
        assert obs.source == "curiosity_probe"
        assert scheduler.inspect(status="answered")[0]["answer"]["value"] == "running"

    def test_probe_failure_never_fakes_an_answer(self, scheduler, world, monkeypatch):
        v = scheduler.admit(_valid_question())
        def boom(*a, **k):
            raise RuntimeError("psutil exploded")
        monkeypatch.setattr(
            "app.tools.app_inventory.SystemAppInventory.verify_app_running",
            classmethod(boom))
        res = scheduler.run_probe(v["question_id"], world=world)
        assert res["success"] is False
        assert "honestly" in res["reason"]
        assert scheduler.inspect(status="answered") == []

    def test_expired_question_cannot_probe(self, scheduler):
        q = _valid_question()
        v = scheduler.admit(q)
        scheduler.expire_due(now="2999-01-01T00:00:00+00:00")
        res = scheduler.run_probe(v["question_id"])
        assert res["success"] is False
        assert "expired" in res["reason"]


# ── owner controls ────────────────────────────────────────────────────────


class TestOwnerControls:
    def test_pause_blocks_admission(self, scheduler):
        scheduler.pause()
        assert scheduler.is_paused() is True
        v = scheduler.admit(_valid_question())
        assert v["admitted"] is False and "paused" in v["reason"]
        scheduler.resume()
        assert scheduler.admit(_valid_question())["admitted"]

    def test_decide_approve_reject_delete(self, scheduler):
        ids = [scheduler.admit(_valid_question(subject=f"A{i}"))["question_id"]
               for i in range(3)]
        assert scheduler.decide(ids[0], "approve")["status"] == "approved"
        assert scheduler.decide(ids[1], "reject")["status"] == "rejected"
        assert scheduler.decide(ids[2], "delete")["status"] == "deleted"
        assert scheduler.decide("nope", "approve")["success"] is False
        assert scheduler.decide(ids[0], "maybe")["success"] is False

    def test_inspect_filters_by_status(self, scheduler):
        v = scheduler.admit(_valid_question())
        scheduler.decide(v["question_id"], "approve")
        assert scheduler.inspect(status="open") == []
        assert len(scheduler.inspect(status="approved")) == 1

    def test_kill_switch_silences_everything(self, scheduler, world, monkeypatch):
        monkeypatch.setattr("app.config.settings.ARENA_CURIOSITY", "0")
        assert scheduler.generate_candidates(world) == []
        v = scheduler.admit(_valid_question())
        assert v["admitted"] is False and "disabled" in v["reason"]


# ── API endpoints (owner surface) ─────────────────────────────────────────


class TestOwnerAPI:
    @pytest.fixture(autouse=True)
    def _tmp_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.config.settings.DB_PATH",
                            str(tmp_path / "owner.sqlite3"))

    def test_list_and_summary_and_pause(self):
        from app.api.owner_control_autonomy import (
            CuriosityPauseRequest,
            curiosity_summary_endpoint,
            list_curiosity_questions_endpoint,
            pause_curiosity_endpoint,
        )
        # explicit args mirror what FastAPI injects at runtime
        out = list_curiosity_questions_endpoint(None, 100)
        assert out["success"] is True and out["questions"] == []
        pause_curiosity_endpoint(CuriosityPauseRequest(paused=True))
        summary = curiosity_summary_endpoint()
        assert summary["paused"] is True and summary["enabled"] is True
        pause_curiosity_endpoint(CuriosityPauseRequest(paused=False))
        assert curiosity_summary_endpoint()["paused"] is False

    def test_decision_endpoint_validates(self):
        from app.api.owner_control_autonomy import (
            CuriosityDecisionRequest,
            decide_curiosity_question_endpoint,
        )
        with pytest.raises(HTTPException) as e:
            decide_curiosity_question_endpoint("missing-id",
                                               CuriosityDecisionRequest(decision="approve"))
        assert e.value.status_code == 404
        with pytest.raises(HTTPException) as e:
            decide_curiosity_question_endpoint("any",
                                               CuriosityDecisionRequest(decision="maybe"))
        assert e.value.status_code == 400

    def test_probe_endpoint_reports_honest_failure(self):
        from app.api.owner_control_autonomy import run_curiosity_probe_endpoint
        with pytest.raises(HTTPException) as e:
            run_curiosity_probe_endpoint("missing-id")
        assert e.value.status_code == 404


# ── wiring ────────────────────────────────────────────────────────────────


def test_wiring_is_in_place():
    import inspect

    import app.api.owner_control_autonomy as api
    import app.cognition.periodic_autonomous_cycle as pac

    cycle_src = inspect.getsource(pac)
    assert "CuriosityScheduler" in cycle_src
    assert "curiosity_sweep" in cycle_src
    api_src = inspect.getsource(api)
    assert "curiosity-questions" in api_src
    assert "curiosity-pause" in api_src
    from app.config import settings
    assert hasattr(settings, "ARENA_CURIOSITY")
