"""Shared test diagnostics."""

from __future__ import annotations

import os


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
