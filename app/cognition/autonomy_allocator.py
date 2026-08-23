"""Resource-aware multi-goal allocation with owner priority dominance."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Any,Dict,List,Optional
@dataclass(frozen=True)
class GoalAllocation:
 goal_id:str;score:float;eligible:bool;reasons:List[str];resource_penalty:float
 def to_dict(self):return asdict(self)
class AutonomyResourceAllocator:
 PRIORITY={'critical':400.0,'high':300.0,'normal':200.0,'low':100.0}
 EFFORT={'low':1.0,'medium':2.0,'high':4.0,'unknown':2.5}
 def rank(self,goals,goal_lookup,hardware:Optional[Dict[str,Any]]=None):
  hardware=hardware or {};ram=float(hardware.get('ram_used_percent',hardware.get('ram_usage_percent',0)) or 0);cpu=float(hardware.get('cpu_used_percent',hardware.get('cpu_percent',0)) or 0)
  pressure=max(ram/100,cpu/100);ranked=[]
  for g in goals:
   reasons=[f'owner_priority:{g.priority.value}'];eligible=True
   incomplete=[]
   for dep in g.dependencies:
    d=goal_lookup(dep)
    if not d or getattr(d.status,'value',d.status)!='completed':incomplete.append(dep)
   if incomplete:eligible=False;reasons.append(f'incomplete_dependencies:{incomplete}')
   penalty=self.EFFORT.get(g.estimated_effort,2.5)*pressure*20
   score=self.PRIORITY[g.priority.value]+g.overall_score*40+g.urgency_score*20+g.value_score*20-penalty
   if g.source.value=='owner_directive':score+=50;reasons.append('explicit_owner_directive')
   reasons.append(f'resource_pressure:{pressure:.2f}');ranked.append(GoalAllocation(g.goal_id,round(score,4),eligible,reasons,round(penalty,4)))
  return sorted(ranked,key=lambda x:(x.eligible,x.score),reverse=True)
 def select(self,goal_generator,hardware=None):
  from app.cognition.autonomous_goal_generator import GoalStatus
  goals=goal_generator.list_goals(status=GoalStatus.APPROVED,limit=1000)
  ranked=self.rank(goals,goal_generator.get_goal,hardware)
  selected=next((x for x in ranked if x.eligible),None)
  return {'goal':goal_generator.get_goal(selected.goal_id) if selected else None,'selected':selected.to_dict() if selected else None,'rankings':[x.to_dict() for x in ranked]}
