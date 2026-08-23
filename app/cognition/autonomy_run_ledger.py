"""Persistent stage-by-stage audit ledger for autonomous work."""
from __future__ import annotations
import json,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional
from uuid import uuid4

def _now(): return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class AutonomyEvent:
 event_id:str; cycle_id:str; goal_id:Optional[str]; stage:str; reason:str; details:Dict[str,Any]; created_at:str
 def to_dict(self): return asdict(self)
class AutonomyRunLedger:
 STAGES={'cycle_started','cycle_skipped','observed','considered','recommended','approved_for_planning','execution_started','executed','blocked','budget_stopped','cycle_completed','cycle_failed'}
 def __init__(self,path:str|Path):
  self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:
   c.execute('CREATE TABLE IF NOT EXISTS autonomy_events (event_id TEXT PRIMARY KEY,cycle_id TEXT,goal_id TEXT,stage TEXT,reason TEXT,details_json TEXT,created_at TEXT)'); c.commit()
 def record(self,cycle_id:str,stage:str,*,goal_id=None,reason='',details=None):
  if stage not in self.STAGES: raise ValueError(f'Unknown autonomy stage: {stage}')
  e=AutonomyEvent(f'auto_{uuid4().hex[:16]}',cycle_id,goal_id,stage,reason,details or {},_now())
  with sqlite3.connect(self.path) as c: c.execute('INSERT INTO autonomy_events VALUES (?,?,?,?,?,?,?)',(e.event_id,e.cycle_id,e.goal_id,e.stage,e.reason,json.dumps(e.details,default=str),e.created_at)); c.commit()
  return e
 def list(self,*,cycle_id=None,goal_id=None,limit=500):
  q='SELECT * FROM autonomy_events WHERE 1=1'; p=[]
  if cycle_id:q+=' AND cycle_id=?';p.append(cycle_id)
  if goal_id:q+=' AND goal_id=?';p.append(goal_id)
  q+=' ORDER BY created_at DESC LIMIT ?';p.append(max(1,min(limit,2000)))
  with sqlite3.connect(self.path) as c: rows=c.execute(q,p).fetchall()
  return [AutonomyEvent(r[0],r[1],r[2],r[3],r[4],json.loads(r[5]),r[6]) for r in rows]
