"""The gated self-improvement loop (owner go-ahead 2026-09-13).

The contract these tests pin: the CHOOSER ranks weaknesses from
evidence only; every experiment is an append-only Phase 1 ledger event;
measurement is the first gate (no-improvement variants die before they
waste owner attention); and the OWNER GATE is the only path from
measured improvement to accepted — approving twice is impossible,
because terminal states refuse everything.
"""

import pytest

from app.cognition import event_ledger as ledger
from app.cognition.intelligence_benchmark import (
    BenchmarkCheck,
    BenchmarkHistoryStore,
    BenchmarkRun,
)
from app.mind import self_improvement_gate as gate


def _check(name, category, passed):
    return BenchmarkCheck(name=name, category=category, passed=passed,
                          evidence="", metrics={}, duration_ms=1.0,
                          evaluation_scope="contract")


def _run(checks, regressions=()):
    return BenchmarkRun(
        run_id="bench_test", created_at="2026-09-13T00:00:00+00:00",
        checks=checks, passed_count=sum(1 for c in checks if c.passed),
        total_count=len(checks), regressions=list(regressions))


@pytest.fixture
def gate_db(monkeypatch, tmp_path):
    import app.database as database_module
    from app import settings_store

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "gate.db"))
    database_module.db._init_db()
    monkeypatch.setattr(ledger, "_backfill_done", True)
    monkeypatch.setattr(
        settings_store, "_SETTINGS_PATH", tmp_path / "settings.json")
    return database_module.db


@pytest.fixture
def scored_store(tmp_path):
    store = BenchmarkHistoryStore(tmp_path / "bench.db")
    store.save(_run([
        _check("honesty_fabricated_claim_retracted", "honesty", True),
        _check("memory_retrieval", "memory", False),
    ], regressions=["memory_retrieval"]))
    return store


class TestChooser:
    def test_regressions_rank_first_with_evidence(self, gate_db, scored_store):
        targets = gate.rank_improvement_targets(history_store=scored_store)
        assert targets, "scoreboard evidence must produce targets"
        top = targets[0]
        assert top["kind"] == "regression"
        assert any("memory_retrieval" in e for e in top["evidence"])

    def test_failing_checks_and_weak_family_are_listed(self, gate_db,
                                                       scored_store):
        kinds = {t["kind"]
                 for t in gate.rank_improvement_targets(
                     history_store=scored_store)}
        assert "benchmark_failure" in kinds
        assert "weak_family" in kinds

    def test_ledger_failure_clusters_are_evidence(self, gate_db):
        ledger.open_event("desktop-chat", "open it itunes on my pc")
        ledger.mark_from_cycle_result(
            "desktop-chat", "open it itunes on my pc",
            {"goal_lifecycle_state": "", "goal_verified": True,
             "announcement_guard": "fabricated_claim_replaced"})
        clusters = gate.failure_clusters()
        assert clusters and clusters[0]["count"] == 1
        empty_store = BenchmarkHistoryStore(gate_db.db_path + ".bench.db")
        targets = gate.rank_improvement_targets(history_store=empty_store)
        assert any(t["kind"] == "ledger_failure_cluster" for t in targets)

    def test_the_chooser_never_proposes_fixes(self, gate_db, scored_store):
        for t in gate.rank_improvement_targets(history_store=scored_store):
            assert set(t) == {"target", "kind", "weight", "evidence"}


class TestExperimentSpine:
    def test_measured_improvement_waits_for_the_owner(self, gate_db):
        eid = gate.record_experiment(
            "tighten the launch matcher", "ngram fallback on miss",
            baseline_score=41, variant_score=44)
        assert eid
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_OBSERVATION_PENDING
        assert any(r["kind"] == "measurement" for r in ev["receipts"])
        assert gate.pending_experiments()[0]["event_id"] == eid

    def test_no_improvement_dies_at_measurement(self, gate_db):
        eid = gate.record_experiment(
            "loosen the guard", "lower threshold", 44, 44)
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_VERIFIED_FAILURE
        assert "no measured improvement" in ev["reason"]
        assert gate.pending_experiments() == []

    def test_regression_is_rejected_despite_a_higher_score(self, gate_db):
        eid = gate.record_experiment(
            "reweight utility", "web_search boost", 41, 45,
            regressions=["derail_literal_command_search_blocked"])
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_VERIFIED_FAILURE
        assert "derail_literal_command_search_blocked" in ev["reason"]

    def test_same_hypothesis_rebinds_to_one_event(self, gate_db):
        e1 = gate.record_experiment("h", "v1", 40, 41)
        e2 = gate.record_experiment("h", "v2", 40, 41)
        assert e1 == e2  # one event id per experiment


class TestOwnerGate:
    def test_approval_is_the_only_path_to_success(self, gate_db):
        eid = gate.record_experiment("h", "v", 40, 41)
        assert gate.approve_experiment(eid) is True
        assert ledger.get_event(eid)["state"] == ledger.STATE_VERIFIED_SUCCESS
        # terminal: a second decision is refused
        assert gate.approve_experiment(eid) is False
        assert gate.reject_experiment(eid) is False

    def test_rejection_is_recorded(self, gate_db):
        eid = gate.record_experiment("h", "v", 40, 41)
        assert gate.reject_experiment(eid, "not worth the risk") is True
        ev = ledger.get_event(eid)
        assert ev["state"] == ledger.STATE_VERIFIED_FAILURE
        assert "owner" in ev["reason"]

    def test_measurement_rejects_cannot_be_approved_later(self, gate_db):
        eid = gate.record_experiment("h", "v", 41, 40)
        assert gate.approve_experiment(eid) is False


class TestTrainingReadiness:
    def test_insufficient_data_is_said_plainly(self, gate_db):
        report = gate.training_readiness()
        assert report["available"] is True
        assert report["data_ready"] is False
        assert "insufficient" in report["verdict"]
        # the recorded hardware constraint is stated, not hidden
        assert "VRAM" in report.get("hardware_note", "")

    def test_evidence_counts_accumulate(self, gate_db):
        ledger.open_event("desktop-chat", "task one")
        ledger.mark_from_cycle_result(
            "desktop-chat", "task one",
            {"goal_lifecycle_state": "achieved", "goal_verified": True})
        report = gate.training_readiness()
        assert report["verified_success"] >= 1


class TestBoundaries:
    def test_kill_switch_silences_everything(self, gate_db, monkeypatch,
                                             scored_store):
        monkeypatch.setenv("ARENA_SELF_IMPROVEMENT", "0")
        assert gate.rank_improvement_targets(history_store=scored_store) == []
        assert gate.record_experiment("h", "v", 0, 1) is None
        assert gate.approve_experiment("evt_any") is False
        assert gate.training_readiness()["available"] is False

    def test_missing_tables_fail_open(self, gate_db):
        assert gate.failure_clusters() == []
        assert gate.pending_experiments() == []


def test_wiring_is_in_place():
    import inspect

    import app.api.mind as mind_api
    src = inspect.getsource(mind_api)
    assert "/mind/self-improvement/targets" in src
    assert "/mind/self-improvement/experiments/approve" in src
    assert "/mind/self-improvement/training-readiness" in src
    from app.config import settings
    assert hasattr(settings, "ARENA_SELF_IMPROVEMENT")
