"""Persistent isolated intelligence benchmark and regression history."""

from app.cognition.intelligence_benchmark import (
    BenchmarkCheck,
    BenchmarkHistoryStore,
    IntelligenceBenchmarkSuite,
)


def test_benchmark_runs_isolated_behavioral_checks_and_persists(tmp_path):
    history = BenchmarkHistoryStore(tmp_path / "benchmarks.db")
    suite = IntelligenceBenchmarkSuite(history)

    run = suite.run()

    assert run.total_count == 14
    assert run.passed_count == run.total_count
    assert run.regressions == []
    assert {check.category for check in run.checks} >= {
        "memory", "learning", "adaptation", "control", "perception", "planning"
    }
    assert all(check.duration_ms >= 0 for check in run.checks)

    restored = BenchmarkHistoryStore(tmp_path / "benchmarks.db").latest()
    assert restored is not None
    assert restored.run_id == run.run_id
    assert restored.passed_count == 14


def test_history_detects_pass_to_fail_regression(tmp_path, monkeypatch):
    history = BenchmarkHistoryStore(tmp_path / "benchmarks.db")
    baseline = IntelligenceBenchmarkSuite(history).run()
    assert baseline.passed_count == baseline.total_count

    original = IntelligenceBenchmarkSuite._run_check

    def fail_one(name, category, function):
        if name == "memory_paraphrase_retrieval":
            return BenchmarkCheck(
                name=name,
                category=category,
                passed=False,
                evidence="injected regression",
                metrics={},
                duration_ms=0.0,
            )
        return original(name, category, function)

    monkeypatch.setattr(IntelligenceBenchmarkSuite, "_run_check", staticmethod(fail_one))
    regressed = IntelligenceBenchmarkSuite(history).run()

    assert regressed.passed_count == regressed.total_count - 1
    assert regressed.regressions == ["memory_paraphrase_retrieval"]
    assert len(history.history()) == 2


def test_history_does_not_call_pass_count_an_agi_percentage(tmp_path):
    history = BenchmarkHistoryStore(tmp_path / "benchmarks.db")
    run = IntelligenceBenchmarkSuite(history).run()
    report = run.to_dict()

    assert "percentage" not in report
    assert "agi_score" not in report
    assert report["environment"] == "isolated_deterministic"
    assert report["passed_count"] <= report["total_count"]
