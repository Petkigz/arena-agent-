"""
Scheduler wiring guards: the autonomous cycle can be scheduled as a recurring job,
and the job registry reflects it (and can be cleared).
"""

import pytest

from app.scheduler.scheduler import ProactiveScheduler


@pytest.fixture
def fresh_scheduler():
    """Reset the class-level scheduler so each test starts clean, then shut it down."""
    ProactiveScheduler._scheduler = None
    yield
    sched = ProactiveScheduler._scheduler
    if sched is not None:
        sched.shutdown(wait=False)
    ProactiveScheduler._scheduler = None


def test_schedule_recurring_registers_job(fresh_scheduler):
    calls = []
    ok = ProactiveScheduler.schedule_recurring("test_job", lambda: calls.append(1), interval_seconds=3600)
    assert ok is True

    jobs = ProactiveScheduler.list_jobs()
    ids = [j["id"] for j in jobs]
    assert "test_job" in ids


def test_schedule_recurring_replaces_existing_job(fresh_scheduler):
    ProactiveScheduler.schedule_recurring("job_x", lambda: None, interval_seconds=10)
    ProactiveScheduler.schedule_recurring("job_x", lambda: None, interval_seconds=20)

    jobs = ProactiveScheduler.list_jobs()
    ids = [j["id"] for j in jobs]
    assert ids.count("job_x") == 1  # no duplicate job


def test_remove_job(fresh_scheduler):
    ProactiveScheduler.schedule_recurring("job_y", lambda: None, interval_seconds=10)
    assert ProactiveScheduler.remove_job("job_y") is True

    jobs = ProactiveScheduler.list_jobs()
    ids = [j["id"] for j in jobs]
    assert "job_y" not in ids


def test_remove_missing_job_returns_false(fresh_scheduler):
    assert ProactiveScheduler.remove_job("does_not_exist") is False
