from datetime import datetime,timedelta,timezone
from app.cognition.autonomy_schedule import AutonomySchedule
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator

def test_one_time_schedule_releases_owner_goal(tmp_path):
 s=AutonomySchedule(tmp_path/'s.db'); g=AutonomousGoalGenerator(str(tmp_path/'g.db'))
 item=s.create('Owner report',(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),priority='critical')
 result=s.release_due(g)
 assert len(result['released_goals'])==1
 assert result['released_goals'][0].status.value=='approved'
 assert next(x for x in s.list() if x.schedule_id==item.schedule_id).status=='completed'

def test_daily_schedule_advances_and_missed_skip_is_honored(tmp_path):
 s=AutonomySchedule(tmp_path/'s.db'); g=AutonomousGoalGenerator(str(tmp_path/'g.db'))
 old=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
 skipped=s.create('Skip stale',old,missed_policy='skip')
 daily=s.create('Daily',old,recurrence='daily',missed_policy='run_once',approve_for_planning=False)
 result=s.release_due(g)
 assert skipped.schedule_id in result['skipped_schedule_ids']
 assert len(result['released_goals'])==1
 assert result['released_goals'][0].status.value=='evaluated'
 assert next(x for x in s.list() if x.schedule_id==daily.schedule_id).status=='active'
