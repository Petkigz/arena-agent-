"""Multi-hour restart and preemption durability (accelerated time, real state).

These tests prove the SEMANTICS of long-running operation without wall-clock
waiting: hours and days are simulated by explicit `now` arguments and persisted
timestamp manipulation, and process restarts are simulated by constructing
fresh store instances over the same SQLite files. No sleeps; CI-realistic
runtime; real persistence and recovery code paths throughout.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.cognition.autonomous_goal_executor import (
    AutonomousGoalExecutor,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionStep,
    TaskType,
)
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator
from app.cognition.autonomy_lease import AutonomyCycleLease
from app.cognition.autonomy_preemption import AutonomyPreemptionStore
from app.cognition.autonomy_schedule import AutonomySchedule
from app.cognition.execution_control import ExecutionControlRegistry
from app.cognition.plan_step_reconciliation import PlanStepReconciliationStore

KAMPALA = ZoneInfo("Africa/Kampala")


def rewind(db_path, table, updates, where):
    with sqlite3.connect(db_path) as conn:
        for column, value in updates:
            conn.execute(f"UPDATE {table} SET {column}=? WHERE {where}", (value,))
        conn.commit()


# ── cycle lease across simulated crashes and long cycles ────────────────────

def test_stale_lease_from_crashed_cycle_is_recovered_after_hours(tmp_path):
    db = tmp_path / "lease.db"
    crashed = AutonomyCycleLease(db)
    held = crashed.acquire()  # process "crashes" immediately after, no release
    assert held["acquired"] is True
    # Simulate 3 hours passing: the persisted expiry is now in the past.
    past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    rewind(db, "autonomy_leases", [("expires_at", past)], "lease_name='periodic_cycle'")
    restarted = AutonomyCycleLease(db)  # a fresh process
    takeover = restarted.acquire()
    assert takeover["acquired"] is True  # stale claim recovered, cycle may proceed
    # The dead holder can no longer heartbeat or release the lease it lost.
    assert crashed.heartbeat(held["holder"]) is False
    assert crashed.release(held["holder"]) is False


def test_lease_age_alone_never_releases_an_active_long_cycle(tmp_path):
    db = tmp_path / "lease.db"
    holder_a = AutonomyCycleLease(db).acquire()
    # A 5-hour-old lease that is still inside its TTL (heartbeated far ahead)
    # must keep blocking a second process — age is not the criterion, expiry is.
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    old_acquired = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    rewind(db, "autonomy_leases",
           [("expires_at", future), ("acquired_at", old_acquired)],
           "lease_name='periodic_cycle'")
    second = AutonomyCycleLease(db).acquire()
    assert second["acquired"] is False and "lease" in second["reason"].lower()
    assert holder_a["acquired"] is True


def test_heartbeat_extends_multi_hour_cycle_until_ttl_expiry(tmp_path):
    import app.cognition.autonomy_lease as lease_module
    clock = {"t": datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)}

    def fake_now():
        return clock["t"]

    db = tmp_path / "lease.db"
    with patch.object(lease_module, "_now", side_effect=fake_now):
        first = AutonomyCycleLease(db)
        held = first.acquire(ttl_seconds=900)
        assert held["acquired"] is True

        for minute in range(1, 8):  # a long cycle heartbeats every ~10 minutes
            clock["t"] += timedelta(minutes=10)
            assert first.heartbeat(held["holder"], ttl_seconds=900) is True
            clock["t"] += timedelta(seconds=30)
            challenger = AutonomyCycleLease(db).acquire()
            assert challenger["acquired"] is False  # still single-owner at t+70min

        # The holder crashes; 20 minutes past the last heartbeat the lease dies.
        clock["t"] += timedelta(minutes=20)
        restarted = AutonomyCycleLease(db).acquire()
        assert restarted["acquired"] is True
        assert first.heartbeat(held["holder"]) is False


# ── schedules across a simulated week of days ───────────────────────────────

def test_daily_recurrence_runs_exactly_once_per_day_for_a_week(tmp_path):
    schedule = AutonomySchedule(tmp_path / "s.db")
    goals = AutonomousGoalGenerator(str(tmp_path / "g.db"))
    # 09:00 Kampala (06:00 UTC), starting Aug 18 — release windows for 7 days.
    schedule.create("Daily report", "2026-08-18T09:00:00",
                    recurrence="daily", timezone_name="Africa/Kampala")
    released_per_day = []
    for day in range(7):
        now = datetime(2026, 8, 18 + day, 6, 30, tzinfo=timezone.utc)
        first = schedule.release_due(goals, now)
        duplicate = schedule.release_due(goals, now)  # same instant re-poll
        released_per_day.append(len(first["released_goals"]))
        assert duplicate["released_goals"] == []  # deterministic occurrence ids
        current = schedule.list(status="active")[0]
        assert datetime.fromisoformat(current.next_run_at) > now
    assert released_per_day == [1] * 7
    assert goals.count_goals() == 7  # exactly one goal per day, no duplicates
    # Local wall time stayed 09:00 Kampala across the whole simulated week.
    for item in schedule.list():
        if item.status == "active":
            assert datetime.fromisoformat(item.next_run_at).astimezone(KAMPALA).hour == 9


def test_weekly_recurrence_advances_exactly_seven_days(tmp_path):
    schedule = AutonomySchedule(tmp_path / "s.db")
    goals = AutonomousGoalGenerator(str(tmp_path / "g.db"))
    schedule.create("Weekly review", "2026-08-17T09:00:00",
                    recurrence="weekly", timezone_name="Africa/Kampala")
    first = schedule.release_due(goals, datetime(2026, 8, 17, 6, 30, tzinfo=timezone.utc))
    assert len(first["released_goals"]) == 1
    item = schedule.list(status="active")[0]
    next_due = datetime.fromisoformat(item.next_run_at)
    assert next_due == datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)  # +7 days
    # Six days later nothing fires; on day 7 exactly one goal releases.
    midweek = schedule.release_due(goals, datetime(2026, 8, 20, 6, 30, tzinfo=timezone.utc))
    assert midweek["released_goals"] == []
    due_week = schedule.release_due(goals, datetime(2026, 8, 24, 6, 30, tzinfo=timezone.utc))
    assert len(due_week["released_goals"]) == 1
    assert goals.count_goals() == 2


def test_multi_hour_downtime_skip_and_single_catch_up(tmp_path):
    schedule = AutonomySchedule(tmp_path / "s.db")
    goals = AutonomousGoalGenerator(str(tmp_path / "g.db"))
    ten_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    skip_once = schedule.create("Skip stale one-time", ten_hours_ago, missed_policy="skip")
    skip_daily = schedule.create("Skip stale daily", ten_hours_ago, recurrence="daily", missed_policy="skip")
    catcher = schedule.create("Catch up once", ten_hours_ago, recurrence="daily",
                              missed_policy="run_once")
    result = schedule.release_due(goals)  # host was "down" for 10 hours
    assert skip_once.schedule_id in result["skipped_schedule_ids"]
    assert skip_daily.schedule_id in result["skipped_schedule_ids"]
    assert len(result["released_goals"]) == 1  # run_once released exactly once
    assert goals.count_goals() == 1
    statuses = {x.schedule_id: x.status for x in schedule.list()}
    # A skipped one-time directive is terminal; a skipped recurring directive
    # stays scheduled for its next future occurrence.
    assert statuses[skip_once.schedule_id] == "completed"
    assert statuses[skip_daily.schedule_id] == "active"
    again = schedule.release_due(goals)
    assert again["released_goals"] == []  # no second catch-up release


# ── restart durability: executions, preemptions, reconciliation, resume ─────

def test_execution_registry_restart_marks_interrupted_and_keeps_results(tmp_path):
    db = str(tmp_path / "exec.db")
    live = ExecutionControlRegistry(db)
    running = live.begin("proposal_1", "browser_download")
    finished = live.begin("proposal_2", "create_backup")
    live.complete(finished.execution_id, status="completed", note="done before restart")

    restarted = ExecutionControlRegistry(db)  # fresh process over the same file
    interrupted = restarted.get(running.execution_id)
    assert interrupted.status == "interrupted"  # running row marked on init
    assert interrupted.completed_at is not None
    still_done = restarted.get(finished.execution_id)
    assert still_done.status == "completed"  # terminal rows are never rewritten

    live.record_result(running.execution_id, {"success": True, "goal_verified": True})
    again = ExecutionControlRegistry(db)
    assert again.get_result(running.execution_id)["goal_verified"] is True  # evidence persisted


def test_preemption_and_reconciliation_survive_restart_and_resume_skips_verified_work(tmp_path):
    exec_db = str(tmp_path / "exec.db")
    preempt_db = tmp_path / "preempt.db"
    step_db = tmp_path / "steps.db"

    # Live process: an execution is cancelled mid-flight and preempted. The
    # cancellation must be OBSERVED (cooperative checkpoint) — a cancel request
    # alone never claims observation.
    registry = ExecutionControlRegistry(exec_db)
    record = registry.begin("proposal_9", "copy_file_verified")
    registry.request_cancel(record.execution_id)
    from app.cognition.execution_control import ExecutionCancelled
    try:
        with registry.scope(record.execution_id):
            registry.checkpoint("cancelled_during:test")
    except ExecutionCancelled:
        pass  # expected: the checkpoint both observes and signals cancellation
    registry.complete(record.execution_id, status="cancelled", note="Owner cancelled")
    cancelled_row = registry.get(record.execution_id)
    assert cancelled_row.cancellation_observed is True
    preemptions = AutonomyPreemptionStore(preempt_db)
    receipt = preemptions.create(record.execution_id, "urgent_goal",
                                 plan_id="plan_resume", reason="Urgent owner priority")

    # "Restart": fresh instances over the same files.
    registry2 = ExecutionControlRegistry(exec_db)
    preemptions2 = AutonomyPreemptionStore(preempt_db)
    persisted = preemptions2.get(receipt.preemption_id)
    assert persisted is not None and persisted.plan_id == "plan_resume"
    refreshed = preemptions2.refresh(receipt.preemption_id, registry2.get(record.execution_id).to_dict())
    assert refreshed.status == "resume_ready"  # observation state survived restart

    # Reconciliation applied before the restart is visible after it.
    before_restart = PlanStepReconciliationStore(step_db)
    before_restart.apply("plan_resume",
                         {"step_id": "step_first", "action_type": "copy_file_verified", "payload": {}},
                         "skip_verified_step_and_review_next",
                         verification={"goal_verified": True},
                         preemption_id=receipt.preemption_id, execution_id=record.execution_id)
    after_restart = PlanStepReconciliationStore(step_db)
    assert after_restart.get("step_first").status == "completed"

    # The resumed plan (fresh executor process) skips the verified step.
    first = ExecutionStep(step_id="step_first", description="Copy report",
                          task_type=TaskType.ANALYSIS, action_type="copy_file_verified", payload={})
    second = ExecutionStep(step_id="step_second", description="Archive report",
                           task_type=TaskType.ANALYSIS, action_type="compress_files", payload={},
                           depends_on=["step_first"])
    plan = ExecutionPlan(plan_id="plan_resume", goal_id="g1", goal_title="Safely move report",
                         steps=[first, second])
    executor = AutonomousGoalExecutor.__new__(AutonomousGoalExecutor)
    executed = []
    with patch.object(AutonomousGoalExecutor, "save_plan", lambda self, p: None), \
         patch.object(AutonomousGoalExecutor, "execute_step",
                      lambda self, s, crt=None: executed.append(s.step_id) or setattr(s, "status", ExecutionStatus.COMPLETED)), \
         patch("app.cognition.plan_step_reconciliation.plan_step_reconciliation_store", after_restart):
        executor._execute_plan_steps(plan)
    # Verified work is not re-executed after the restart; the dependent runs once.
    assert executed == ["step_second"]
    assert plan.steps[0].status == ExecutionStatus.COMPLETED
    assert "skipped on resume" in plan.steps[0].result


def test_restart_during_cycle_lease_does_not_double_execute_schedule(tmp_path):
    # A schedule release claimed but not completed (crash between claim and
    # goal creation) must not double-release after restart: the stale claim is
    # cleared and the deterministic occurrence id prevents a duplicate goal.
    schedule = AutonomySchedule(tmp_path / "s.db")
    goals = AutonomousGoalGenerator(str(tmp_path / "g.db"))
    due = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    schedule.create("Crash window", due, recurrence="daily", missed_policy="run_once")
    # Simulate a crashed claim: claim_token set 30 minutes ago (past 15-min stale horizon).
    with sqlite3.connect(schedule.path) as conn:
        conn.execute(
            "UPDATE autonomy_schedule SET claim_token='claim_crashed', claimed_at=? WHERE title='Crash window'",
            ((datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),),
        )
        conn.commit()
    restarted = AutonomySchedule(schedule.path)
    first = restarted.release_due(goals)
    second = restarted.release_due(goals)
    assert len(first["released_goals"]) == 1
    assert second["released_goals"] == []
    assert goals.count_goals() == 1
