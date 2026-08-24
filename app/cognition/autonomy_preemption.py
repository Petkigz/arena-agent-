"""Persistent receipts for owner-directed preemption and safe resume review."""
from __future__ import annotations
import json,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional
from uuid import uuid4

def _now():return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class PreemptionReceipt:
 preemption_id:str; execution_id:str; urgent_goal_id:str; interrupted_goal_id:Optional[str]
 plan_id:Optional[str]; status:str; reason:str; cancellation_observed:bool
 side_effect_state:str; requires_observation_reconciliation:bool
 resume_requested:bool; created_at:str; updated_at:str
 def to_dict(self):return asdict(self)
class AutonomyPreemptionStore:
 def __init__(self,path:str|Path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:
   c.execute('''CREATE TABLE IF NOT EXISTS autonomy_preemptions
   (preemption_id TEXT PRIMARY KEY,execution_id TEXT,urgent_goal_id TEXT,interrupted_goal_id TEXT,
   plan_id TEXT,status TEXT,reason TEXT,cancellation_observed INTEGER,side_effect_state TEXT,
   requires_reconciliation INTEGER,resume_requested INTEGER,created_at TEXT,updated_at TEXT)''')
   c.execute('''CREATE TABLE IF NOT EXISTS preemption_reconciliations
   (preemption_id TEXT PRIMARY KEY,result_json TEXT,recorded_at TEXT)''');c.commit()
 def _row(self,r):return PreemptionReceipt(r[0],r[1],r[2],r[3],r[4],r[5],r[6],bool(r[7]),r[8],bool(r[9]),bool(r[10]),r[11],r[12])
 def create(self,execution_id,urgent_goal_id,*,interrupted_goal_id=None,plan_id=None,reason='Urgent owner priority'):
  now=_now();x=PreemptionReceipt(f'preempt_{uuid4().hex[:16]}',execution_id,urgent_goal_id,interrupted_goal_id,plan_id,'cancellation_requested',reason,False,'unknown',True,False,now,now)
  with sqlite3.connect(self.path) as c:c.execute('INSERT INTO autonomy_preemptions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(x.preemption_id,x.execution_id,x.urgent_goal_id,x.interrupted_goal_id,x.plan_id,x.status,x.reason,0,x.side_effect_state,1,0,now,now));c.commit()
  return x
 def refresh(self,preemption_id,execution:Dict[str,Any]):
  current=self.get(preemption_id)
  if not current:raise KeyError(preemption_id)
  observed=bool(execution.get('cancellation_observed')); execution_status=execution.get('status','unknown')
  if observed and execution_status=='cancelled':status='resume_ready' if current.plan_id else 'resume_blocked';side='partial_or_unknown'
  elif execution_status=='completed_after_cancel_request':status='resume_blocked';side='side_effects_may_exist'
  elif execution_status in ('completed','failed'):status='resume_blocked';side='terminal_execution_requires_fresh_verification'
  else:status='cancellation_requested';side='unknown'
  now=_now()
  with sqlite3.connect(self.path) as c:c.execute('UPDATE autonomy_preemptions SET status=?,cancellation_observed=?,side_effect_state=?,updated_at=? WHERE preemption_id=?',(status,int(observed),side,now,preemption_id));c.commit()
  return self.get(preemption_id)
 def request_resume(self,preemption_id):
  x=self.get(preemption_id)
  if not x:raise KeyError(preemption_id)
  if x.status!='resume_ready':raise ValueError('Preemption is not resume-ready')
  now=_now()
  with sqlite3.connect(self.path) as c:c.execute("UPDATE autonomy_preemptions SET status='resume_requested',resume_requested=1,updated_at=? WHERE preemption_id=?",(now,preemption_id));c.commit()
  return self.get(preemption_id)
 def record_reconciliation(self,preemption_id,result):
  if not self.get(preemption_id):raise KeyError(preemption_id)
  with sqlite3.connect(self.path) as c:c.execute('INSERT OR REPLACE INTO preemption_reconciliations VALUES (?,?,?)',(preemption_id,json.dumps(result,default=str),_now()));c.commit()
  return result
 def get_reconciliation(self,preemption_id):
  with sqlite3.connect(self.path) as c:r=c.execute('SELECT result_json FROM preemption_reconciliations WHERE preemption_id=?',(preemption_id,)).fetchone()
  return json.loads(r[0]) if r else None
 def get(self,i):
  with sqlite3.connect(self.path) as c:r=c.execute('SELECT * FROM autonomy_preemptions WHERE preemption_id=?',(i,)).fetchone()
  return self._row(r) if r else None
 def list(self,limit=200):
  with sqlite3.connect(self.path) as c:rows=c.execute('SELECT * FROM autonomy_preemptions ORDER BY created_at DESC LIMIT ?',(max(1,min(limit,1000)),)).fetchall()
  return [self._row(r) for r in rows]
