"""Explicit OS privilege and process-ownership evidence."""
from __future__ import annotations
import getpass,json,os,platform,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Optional
import psutil

def _now():return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class PrivilegeSnapshot:
 platform:str;username:str;is_elevated:bool;elevation_mechanism:str;evidence:list[str];observed_at:str
 def to_dict(self):return asdict(self)
class PrivilegeModel:
 @staticmethod
 def probe():
  system=platform.system().lower();user=getpass.getuser();evidence=[f'username:{user}',f'platform:{system}']
  if system=='windows':
   try:
    import ctypes;elevated=bool(ctypes.windll.shell32.IsUserAnAdmin());mechanism='uac'
    evidence.append(f'IsUserAnAdmin:{elevated}')
   except Exception:elevated=False;mechanism='uac_unknown';evidence.append('admin_probe_failed')
  else:
   elevated=hasattr(os,'geteuid') and os.geteuid()==0;mechanism='sudo_or_root';evidence.append(f'euid:{os.geteuid() if hasattr(os,"geteuid") else "unknown"}')
  return PrivilegeSnapshot(system,user,elevated,mechanism,evidence,_now())
class ProcessOwnershipStore:
 def __init__(self,path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:c.execute('CREATE TABLE IF NOT EXISTS process_ownership (pid INTEGER PRIMARY KEY,launcher TEXT,task_id TEXT,executable_path TEXT,registered_at TEXT)');c.commit()
 def register_arena_launch(self,pid:int,*,task_id=None,executable_path=''):
  with sqlite3.connect(self.path) as c:c.execute('INSERT OR REPLACE INTO process_ownership VALUES (?,?,?,?,?)',(int(pid),'arena',task_id,executable_path,_now()));c.commit()
  return self.inspect(pid)
 def inspect(self,pid:int):
  try:
   p=psutil.Process(int(pid));username=p.username();exe=p.exe();parent=p.ppid()
  except (psutil.Error,ValueError) as exc:return {'success':False,'verified':False,'error':str(exc)}
  with sqlite3.connect(self.path) as c:r=c.execute('SELECT launcher,task_id,executable_path,registered_at FROM process_ownership WHERE pid=?',(int(pid),)).fetchone()
  launcher=r[0] if r else 'external_or_owner';evidence=[f'psutil_pid:{pid}',f'username:{username}',f'executable:{exe}']
  return {'success':True,'verified':True,'pid':int(pid),'username':username,'executable_path':exe,'parent_pid':parent,'launcher':launcher,'arena_launched':launcher=='arena','task_id':r[1] if r else None,'registered_at':r[3] if r else None,'evidence':evidence}
