"""Regression-gated continual learning: plan → (owner trains) → evaluate.

Planning snapshots dataset readiness and a baseline benchmark; evaluation
re-runs the benchmark and applies a hard regression gate (any previously
passing check that now fails fails the cycle). Planning authorizes nothing;
a passing gate releases nothing automatically.
"""
import pytest

from app.cognition.continual_learning import (
    ContinualLearningCycle,
    ContinualLearningStore,
)


class FakeBench:
    """Configurable benchmark runner: dict-shaped runs."""

    def __init__(self, runs):
        self.runs = list(runs)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.runs.pop(0)


def run(passed=("a", "b", "c"), all_checks=("a", "b", "c", "d")):
    return {
        "passed_count": len(passed),
        "total_count": len(all_checks),
        "checks": [{"name": name, "passed": name in passed} for name in all_checks],
    }


def make_cycle(tmp_path, runs):
    store = ContinualLearningStore(tmp_path / "cl.db")
    return ContinualLearningCycle(store=store, benchmark_runner=FakeBench(runs)), store


def test_plan_records_dataset_and_baseline(tmp_path):
    cycle, store = make_cycle(tmp_path, [run(passed=("a", "b", "c"))])
    planned = cycle.plan_training(note="first cycle")
    assert planned["success"] is True
    assert "Plan only" in planned["note"]
    record = store.get(planned["cycle"]["cycle_id"])
    assert record.status == "planned"
    assert record.before_benchmark["passed_count"] == 3
    assert "min_approved_for_export" in record.dataset_summary


def test_evaluate_passes_when_nothing_regressed(tmp_path):
    cycle, store = make_cycle(tmp_path, [
        run(passed=("a", "b", "c")),
        run(passed=("a", "b", "c", "d")),  # gained d, lost nothing
    ])
    planned = cycle.plan_training()
    result = cycle.evaluate(planned["cycle"]["cycle_id"])
    assert result["success"] is True
    assert result["gate"]["verdict"] == "pass"
    assert result["gate"]["newly_passing_checks"] == ["d"]
    assert "releases nothing automatically" in result["note"]
    assert store.get(planned["cycle"]["cycle_id"]).status == "evaluated_pass"

    # Double evaluation is refused.
    assert cycle.evaluate(planned["cycle"]["cycle_id"])["success"] is False


def test_evaluate_fails_on_any_regression(tmp_path):
    cycle, store = make_cycle(tmp_path, [
        run(passed=("a", "b", "c")),
        run(passed=("a", "b", "d")),  # c regressed even though d gained
    ])
    planned = cycle.plan_training()
    result = cycle.evaluate(planned["cycle"]["cycle_id"])
    assert result["success"] is True
    assert result["gate"]["verdict"] == "fail"
    assert result["gate"]["regressed_checks"] == ["c"]
    assert "keep the previous model" in result["note"]
    assert store.get(planned["cycle"]["cycle_id"]).status == "evaluated_fail"


def test_evaluate_fails_on_shrinking_totals(tmp_path):
    cycle, _ = make_cycle(tmp_path, [
        run(passed=("a", "b", "c"), all_checks=("a", "b", "c", "d")),
        run(passed=("a", "b", "c"), all_checks=("a", "b", "c")),  # fewer checks than baseline
    ])
    planned = cycle.plan_training()
    result = cycle.evaluate(planned["cycle"]["cycle_id"])
    assert result["gate"]["verdict"] == "fail"


def test_cycle_without_baseline_refuses_evaluation(tmp_path):
    cycle, _ = make_cycle(tmp_path, [])
    planned = cycle.plan_training(run_baseline=False)
    assert planned["cycle"]["before_benchmark"] is None
    result = cycle.evaluate(planned["cycle"]["cycle_id"])
    assert result["success"] is False and "no baseline" in result["error"]


def test_benchmark_failure_is_honest(tmp_path):
    class Exploding:
        def __call__(self):
            raise RuntimeError("provider offline")

    store = ContinualLearningStore(tmp_path / "cl.db")
    cycle = ContinualLearningCycle(store=store, benchmark_runner=Exploding())
    planned = cycle.plan_training()
    assert planned["baseline_error"] is not None  # honest: baseline failed, cycle still planned
    result = cycle.evaluate(planned["cycle"]["cycle_id"])
    assert result["success"] is False  # honest failure either way
    assert "provider offline" in result.get("error", "") or "no baseline" in result.get("error", "")


def test_status_lists_recent_cycles(tmp_path):
    cycle, _ = make_cycle(tmp_path, [run(), run()])
    cycle.plan_training()
    status = cycle.status()
    assert status["success"] is True
    assert len(status["recent_cycles"]) == 1
    assert "dataset" in status
