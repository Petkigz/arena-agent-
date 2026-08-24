from datetime import datetime,timedelta,timezone
from app.cognition.autonomy_lease import AutonomyCycleLease
from app.cognition.autonomy_schedule import AutonomySchedule
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator
from app.main import execute_next_autonomous_goal_endpoint

def test_only_one_cycle_lease_holder(tmp_path):
 a=AutonomyCycleLease(tmp_path/'lease.db');b=AutonomyCycleLease(tmp_path/'lease.db')
 first=a.acquire();second=b.acquire()
 assert first['acquired'] is True and second['acquired'] is False
 assert a.release(first['holder']) is True
 assert b.acquire()['acquired'] is True

def test_schedule_claim_prevents_duplicate_release_and_catches_up(tmp_path):
 schedule=AutonomySchedule(tmp_path/'schedule.db');goals=AutonomousGoalGenerator(str(tmp_path/'goals.db'))
 now=datetime.now(timezone.utc);item=schedule.create('Daily owner task',(now-timedelta(days=5)).isoformat(),recurrence='daily',timezone_name='UTC')
 first=schedule.release_due(goals,now);second=schedule.release_due(goals,now)
 assert len(first['released_goals'])==1 and second['released_goals']==[]
 current=next(x for x in schedule.list() if x.schedule_id==item.schedule_id)
 assert datetime.fromisoformat(current.next_run_at)>now
 assert goals.count_goals()==1

def test_manual_execute_next_uses_same_cycle_lease(tmp_path):
 lease=AutonomyCycleLease(tmp_path/'lease.db');held=lease.acquire()
 runtime=SimpleNamespace(autonomy_cycle_lease=lease,execute_autonomous_goal=lambda:(_ for _ in ()).throw(AssertionError('must not execute')))
 with patch('app.cognition.runtime.CognitiveRuntime.get_instance',return_value=runtime):
  with pytest.raises(HTTPException) as exc:execute_next_autonomous_goal_endpoint()
 assert exc.value.status_code==409
 lease.release(held['holder'])

def test_timezone_preserves_local_daily_wall_time(tmp_path):
 schedule=AutonomySchedule(tmp_path/'schedule.db');goals=AutonomousGoalGenerator(str(tmp_path/'goals.db'))
 # 09:00 Kampala is 06:00 UTC and has no DST; recurrence remains local 09:00.
 item=schedule.create('Morning','2026-08-20T09:00:00',recurrence='daily',timezone_name='Africa/Kampala')
 now=datetime(2026,8,24,7,0,tzinfo=timezone.utc);schedule.release_due(goals,now)
 current=next(x for x in schedule.list() if x.schedule_id==item.schedule_id)
 assert datetime.fromisoformat(current.next_run_at).astimezone(__import__('zoneinfo').ZoneInfo('Africa/Kampala')).hour==9
 assert datetime.fromisoformat(current.next_run_at)>now
