"""Cross-session environment assumptions bound to an approved plan revision."""
from __future__ import annotations
import hashlib,json,sqlite3
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional

def _now():return datetime.now(timezone.utc).isoformat()
def _digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
@dataclass(frozen=True)
class PlanFreshness:
 plan_id:str;revision:int;fresh:bool;baseline_digest:Optional[str];current_digest:Optional[str];changes:List[Dict[str,Any]];captured_at:Optional[str]
 def to_dict(self):return asdict(self)
class PlanFreshnessStore:
 def __init__(self,path:str|Path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:c.execute('CREATE TABLE IF NOT EXISTS plan_assumptions (plan_id TEXT,revision INTEGER,snapshot_json TEXT,digest TEXT,captured_at TEXT,PRIMARY KEY(plan_id,revision))');c.commit()
 def build_snapshot(self,review,runtime):
  from app.cognition.owner_control import owner_control_store
  from app.tools.manifest import get_tool_manifest
  manifest=get_tool_manifest();steps=review.snapshot.get('steps',[]);contracts=[]
  for step in steps:
   action=str(step.get('action_type',''));entry=manifest.get(action,{})
   availability=runtime.registry.get_tool_availability(action,probe=False) if action else {'status':'no_action'}
   contracts.append({'step_id':step.get('step_id'),'action_type':action,'safety_level':entry.get('safety_level'),'availability':availability.get('status')})
  interfaces=[]
  if hasattr(runtime,'embodied_boundary'):
   interfaces=[{'interface_id':x.interface_id,'available':x.available,'kind':x.kind} for x in runtime.embodied_boundary.interfaces()]
  goal_priority=None
  try:
   goal=runtime.goal_generator.get_goal(review.goal_id);goal_priority=goal.priority.value if goal else None
  except Exception:pass
  policy=owner_control_store.get_policy()
  return {'plan_id':review.plan_id,'revision':review.revision,'snapshot_sha256':review.snapshot_sha256,'owner_policy_revision':policy.revision,'tool_count':len(runtime.registry._registry),'action_contracts':contracts,'interfaces':interfaces,'goal_priority':goal_priority}
 def capture(self,review,runtime):
  snap=self.build_snapshot(review,runtime);digest=_digest(snap);now=_now()
  with sqlite3.connect(self.path) as c:c.execute('INSERT OR REPLACE INTO plan_assumptions VALUES (?,?,?,?,?)',(review.plan_id,review.revision,json.dumps(snap),digest,now));c.commit()
  return PlanFreshness(review.plan_id,review.revision,True,digest,digest,[],now)
 def validate(self,review,runtime):
  current=self.build_snapshot(review,runtime);current_digest=_digest(current)
  with sqlite3.connect(self.path) as c:r=c.execute('SELECT snapshot_json,digest,captured_at FROM plan_assumptions WHERE plan_id=? AND revision=?',(review.plan_id,review.revision)).fetchone()
  if not r:return PlanFreshness(review.plan_id,review.revision,False,None,current_digest,[{'field':'baseline','before':None,'after':'missing'}],None)
  baseline=json.loads(r[0]);changes=[]
  for field in ('snapshot_sha256','owner_policy_revision','tool_count','action_contracts','interfaces','goal_priority'):
   if baseline.get(field)!=current.get(field):changes.append({'field':field,'before':baseline.get(field),'after':current.get(field)})
  return PlanFreshness(review.plan_id,review.revision,not changes,r[1],current_digest,changes,r[2])
