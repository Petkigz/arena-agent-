"""Shared test diagnostics."""

from __future__ import annotations

import os


def pytest_runtest_logreport(report):
    """Expose CI failure details as check annotations when log blobs are unavailable."""
    if not os.getenv("GITHUB_ACTIONS") or report.when != "call" or not report.failed:
        return
    message = str(report.longrepr).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    node = report.nodeid.split("::", 1)[0]
    print(f"::error file={node},title=pytest failure::{message[:7000]}")
