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
