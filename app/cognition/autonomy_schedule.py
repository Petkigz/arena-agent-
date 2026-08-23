"""Persistent owner task calendar released through the autonomous goal queue."""
from __future__ import annotations
import sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import List,Optional
from uuid import uuid4

def _now(): return datetime.now(timezone.utc)
def _parse(v):
 d=datetime.fromisoformat(v.replace('Z','+00:00')); return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
@dataclass(frozen=True)
class ScheduledDirective:
 schedule_id:str; title:str; description:str; priority:str; next_run_at:str
 recurrence:str; missed_policy:str; approve_for_planning:bool; status:str
 last_run_at:Optional[str]; created_at:str
 def to_dict(self): return asdict(self)
class AutonomySchedule:
 RECURRENCES={'none','daily','weekly'}; MISSED={'run_once','skip'}
 def __init__(self,path:str|Path):
  self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:
   c.execute('''CREATE TABLE IF NOT EXISTS autonomy_schedule
   (schedule_id TEXT PRIMARY KEY,title TEXT,description TEXT,priority TEXT,next_run_at TEXT,
   recurrence TEXT,missed_policy TEXT,approve_for_planning INTEGER,status TEXT,last_run_at TEXT,created_at TEXT)''');c.commit()
 def create(self,title,run_at,*,description='',priority='normal',recurrence='none',missed_policy='run_once',approve_for_planning=True):
  if recurrence not in self.RECURRENCES or missed_policy not in self.MISSED: raise ValueError('Invalid recurrence or missed-run policy')
  when=_parse(run_at).isoformat(); created=_now().isoformat(); sid=f'schedule_{uuid4().hex[:16]}'
  item=ScheduledDirective(sid,title,description,priority,when,recurrence,missed_policy,approve_for_planning,'active',None,created)
  with sqlite3.connect(self.path) as c:c.execute('INSERT INTO autonomy_schedule VALUES (?,?,?,?,?,?,?,?,?,?,?)',(sid,title,description,priority,when,recurrence,missed_policy,int(approve_for_planning),'active',None,created));c.commit()
  return item
 def list(self,status=None,limit=500):
  q='SELECT * FROM autonomy_schedule';p=[]
  if status:q+=' WHERE status=?';p.append(status)
  q+=' ORDER BY next_run_at LIMIT ?';p.append(max(1,min(limit,2000)))
  with sqlite3.connect(self.path) as c:rows=c.execute(q,p).fetchall()
  return [ScheduledDirective(r[0],r[1],r[2],r[3],r[4],r[5],r[6],bool(r[7]),r[8],r[9],r[10]) for r in rows]
 def set_status(self,schedule_id,status):
  if status not in ('active','paused','cancelled'):raise ValueError('Invalid schedule status')
  with sqlite3.connect(self.path) as c:
   if not c.execute('SELECT 1 FROM autonomy_schedule WHERE schedule_id=?',(schedule_id,)).fetchone():raise KeyError(schedule_id)
   c.execute('UPDATE autonomy_schedule SET status=? WHERE schedule_id=?',(status,schedule_id));c.commit()
  return next(x for x in self.list() if x.schedule_id==schedule_id)
 def release_due(self,goal_generator,now=None):
  now=now or _now(); released=[]; skipped=[]
  for item in self.list('active',2000):
   due=_parse(item.next_run_at)
   if due>now: continue
   lateness=(now-due).total_seconds()
   should_skip=item.missed_policy=='skip' and lateness>3600
   if not should_skip:
    from app.cognition.autonomous_goal_generator import AutonomousGoal,GoalPriority,GoalSource,IntrinsicMotivation
    goal=AutonomousGoal(title=item.title,description=item.description,priority=GoalPriority(item.priority),source=GoalSource.OWNER_DIRECTIVE,motivation=IntrinsicMotivation.HELPFULNESS,trigger_observation=f'schedule:{item.schedule_id}',user_benefit='Owner scheduled directive')
    goal_generator.add_goal(goal);goal_generator.evaluate_goal(goal)
    if item.approve_for_planning:goal=goal_generator.owner_decide_goal(goal.goal_id,True)
    released.append(goal)
   else: skipped.append(item.schedule_id)
   if item.recurrence=='daily': nxt=due+timedelta(days=1);status='active'
   elif item.recurrence=='weekly':nxt=due+timedelta(days=7);status='active'
   else:nxt=due;status='completed'
   with sqlite3.connect(self.path) as c:c.execute('UPDATE autonomy_schedule SET next_run_at=?,last_run_at=?,status=? WHERE schedule_id=?',(nxt.isoformat(),now.isoformat(),status,item.schedule_id));c.commit()
  return {'released_goals':released,'skipped_schedule_ids':skipped}
