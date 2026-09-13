"""Phase 8 — the honesty family inside the intelligence benchmark.

The owner's go-ahead (2026-09-11) made the scoreboard the next organ:
the live-round failure classes must be SCORED probes, so a regression
in any shipped guard shows up as a benchmark failure with a named
regression entry — not only inside a pytest file nobody reruns. These
tests pin the family itself: it exists, it is complete, it passes, and
its runs persist with trend support.
"""

import pytest

from app.cognition.intelligence_benchmark import (
    BenchmarkHistoryStore,
    IntelligenceBenchmarkSuite,
)

HONESTY_FAMILY = {
    # round 8: the fabricated completion claim with nothing executed
    "honesty_fabricated_claim_retracted",
    # round 7/8: unverified outcome surfaced, real actions named
    "honesty_unverified_outcome_surfaced",
    # the empty promise with nothing executed
    "honesty_promise_without_action_replaced",
    # round 7: googling the raw command hands the win to a real branch
    "derail_literal_command_search_blocked",
    # round 6/7: the typo extracts to the app, the pronoun to nothing
    "clarity_typo_extraction",
    # round 8: answers to our own questions complete the request
    "clarity_followup_resolution",
    # phase 1: one event id per request, typed verdicts, guard->failure
    "ledger_request_spine",
}


@pytest.fixture(scope="module")
def suite_run(tmp_path_factory):
    store = BenchmarkHistoryStore(
        tmp_path_factory.mktemp("bench") / "bench.db")
    run = IntelligenceBenchmarkSuite(history_store=store).run()
    return run, store


def test_honesty_family_is_present_and_complete(suite_run):
    run, _ = suite_run
    names = {c.name for c in run.checks if c.category == "honesty"}
    assert names == HONESTY_FAMILY


def test_honesty_family_all_passes(suite_run):
    run, _ = suite_run
    failed = [
        f"{c.name}: {c.evidence}"
        for c in run.checks
        if c.category == "honesty" and not c.passed
    ]
    assert failed == []


def test_full_suite_passes_with_the_family(suite_run):
    run, _ = suite_run
    assert run.passed_count == run.total_count
    assert run.regressions == []
    # measured this phase: 38 pre-existing checks + 7 honesty-family
    # probes = 45; the family extended the suite, replaced nothing
    assert run.total_count >= 45


def test_run_persists_for_trends(suite_run):
    run, store = suite_run
    latest = store.latest()
    assert latest is not None
    assert latest.run_id == run.run_id
    trend = store.trend()
    assert trend  # the scoreboard is a number over time, not a vibe
