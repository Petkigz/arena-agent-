"""Timezone/DST safety for recurring schedules, pinned.

Empirically verified behavior (Europe/Berlin; Africa/Kampala has no DST):
  * Daily/weekly wall time is preserved across fall-back and spring-forward
    transitions (09:00 stays 09:00 local; the UTC offset shifts correctly).
  * Ambiguous local times during fall-back resolve to the FIRST occurrence
    (fold=0), deterministically — never twice.
  * Nonexistent local times during spring-forward shift forward by the gap
    (02:30 → 03:30) — the occurrence still fires, never silently skipped.
These tests pin that behavior so refactors cannot silently break it.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator
from app.cognition.autonomy_schedule import AutonomySchedule

BERLIN = ZoneInfo("Europe/Berlin")


def setup(tmp_path):
    schedule = AutonomySchedule(tmp_path / "s.db")
    goals = AutonomousGoalGenerator(str(tmp_path / "g.db"))
    return schedule, goals


def current(schedule, schedule_id):
    return next(x for x in schedule.list() if x.schedule_id == schedule_id)


def test_daily_wall_time_survives_fall_back(tmp_path):
    schedule, goals = setup(tmp_path)
    item = schedule.create("Morning", "2026-10-23T09:00:00",
                           recurrence="daily", timezone_name="Europe/Berlin")
    # Fall-back: 2026-10-25 03:00 CEST → 02:00 CET.
    for day in (23, 24, 25):
        schedule.release_due(goals, datetime(2026, 10, day, 10, 30, tzinfo=timezone.utc))
    nxt = datetime.fromisoformat(current(schedule, item.schedule_id).next_run_at)
    local = nxt.astimezone(BERLIN)
    assert local.year == 2026 and local.month == 10 and local.day == 26
    assert (local.hour, local.minute) == (9, 0)   # wall time preserved
    assert local.utcoffset().total_seconds() == 3600  # CET after the transition


def test_daily_wall_time_survives_spring_forward(tmp_path):
    schedule, goals = setup(tmp_path)
    item = schedule.create("Morning", "2027-03-26T09:00:00",
                           recurrence="daily", timezone_name="Europe/Berlin")
    # Spring-forward: 2027-03-28 02:00 CET → 03:00 CEST.
    for day in (26, 27, 28):
        schedule.release_due(goals, datetime(2027, 3, day, 10, 30, tzinfo=timezone.utc))
    nxt = datetime.fromisoformat(current(schedule, item.schedule_id).next_run_at)
    local = nxt.astimezone(BERLIN)
    assert (local.month, local.day) == (3, 29)
    assert (local.hour, local.minute) == (9, 0)
    assert local.utcoffset().total_seconds() == 7200  # CEST after the transition


def test_ambiguous_fall_back_time_fires_once_at_first_occurrence(tmp_path):
    schedule, goals = setup(tmp_path)
    item = schedule.create("Edge 0230", "2026-10-24T02:30:00",
                           recurrence="daily", timezone_name="Europe/Berlin")
    # On 2026-10-25 local 02:30 exists twice (00:30 UTC and 01:30 UTC).
    schedule.release_due(goals, datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc))
    nxt = datetime.fromisoformat(current(schedule, item.schedule_id).next_run_at)
    assert nxt == datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)  # FIRST occurrence (fold=0)
    # Polling during BOTH instants of the repeated hour releases exactly once.
    first = schedule.release_due(goals, datetime(2026, 10, 25, 0, 45, tzinfo=timezone.utc))
    second = schedule.release_due(goals, datetime(2026, 10, 25, 1, 45, tzinfo=timezone.utc))
    assert len(first["released_goals"]) == 1 and second["released_goals"] == []
    nxt2_local = datetime.fromisoformat(
        current(schedule, item.schedule_id).next_run_at).astimezone(BERLIN)
    assert (nxt2_local.hour, nxt2_local.minute) == (2, 30)
    assert nxt2_local.utcoffset().total_seconds() == 3600  # CET after fall-back


def test_nonexistent_spring_forward_time_shifts_forward_not_skipped(tmp_path):
    schedule, goals = setup(tmp_path)
    # 2027-03-28 02:30 local does not exist (clocks jump 02:00→03:00).
    item = schedule.create("Nonexistent", "2027-03-27T02:30:00",
                           recurrence="daily", timezone_name="Europe/Berlin")
    schedule.release_due(goals, datetime(2027, 3, 27, 1, 30, tzinfo=timezone.utc))
    nxt = datetime.fromisoformat(current(schedule, item.schedule_id).next_run_at)
    assert nxt == datetime(2027, 3, 28, 1, 30, tzinfo=timezone.utc)  # = 03:30 CEST local
    # The occurrence still fires on the transition day — never silently skipped.
    fired = schedule.release_due(goals, datetime(2027, 3, 28, 2, 0, tzinfo=timezone.utc))
    assert len(fired["released_goals"]) == 1


def test_weekly_recurrence_crosses_dst_at_exact_wall_time(tmp_path):
    schedule, goals = setup(tmp_path)
    item = schedule.create("Weekly", "2026-10-16T09:00:00",
                           recurrence="weekly", timezone_name="Europe/Berlin")
    schedule.release_due(goals, datetime(2026, 10, 16, 7, 30, tzinfo=timezone.utc))
    nxt = datetime.fromisoformat(current(schedule, item.schedule_id).next_run_at)
    assert nxt.astimezone(BERLIN) == datetime(2026, 10, 23, 9, 0, tzinfo=BERLIN)
    # Advance past the transition: the following week is CET, still 09:00 local.
    schedule.release_due(goals, datetime(2026, 10, 23, 7, 30, tzinfo=timezone.utc))
    nxt2 = datetime.fromisoformat(current(schedule, item.schedule_id).next_run_at)
    local2 = nxt2.astimezone(BERLIN)
    assert local2 == datetime(2026, 10, 30, 9, 0, tzinfo=BERLIN)
    assert local2.utcoffset().total_seconds() == 3600
