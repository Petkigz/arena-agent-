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

    assert run.total_count == 36
    assert run.passed_count == run.total_count
    assert run.regressions == []
    assert {check.category for check in run.checks} >= {
        "memory", "learning", "adaptation", "control", "perception", "planning",
        "identity_adaptation", "calibration", "grounding", "phase1_evidence",
    }
    assert {check.name for check in run.checks} >= {
        "identity_adaptation_governance",
        "shutdown_cooperation_boundary",
        "confidence_calibration_history",
        "held_out_unknown_answer",
        "held_out_unsupported_claim_control",
        "held_out_deterministic_mismatch",
        "held_out_empty_observation",
        "held_out_outcome_guided_choice",
        "held_out_usefulness_guided_choice",
        "held_out_correction_measurement",
        "held_out_correction_non_generalization",
        "held_out_memory_compounding_baseline",
        "held_out_consolidation_improves_foreground",
        "held_out_pattern_transfer_advisory",
    }
    assert all(
        check.evaluation_scope == "held_out"
        for check in run.checks
        if check.name.startswith("held_out_")
    )
    by_name = {check.name: check for check in run.checks}
    assert by_name["held_out_unsupported_claim_control"].metrics["supported"] is False
    assert by_name["held_out_outcome_guided_choice"].metrics["observed_outcome_delta"] == 1
    assert by_name["held_out_usefulness_guided_choice"].metrics["adapted_strategy"] == "web_search"
    assert by_name["held_out_correction_measurement"].metrics["latency_ms"] == 125.0
    assert by_name["held_out_correction_non_generalization"].metrics["unrelated_context_after_repeat"] == 1.0
    assert by_name["held_out_memory_compounding_baseline"].metrics["baseline_relevant_hits"] == 0
    assert by_name["held_out_memory_compounding_baseline"].metrics["learned_relevant_hits"] >= 1
    assert by_name["held_out_memory_compounding_baseline"].metrics["idempotent_replay_records"] == 0
    assert by_name["held_out_consolidation_improves_foreground"].metrics["baseline_actionable_hits"] == 0
    assert by_name["held_out_consolidation_improves_foreground"].metrics["learned_actionable_hits"] >= 1
    assert by_name["held_out_consolidation_improves_foreground"].metrics["incubation_scope"] == "owner_enabled_not_simulated"
    assert by_name["held_out_pattern_transfer_advisory"].metrics["baseline_suggestions"] == 0
    assert by_name["held_out_pattern_transfer_advisory"].metrics["advisory_only"] is True
    assert by_name["phase1_evidence_aggregation"].metrics["usefulness_feedback_count"] == 2
    assert by_name["phase1_task_evaluation_recording"].metrics["paired_improved_count"] == 1
    assert all(check.duration_ms >= 0 for check in run.checks)

    restored = BenchmarkHistoryStore(tmp_path / "benchmarks.db").latest()
    assert restored is not None
    assert restored.run_id == run.run_id
    assert restored.passed_count == 36


def test_history_detects_pass_to_fail_regression(tmp_path, monkeypatch):
    history = BenchmarkHistoryStore(tmp_path / "benchmarks.db")
    baseline = IntelligenceBenchmarkSuite(history).run()
    assert baseline.passed_count == baseline.total_count

    original = IntelligenceBenchmarkSuite._run_check

    def fail_one(name, category, function, *, evaluation_scope="contract"):
        if name == "memory_paraphrase_retrieval":
            return BenchmarkCheck(
                name=name,
                category=category,
                passed=False,
                evidence="injected regression",
                    metrics={},
                    duration_ms=0.0,
                    evaluation_scope=evaluation_scope,
                )
        return original(name, category, function, evaluation_scope=evaluation_scope)

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


def test_trend_requires_repeated_runs_and_reports_observed_changes_only(tmp_path):
    history = BenchmarkHistoryStore(tmp_path / "benchmarks.db")
    suite = IntelligenceBenchmarkSuite(history)

    assert history.trend()["status"] == "insufficient_evidence"
    suite.run()
    assert history.trend()["status"] == "insufficient_evidence"
    suite.run()

    trend = history.trend()
    assert trend["status"] == "measured"
    assert trend["run_count"] == 2
    assert trend["checks"]["identity_adaptation_governance"]["observed_change"] == "stable"
    assert trend["checks"]["held_out_unknown_answer"]["evaluation_scope"] == "held_out"
    assert "agi_score" not in trend
    assert "causal" in trend["note"].lower()


def test_trend_endpoint_exposes_persisted_observations(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.cognition.runtime import CognitiveRuntime
    from app.main import intelligence_benchmark_trend_endpoint

    history = BenchmarkHistoryStore(tmp_path / "benchmarks.db")
    suite = IntelligenceBenchmarkSuite(history)
    suite.run()
    suite.run()
    runtime = SimpleNamespace(
        intelligence_benchmarks=SimpleNamespace(history_store=history),
    )
    monkeypatch.setattr(
        CognitiveRuntime,
        "get_instance",
        classmethod(lambda cls: runtime),
    )

    result = intelligence_benchmark_trend_endpoint(limit=2)
    assert result["success"] is True
    assert result["trend"]["status"] == "measured"
