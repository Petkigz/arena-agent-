"""Shared test diagnostics."""

from __future__ import annotations

import os

import pytest


def pytest_terminal_summary(terminalreporter):
    """Expose CI failure details as check annotations when log blobs are unavailable."""
    if not os.getenv("GITHUB_ACTIONS"):
        return
    for report in terminalreporter.stats.get("failed", []):
        message = str(report.longrepr).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        node = report.nodeid.split("::", 1)[0]
        terminalreporter.write_line(
            f"::error file={node},title=pytest failure::{message[:7000]}"
        )


# ── Hermeticity guard (owner run 2026-09-02) ─────────────────────────────
# The suite's baseline is the OFFLINE deterministic layer (what CI and the
# sandbox can run). The owner's machine has LM Studio up by default, and
# the 2026-09-02 full run showed ~20 tests flipping on live-LLM variance
# (interpreter conditions, embedding backend, 'provider unavailable'
# error shapes) — 2.5 hours of noise, not regressions. This guard makes
# every provider call behave exactly as if the server were unreachable,
# so the suite is deterministic on ANY machine. Tests that exercise the
# REAL transport internals (test_llm*.py, test_inference_profile.py)
# remove the variable locally.
os.environ.setdefault("ARENA_LLM_DISABLED", "1")

# ── Background-life hermeticity (owner live-test slice, 2026-09-08) ──────
# The resurrection slice gives the server real background life: scheduled
# parked-goal re-checks, dashboard auto-open, the desktop screen watcher,
# and the decision-trace file. Left on during tests they reach into
# unrelated test state (a re-check runs a full cognitive cycle mid-test;
# the trace file lands in the repo). CI's fresh DB made this visible.
# The features themselves stay ON for the owner (config defaults "1").
os.environ.setdefault("ARENA_PARKED_RECHECK", "0")
os.environ.setdefault("ARENA_AUTO_OPEN_DASHBOARD", "0")
os.environ.setdefault("ARENA_DECISION_TRACE", "0")
os.environ.setdefault("ARENA_SCREEN_WATCHER", "0")
# NOTE: ARENA_ANNOUNCEMENT_GUARD is deliberately NOT disabled here. The
# line used to exist, but the settings loader's LPA_ prefix silently
# ignored the bare name, so the guard was effectively ON for the whole
# test history — and its own contract tests (hollow promises must be
# replaced) require it ON. Since bare names now really load (config
# naming fix, audit 2026-09-09: app/config.py::_BareNameEnvSource),
# re-adding it would flip long-verified suite behavior. The guard is a
# reply rewriter, not a background side-effect feature like the four
# above.


@pytest.fixture(autouse=True)
def _reset_interpreter_domain_cache():
    """Isolation guard (found via the control-envelope batch, 2026-09-05):
    SemanticGoalInterpreter caches manifest-derived domain vocabulary in
    CLASS attributes (_manifest_domains_cache / the synced VALID_DOMAINS).
    Tests that monkeypatch get_tool_manifest with a single-tool fake and
    run a full cycle poison that cache for every later test in the
    process (domain 'code' silently downgraded to 'unknown' — the exact
    class of order-dependent failure that hides until two files run in
    the right sequence). Reset after every test: one manifest pass to
    rebuild is nothing compared to a poisoned vocabulary."""
    yield
    try:
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        SemanticGoalInterpreter._manifest_domains_cache = None
        SemanticGoalInterpreter.VALID_DOMAINS = set(SemanticGoalInterpreter.LEGACY_DOMAINS)
    except Exception:
        pass
