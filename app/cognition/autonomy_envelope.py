"""Owner-defined, persistent operating envelope for autonomous cycles."""
from __future__ import annotations
import json, threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

@dataclass
class AutonomyEnvelope:
    cycles_enabled: bool=True
    max_goal_executions_per_cycle: int=3
    max_project_steps_per_cycle: int=3
    max_projects_per_cycle: int=3
    max_cycle_seconds: int=300
    minimum_seconds_between_cycles: int=300
    max_consecutive_failures: int=2
    def normalized(self):
        self.max_goal_executions_per_cycle=max(0,min(20,int(self.max_goal_executions_per_cycle)))
        self.max_project_steps_per_cycle=max(0,min(20,int(self.max_project_steps_per_cycle)))
        self.max_projects_per_cycle=max(0,min(20,int(self.max_projects_per_cycle)))
        self.max_cycle_seconds=max(10,min(3600,int(self.max_cycle_seconds)))
        self.minimum_seconds_between_cycles=max(0,min(86400,int(self.minimum_seconds_between_cycles)))
        self.max_consecutive_failures=max(0,min(20,int(self.max_consecutive_failures))); return self
    def to_dict(self): return asdict(self)

class AutonomyEnvelopeStore:
    def __init__(self,path:str|Path):
        self.path=Path(path); self._lock=threading.RLock(); self._policy=self._load()
    def _load(self):
        if not self.path.exists(): return AutonomyEnvelope()
        try:
            raw=json.loads(self.path.read_text()); fields=AutonomyEnvelope.__dataclass_fields__
            return AutonomyEnvelope(**{k:v for k,v in raw.items() if k in fields}).normalized()
        except Exception: return AutonomyEnvelope(cycles_enabled=False)
    def get(self): return AutonomyEnvelope(**self._policy.to_dict()).normalized()
    def update(self,patch:Dict[str,Any]):
        unknown=set(patch)-set(AutonomyEnvelope.__dataclass_fields__)
        if unknown: raise ValueError(f"Unknown autonomy envelope fields: {sorted(unknown)}")
        with self._lock:
            data=self._policy.to_dict(); data.update(patch); self._policy=AutonomyEnvelope(**data).normalized()
            self.path.parent.mkdir(parents=True,exist_ok=True); temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self._policy.to_dict(),indent=2)); temp.replace(self.path); return self.get()
    def evaluate(self,*,owner_policy:Any,last_started_at:Optional[str]=None,now:Optional[datetime]=None):
        p=self.get(); now=now or datetime.now(timezone.utc); reasons=[]
        if not p.cycles_enabled: reasons.append('Autonomous cycles disabled by owner envelope')
        if getattr(owner_policy,'paused',False): reasons.append('Owner emergency pause active')
        if last_started_at and p.minimum_seconds_between_cycles:
            try:
                elapsed=(now-datetime.fromisoformat(last_started_at)).total_seconds()
                if elapsed<p.minimum_seconds_between_cycles: reasons.append('Autonomy cooldown active')
            except ValueError: reasons.append('Previous cycle timestamp invalid')
        mode=getattr(getattr(owner_policy,'mode',None),'value',getattr(owner_policy,'mode',''))
        execution_allowed=not reasons and mode not in ('observe_only','suggest_only')
        return {'cycle_allowed':not reasons,'execution_allowed':execution_allowed,
          'reasons':reasons or ([f'Control mode {mode} permits recommendations but not execution'] if not execution_allowed else []),
          'policy':p.to_dict()}
