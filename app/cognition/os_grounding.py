"""Persistent evidence links between tasks, applications, processes, and windows."""
from __future__ import annotations
import json,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional
from uuid import uuid4
import psutil

def _now():return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class OSGrounding:
 grounding_id:str;task_id:Optional[str];app_name:str;executable_path:str;pid:int
 window_id:Optional[str];window_title:Optional[str];display_id:Optional[str]
 screen_region:Optional[Dict[str,int]];confidence:float;evidence:List[str];status:str;updated_at:str
 def to_dict(self):return asdict(self)
class OSGroundingStore:
 def __init__(self,path:str|Path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:
   c.execute('''CREATE TABLE IF NOT EXISTS os_groundings
   (grounding_id TEXT PRIMARY KEY,task_id TEXT,app_name TEXT,executable_path TEXT,pid INTEGER,
   window_id TEXT,window_title TEXT,display_id TEXT,screen_region_json TEXT,confidence REAL,
   evidence_json TEXT,status TEXT,updated_at TEXT)''');c.commit()
 def _row(self,r):return OSGrounding(r[0],r[1],r[2],r[3],int(r[4]),r[5],r[6],r[7],json.loads(r[8]) if r[8] else None,float(r[9]),json.loads(r[10]),r[11],r[12])
 def observe_application(self,app_name:str,*,executable_path='',pid:Optional[int]=None,task_id=None):
  matches=[]
  for proc in psutil.process_iter(['pid','name','exe']):
   try:
    info=proc.info; exact=bool(executable_path and info.get('exe') and Path(info['exe']).resolve()==Path(executable_path).resolve())
    named=app_name.lower() in (info.get('name') or '').lower()
    if (pid and info['pid']==int(pid)) or exact or named:matches.append((info,exact))
   except (psutil.Error,OSError):continue
  if not matches:return {'success':False,'verified':False,'error':'No matching running process observed'}
  if len(matches)>1 and not any(x[1] for x in matches):return {'success':False,'verified':False,'ambiguous':True,'candidates':[x[0]['pid'] for x in matches]}
  info,exact=next((x for x in matches if x[1]),matches[0]); evidence=[f"process_pid:{info['pid']}",f"process_name:{info.get('name')}"]
  if exact:evidence.append('executable_path_exact_match')
  g=OSGrounding(f'osg_{uuid4().hex[:16]}',task_id,app_name,executable_path or info.get('exe') or '',int(info['pid']),None,None,None,None,.95 if exact or pid else .75,evidence,'active',_now())
  with sqlite3.connect(self.path) as c:c.execute('INSERT INTO os_groundings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(g.grounding_id,g.task_id,g.app_name,g.executable_path,g.pid,None,None,None,None,g.confidence,json.dumps(g.evidence),g.status,g.updated_at));c.commit()
  return {'success':True,'verified':True,'grounding':g.to_dict()}
 def bind_window(self,grounding_id,*,window_id,title,display_id=None,region=None,evidence:List[str]):
  g=self.get(grounding_id)
  if not g or not evidence:raise ValueError('Process grounding and window evidence required')
  now=_now()
  with sqlite3.connect(self.path) as c:c.execute('UPDATE os_groundings SET window_id=?,window_title=?,display_id=?,screen_region_json=?,confidence=?,evidence_json=?,updated_at=? WHERE grounding_id=?',(str(window_id),title,display_id,json.dumps(region) if region else None,min(1,g.confidence+.04),json.dumps(g.evidence+evidence),now,grounding_id));c.commit()
  return self.get(grounding_id)
 def get(self,i):
  with sqlite3.connect(self.path) as c:r=c.execute('SELECT * FROM os_groundings WHERE grounding_id=?',(i,)).fetchone()
  return self._row(r) if r else None
 def get_by_window(self,window_id):
  with sqlite3.connect(self.path) as c:r=c.execute("SELECT * FROM os_groundings WHERE window_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1",(str(window_id),)).fetchone()
  grounding=self._row(r) if r else None
  return grounding if grounding and psutil.pid_exists(grounding.pid) else None
 def list(self,app_name=None,limit=200):
  q="SELECT * FROM os_groundings WHERE status='active'";p=[]
  if app_name:q+=' AND lower(app_name)=lower(?)';p.append(app_name)
  q+=' ORDER BY updated_at DESC LIMIT ?';p.append(max(1,min(limit,1000)))
  with sqlite3.connect(self.path) as c:rows=c.execute(q,p).fetchall()
  return [self._row(r) for r in rows]
 def resolve_target(self,app_name,*,require_window=False):
  candidates=[g for g in self.list(app_name) if psutil.pid_exists(g.pid) and (not require_window or g.window_id)]
  if len(candidates)!=1:return {'success':False,'ambiguous':len(candidates)>1,'error':'No unique verified OS target','candidates':[g.to_dict() for g in candidates]}
  return {'success':True,'target':candidates[0].to_dict()}
