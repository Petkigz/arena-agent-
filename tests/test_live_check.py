"""Live-check runner tests — the aggregation logic (pure), with injected probes.

The real probes hit the network, so here we only test run_live_checks' report
aggregation, exception safety, and skip handling.
"""

from scripts.live_check import run_live_checks


def test_run_live_checks_aggregates():
    probes = [
        ("a", lambda: {"status": "pass", "detail": "ok"}),
        ("b", lambda: {"status": "fail", "detail": "boom"}),
        ("c", lambda: {"status": "skip", "detail": "no creds"}),
    ]
    report = run_live_checks(probes)
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["skipped"] == 1
    assert len(report["checks"]) == 3


def test_run_live_checks_catches_exceptions():
    def boom():
        raise RuntimeError("network down")

    report = run_live_checks([("x", boom)])
    assert report["failed"] == 1
    assert report["checks"][0]["status"] == "fail"
    assert "raised" in report["checks"][0]["detail"]


def test_run_live_checks_rejects_bad_result():
    def weird():
        return "not a dict"

    report = run_live_checks([("x", weird)])
    assert report["failed"] == 1
    assert report["checks"][0]["status"] == "fail"


def test_run_live_checks_empty():
    report = run_live_checks([])
    assert report == {"checks": [], "passed": 0, "failed": 0, "skipped": 0}
