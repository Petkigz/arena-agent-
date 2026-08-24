"""Atomic timezone-aware owner task calendar."""
from __future__ import annotations
import hashlib,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

def _now():return datetime.now(timezone.utc)
def _parse(value,timezone_name='UTC'):
 d=datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:d=d.replace(tzinfo=ZoneInfo(timezone_name))
 return d.astimezone(timezone.utc)
@dataclass(frozen=True)
class ScheduledDirective:
 schedule_id:str;title:str;description:str;priority:str;next_run_at:str;recurrence:str
 missed_policy:str;approve_for_planning:bool;status:str;last_run_at:Optional[str]
 created_at:str;timezone_name:str='UTC'
 def to_dict(self):return asdict(self)
class AutonomySchedule:
 RECURRENCES={'none','daily','weekly'};MISSED={'run_once','skip'}
 def __init__(self,path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:
   c.execute('''CREATE TABLE IF NOT EXISTS autonomy_schedule
   (schedule_id TEXT PRIMARY KEY,title TEXT,description TEXT,priority TEXT,next_run_at TEXT,
   recurrence TEXT,missed_policy TEXT,approve_for_planning INTEGER,status TEXT,last_run_at TEXT,
   created_at TEXT,timezone_name TEXT DEFAULT 'UTC',claim_token TEXT,claimed_at TEXT)''')
   columns={r[1] for r in c.execute('PRAGMA table_info(autonomy_schedule)')}
   for name,ddl in [('timezone_name',"TEXT DEFAULT 'UTC'"),('claim_token','TEXT'),('claimed_at','TEXT')]:
    if name not in columns:c.execute(f'ALTER TABLE autonomy_schedule ADD COLUMN {name} {ddl}')
   c.commit()
 def _item(self,r):return ScheduledDirective(r[0],r[1],r[2],r[3],r[4],r[5],r[6],bool(r[7]),r[8],r[9],r[10],r[11] or 'UTC')
 def create(self,title,run_at,*,description='',priority='normal',recurrence='none',missed_policy='run_once',approve_for_planning=True,timezone_name='UTC'):
  if recurrence not in self.RECURRENCES or missed_policy not in self.MISSED:raise ValueError('Invalid recurrence or missed-run policy')
  try:ZoneInfo(timezone_name)
  except Exception as exc:raise ValueError(f'Invalid timezone: {timezone_name}') from exc
  when=_parse(run_at,timezone_name).isoformat();created=_now().isoformat();sid=f'schedule_{uuid4().hex[:16]}'
  item=ScheduledDirective(sid,title,description,priority,when,recurrence,missed_policy,approve_for_planning,'active',None,created,timezone_name)
  with sqlite3.connect(self.path) as c:c.execute('INSERT INTO autonomy_schedule VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(sid,title,description,priority,when,recurrence,missed_policy,int(approve_for_planning),'active',None,created,timezone_name,None,None));c.commit()
  return item
 def list(self,status=None,limit=500):
  q='SELECT * FROM autonomy_schedule';params=[]
  if status:q+=' WHERE status=?';params.append(status)
  q+=' ORDER BY next_run_at LIMIT ?';params.append(max(1,min(limit,2000)))
  with sqlite3.connect(self.path) as c:rows=c.execute(q,params).fetchall()
  return [self._item(r) for r in rows]
 def set_status(self,schedule_id,status):
  if status not in ('active','paused','cancelled'):raise ValueError('Invalid schedule status')
  with sqlite3.connect(self.path) as c:
   if not c.execute('SELECT 1 FROM autonomy_schedule WHERE schedule_id=?',(schedule_id,)).fetchone():raise KeyError(schedule_id)
   c.execute('UPDATE autonomy_schedule SET status=?,claim_token=NULL,claimed_at=NULL WHERE schedule_id=?',(status,schedule_id));c.commit()
  return next(x for x in self.list() if x.schedule_id==schedule_id)
 def _next_future(self,item,due,now):
  if item.recurrence=='none':return due,'completed'
  zone=ZoneInfo(item.timezone_name);local=due.astimezone(zone);step=timedelta(days=1 if item.recurrence=='daily' else 7)
  local+=step
  while local.astimezone(timezone.utc)<=now:local+=step
  return local.astimezone(timezone.utc),'active'
 def release_due(self,goal_generator,now=None):
  now=now or _now();token=f'claim_{uuid4().hex[:16]}';stale=(now-timedelta(minutes=15)).isoformat()
  with sqlite3.connect(self.path,timeout=10,isolation_level=None) as c:
   c.execute('BEGIN IMMEDIATE');c.execute("UPDATE autonomy_schedule SET claim_token=NULL,claimed_at=NULL WHERE claim_token IS NOT NULL AND claimed_at<?",(stale,))
   ids=[r[0] for r in c.execute("SELECT schedule_id FROM autonomy_schedule WHERE status='active' AND claim_token IS NULL AND next_run_at<=? ORDER BY next_run_at LIMIT 2000",(now.isoformat(),)).fetchall()]
   for sid in ids:c.execute('UPDATE autonomy_schedule SET claim_token=?,claimed_at=? WHERE schedule_id=? AND claim_token IS NULL',(token,now.isoformat(),sid))
   rows=c.execute('SELECT * FROM autonomy_schedule WHERE claim_token=?',(token,)).fetchall();c.execute('COMMIT')
  released=[];skipped=[];errors=[]
  for row in rows:
   item=self._item(row);due=_parse(item.next_run_at,item.timezone_name);late=(now-due).total_seconds();skip=item.missed_policy=='skip' and late>3600
   goal_id='scheduled_'+hashlib.sha256(f'{item.schedule_id}|{due.isoformat()}'.encode()).hexdigest()[:16]
   try:
    if not skip:
     existing=goal_generator.get_goal(goal_id)
     if existing:goal=existing
     else:
      from app.cognition.autonomous_goal_generator import AutonomousGoal,GoalPriority,GoalSource,IntrinsicMotivation
      goal=AutonomousGoal(goal_id=goal_id,title=item.title,description=item.description,priority=GoalPriority(item.priority),source=GoalSource.OWNER_DIRECTIVE,motivation=IntrinsicMotivation.HELPFULNESS,trigger_observation=f'schedule:{item.schedule_id}:{due.isoformat()}',user_benefit='Owner scheduled directive')
      goal_generator.add_goal(goal);goal_generator.evaluate_goal(goal)
      if item.approve_for_planning:goal=goal_generator.owner_decide_goal(goal.goal_id,True)
     released.append(goal)
    else:skipped.append(item.schedule_id)
    nxt,status=self._next_future(item,due,now)
    with sqlite3.connect(self.path) as c:c.execute('UPDATE autonomy_schedule SET next_run_at=?,last_run_at=?,status=?,claim_token=NULL,claimed_at=NULL WHERE schedule_id=? AND claim_token=?',(nxt.isoformat(),now.isoformat(),status,item.schedule_id,token));c.commit()
   except Exception as exc:
    errors.append({'schedule_id':item.schedule_id,'error':str(exc)})
    with sqlite3.connect(self.path) as c:c.execute('UPDATE autonomy_schedule SET claim_token=NULL,claimed_at=NULL WHERE schedule_id=? AND claim_token=?',(item.schedule_id,token));c.commit()
  return {'released_goals':released,'skipped_schedule_ids':skipped,'errors':errors,'claim_token':token}
