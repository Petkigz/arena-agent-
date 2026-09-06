"""Phase 0 runner contracts: isolated checks and regression history."""

from app.cognition.phase0_evaluation import Phase0EvaluationHistoryStore, Phase0EvaluationSuite


def test_phase0_suite_runs_isolated_checks_and_persists_history(tmp_path):
    history = Phase0EvaluationHistoryStore(tmp_path / "phase0.db")
    run = Phase0EvaluationSuite(history).run()

    assert run.total_count == 7
    assert run.passed_count == run.total_count, [
        (check.name, check.evidence) for check in run.checks if not check.passed
    ]
    assert run.regressions == []
    restored = history.latest()
    assert restored is not None
    assert restored.run_id == run.run_id
    assert restored.total_count == 7


def test_phase0_history_roundtrips_check_status_for_regression_comparison(tmp_path):
    from app.cognition.phase0_evaluation import Phase0Check, Phase0Run

    history = Phase0EvaluationHistoryStore(tmp_path / "phase0.db")
    previous = Phase0Run(
        run_id="previous",
        created_at="2026-01-01T00:00:00+00:00",
        checks=[Phase0Check("contract", "epistemic", True, "ok")],
        passed_count=1,
        total_count=1,
        regressions=[],
    )
    history.save(previous)
    # The runner's own current checks remain the source of truth; this test
    # ensures the persisted schema retains regression-capable check data.
    restored = history.latest()
    assert restored.checks[0].name == "contract"
    assert restored.checks[0].passed is True
