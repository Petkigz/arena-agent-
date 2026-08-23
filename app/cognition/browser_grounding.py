"""Persistent browser session/tab grounding without credential assumptions."""
from __future__ import annotations
import json,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional
from uuid import uuid4

def _now():return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class BrowserTab:
 tab_id:str;session_id:str;profile_type:str;url:str;title:str;opener_tab_id:Optional[str]
 owner_takeover:bool;auth_state:str;accessibility_snapshot_id:Optional[str];status:str;evidence:List[str];updated_at:str
 def to_dict(self):return asdict(self)
class BrowserGroundingStore:
 def __init__(self,path:str|Path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:
   c.execute('''CREATE TABLE IF NOT EXISTS browser_tabs
   (tab_id TEXT PRIMARY KEY,session_id TEXT,profile_type TEXT,url TEXT,title TEXT,opener_tab_id TEXT,owner_takeover INTEGER,auth_state TEXT,accessibility_snapshot_id TEXT,status TEXT,evidence_json TEXT,updated_at TEXT)''')
   c.execute('''CREATE TABLE IF NOT EXISTS browser_events
   (event_id TEXT PRIMARY KEY,tab_id TEXT,event_type TEXT,state TEXT,evidence_json TEXT,created_at TEXT)''');c.commit()
 def observe_tab(self,*,session_id,url,title,profile_type='ephemeral',tab_id=None,opener_tab_id=None,accessibility_snapshot_id=None,evidence:List[str]):
  if profile_type not in ('ephemeral','owner_profile','isolated_persistent') or not evidence:raise ValueError('Profile type and evidence required')
  tid=tab_id or f'tab_{uuid4().hex[:16]}';now=_now();existing=self.get(tid)
  tab=BrowserTab(tid,session_id,profile_type,url,title,opener_tab_id,existing.owner_takeover if existing else False,'unknown',accessibility_snapshot_id,'open',evidence,now)
  with sqlite3.connect(self.path) as c:c.execute('INSERT OR REPLACE INTO browser_tabs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(tid,session_id,profile_type,url,title,opener_tab_id,int(tab.owner_takeover),'unknown',accessibility_snapshot_id,'open',json.dumps(evidence),now));c.commit()
  return tab
 def record_event(self,tab_id,event_type,state,*,evidence):
  if not self.get(tab_id) or not evidence:raise ValueError('Known tab and evidence required')
  with sqlite3.connect(self.path) as c:c.execute('INSERT INTO browser_events VALUES (?,?,?,?,?,?)',(f'browser_{uuid4().hex[:16]}',tab_id,event_type,state,json.dumps(evidence),_now()));c.commit()
  return {'success':True,'tab_id':tab_id,'event_type':event_type,'state':state,'evidence':evidence}
 def set_owner_takeover(self,tab_id,active):
  if not self.get(tab_id):raise KeyError(tab_id)
  with sqlite3.connect(self.path) as c:c.execute('UPDATE browser_tabs SET owner_takeover=?,updated_at=? WHERE tab_id=?',(int(active),_now(),tab_id));c.commit()
  return self.get(tab_id)
 def get(self,tid):
  with sqlite3.connect(self.path) as c:r=c.execute('SELECT * FROM browser_tabs WHERE tab_id=?',(tid,)).fetchone()
  return BrowserTab(r[0],r[1],r[2],r[3],r[4],r[5],bool(r[6]),r[7],r[8],r[9],json.loads(r[10]),r[11]) if r else None
 def list(self,session_id=None,limit=200):
  q="SELECT * FROM browser_tabs WHERE status='open'";p=[]
  if session_id:q+=' AND session_id=?';p.append(session_id)
  q+=' ORDER BY updated_at DESC LIMIT ?';p.append(max(1,min(limit,1000)))
  with sqlite3.connect(self.path) as c:rows=c.execute(q,p).fetchall()
  return [BrowserTab(r[0],r[1],r[2],r[3],r[4],r[5],bool(r[6]),r[7],r[8],r[9],json.loads(r[10]),r[11]) for r in rows]
 def resolve(self,*,url=None,title=None,session_id=None):
  tabs=self.list(session_id)
  matches=[t for t in tabs if (not url or t.url==url) and (not title or t.title.lower()==title.lower())]
  if len(matches)!=1:return {'success':False,'ambiguous':len(matches)>1,'error':'No unique browser tab target','candidates':[t.to_dict() for t in matches]}
  if matches[0].owner_takeover:return {'success':False,'owner_takeover':True,'error':'Owner currently controls this tab','target':matches[0].to_dict()}
  return {'success':True,'target':matches[0].to_dict()}
