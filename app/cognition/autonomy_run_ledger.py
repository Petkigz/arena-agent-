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

def _parse_iso(value):
 from datetime import datetime
 if isinstance(value,datetime): return value
 try: return datetime.fromisoformat(str(value))
 except Exception: return None

def attach_cycle_links(events,*,commitment_ledger=None,recovery_store=None):
 """Join commitment and recovery provenance onto recorded timeline events.

 This is a READ-TIME join over immutable stored events: `commitment_links`
 reflect the current commitment state for the plan an event references, and
 `recovery_assessment_ids` list recovery assessments raised during the event's
 OWN cycle time window (temporal co-occurrence, labeled as such — it is not a
 causation claim). Windows are computed per cycle_id so cross-cycle queries
 never mix windows. Joins never rewrite stored evidence.
 """
 from datetime import datetime,timezone
 ordered=list(events)
 windows={}
 for e in ordered:
  cycle_id=getattr(e,'cycle_id',None)
  if cycle_id is None: continue
  window=windows.setdefault(cycle_id,{'started':None,'ended':None})
  if getattr(e,'stage','')=='cycle_started': window['started']=(getattr(e,'details',None) or {}).get('started_at')
  parsed=_parse_iso(getattr(e,'created_at',None))
  if parsed and (window['ended'] is None or parsed>window['ended']): window['ended']=parsed
 now=datetime.now(timezone.utc)
 recovery_by_cycle={}
 if recovery_store is not None:
  try: assessments=list(recovery_store.list(limit=1000))
  except Exception: assessments=[]
  for cycle_id,window in windows.items():
   start_dt=_parse_iso(window['started'])
   if start_dt is None: continue
   end_dt=window['ended'] or now
   links=[]
   for assessment in assessments:
    created=_parse_iso(getattr(assessment,'created_at',None))
    if created is not None and start_dt<=created<=end_dt:
     links.append({'assessment_id':assessment.assessment_id,'status':assessment.status,'created_at':assessment.created_at,'raised_during_cycle':True})
   recovery_by_cycle[cycle_id]=links
 enriched=[]
 for e in ordered:
  out=e.to_dict()
  details=out.get('details') or {}
  plan_id=details.get('plan_id')
  out['commitment_links']=None
  if commitment_ledger is not None and plan_id:
   try:
    commitment=commitment_ledger.get_by_source('approved_plan',str(plan_id))
    if commitment is not None:
     out['commitment_links']=[{'commitment_id':commitment.commitment_id,'status':commitment.status,'completion_verified':commitment.completion_verified,'source':f'approved_plan:{plan_id}'}]
   except Exception: out['commitment_links']=None
  out['recovery_assessment_ids']=list(recovery_by_cycle.get(out.get('cycle_id'),[]))
  enriched.append(out)
 return enriched
