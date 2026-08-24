"""Semantic OS targeting through accessibility trees, with honest degradation."""
from __future__ import annotations
import json,platform,sqlite3
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional
from uuid import uuid4
from app.config import settings
from app.cognition.os_grounding import OSGroundingStore

def _now():return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class AccessibilityNode:
 node_id:str;snapshot_id:str;interface:str;window_id:Optional[str];role:str;name:str
 bounds:Optional[Dict[str,int]];enabled:bool;evidence:List[str];created_at:str
 def to_dict(self):return asdict(self)
class AccessibilityStore:
 def __init__(self,path=None):
  self.path=str(path or settings.DATA_DIR/'accessibility.db');Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:c.execute('''CREATE TABLE IF NOT EXISTS accessibility_nodes
  (node_id TEXT PRIMARY KEY,snapshot_id TEXT,interface TEXT,window_id TEXT,role TEXT,name TEXT,bounds_json TEXT,enabled INTEGER,evidence_json TEXT,created_at TEXT)''');c.commit()
 def ingest(self,nodes:List[Dict[str,Any]],*,interface,window_id=None,evidence:List[str]):
  if not evidence:raise ValueError('Accessibility evidence required')
  sid=f'a11y_{uuid4().hex[:16]}';created=_now();saved=[]
  with sqlite3.connect(self.path) as c:
   for raw in nodes[:5000]:
    role=str(raw.get('role','')).strip();name=str(raw.get('name','')).strip()
    if not role and not name:continue
    bounds=raw.get('bounds');node=AccessibilityNode(f'node_{uuid4().hex[:16]}',sid,interface,window_id,role,name,bounds,bool(raw.get('enabled',True)),list(evidence),created)
    c.execute('INSERT INTO accessibility_nodes VALUES (?,?,?,?,?,?,?,?,?,?)',(node.node_id,sid,interface,window_id,role,name,json.dumps(bounds) if bounds else None,int(node.enabled),json.dumps(node.evidence),created));saved.append(node)
   c.commit()
  return {'success':True,'snapshot_id':sid,'count':len(saved),'nodes':[n.to_dict() for n in saved]}
 def resolve(self,*,role,name,window_id=None,max_age_seconds=30):
  q='SELECT * FROM accessibility_nodes WHERE lower(role)=lower(?)';p=[role]
  if window_id:q+=' AND window_id=?';p.append(window_id)
  q+=' ORDER BY created_at DESC LIMIT 5000'
  with sqlite3.connect(self.path) as c:rows=c.execute(q,p).fetchall()
  def node(r):return AccessibilityNode(r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6]) if r[6] else None,bool(r[7]),json.loads(r[8]),r[9])
  candidates=[node(r) for r in rows];exact=[n for n in candidates if n.name.lower()==name.lower()]
  selected=exact or [n for n in candidates if name.lower() in n.name.lower()]
  now=datetime.now(timezone.utc)
  selected=[n for n in selected if (now-datetime.fromisoformat(n.created_at)).total_seconds()<=max(1,int(max_age_seconds))]
  # Only nodes from the newest matching snapshot may compete.
  if selected:
   newest=selected[0].snapshot_id;selected=[n for n in selected if n.snapshot_id==newest]
  if len(selected)!=1:return {'success':False,'ambiguous':len(selected)>1,'error':'No unique semantic accessibility target','candidates':[n.to_dict() for n in selected]}
  return {'success':True,'target':selected[0].to_dict()}
class AccessibilityControlTool:
 store=AccessibilityStore()
 os_grounding=OSGroundingStore(settings.DATA_DIR/'os_grounding.db')
 @classmethod
 def capture_desktop(cls,window_id=None,max_nodes=1000):
  import platform
  system=platform.system().lower();nodes=[]
  try:
   if system=='linux':
    import pyatspi # type: ignore
    root=pyatspi.Registry.getDesktop(0)
    def walk(item):
     if len(nodes)>=max(1,min(int(max_nodes),5000)):return
     try:
      role=item.getRoleName();name=item.name or '';bounds=None
      try:
       ext=item.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
       bounds={'x':int(ext.x),'y':int(ext.y),'width':int(ext.width),'height':int(ext.height)}
      except Exception:pass
      nodes.append({'role':role,'name':name,'bounds':bounds,'enabled':True})
      for index in range(item.childCount):walk(item.getChildAtIndex(index))
     except Exception:return
    walk(root);engine='linux_atspi'
   elif system=='windows':
    import uiautomation as auto # type: ignore
    root=auto.GetRootControl()
    def walk(item):
     if len(nodes)>=max(1,min(int(max_nodes),5000)):return
     try:
      rect=item.BoundingRectangle
      bounds={'x':int(rect.left),'y':int(rect.top),'width':int(rect.right-rect.left),'height':int(rect.bottom-rect.top)} if rect else None
      nodes.append({'role':str(item.ControlTypeName or ''),'name':str(item.Name or ''),'bounds':bounds,'enabled':bool(item.IsEnabled)})
      for child in item.GetChildren():walk(child)
     except Exception:return
    walk(root);engine='windows_uia'
   else:return {'success':False,'available':False,'error':'Native accessibility capture not integrated for this platform'}
  except ImportError as exc:return {'success':False,'available':False,'error':str(exc),'nodes':[]}
  result=cls.store.ingest(nodes,interface=engine,window_id=window_id,evidence=[f'{engine} native accessibility tree'])
  result.update({'available':True,'engine':engine});return result
 @classmethod
 def status(cls):
  system=platform.system().lower();engine='windows_uia' if system=='windows' else 'linux_atspi' if system=='linux' else 'macos_accessibility'
  try:
   if system=='windows':import uiautomation # type: ignore # noqa
   elif system=='linux':import pyatspi # type: ignore # noqa
   else:raise ImportError('native adapter not integrated')
   return {'success':True,'available':True,'engine':engine}
  except ImportError as exc:return {'success':False,'available':False,'engine':engine,'error':str(exc)}
 @classmethod
 def ingest_snapshot(cls,nodes,interface='browser_accessibility',window_id=None,evidence=None):
  return cls.store.ingest(nodes,interface=interface,window_id=window_id,evidence=evidence or ['owner_or_browser_accessibility_snapshot'])
 @classmethod
 def resolve_target(cls,role,name,window_id=None,max_age_seconds=30):return cls.store.resolve(role=role,name=name,window_id=window_id,max_age_seconds=max_age_seconds)
 @classmethod
 def activate_target(cls,role,name,window_id=None):
  from datetime import datetime,timezone
  resolved=cls.resolve_target(role,name,window_id,max_age_seconds=10)
  if not resolved.get('success'):return resolved
  target=resolved['target'];bounds=target.get('bounds')
  if not bounds:return {'success':False,'available':False,'error':'Semantic target has no observed screen bounds','target':target}
  if not target.get('window_id'):return {'success':False,'error':'Semantic activation requires a grounded window ID','target':target}
  # Every raw-coordinate activation must bind a live process/window grounding.
  grounding=cls.os_grounding.get_by_window(target['window_id'])
  if not grounding:return {'success':False,'error':'Window/process grounding is missing or stale','target':target}
  from app.tools.display_topology import DisplayTopologyTool
  topology=DisplayTopologyTool.capture()
  if not topology.get('success'):return {'success':False,'error':'Display topology unavailable for grounded activation','target':target}
  # The accessibility snapshot is the immediate target-window observation.
  snapshot_age=(datetime.now(timezone.utc)-datetime.fromisoformat(target['created_at'])).total_seconds()
  fresh_observation={'age_seconds':snapshot_age,'evidence':[f"accessibility_snapshot:{target['snapshot_id']}",f"node:{target['node_id']}"]}
  from app.tools.deep_os_controller import DeepOSController
  click_x=int(bounds['x']+bounds['width']/2);click_y=int(bounds['y']+bounds['height']/2)
  result=DeepOSController.mouse_click(
   click_x,click_y,
   grounding_id=grounding.grounding_id,
   expected_topology_sha256=topology['topology_sha256'],
   fresh_observation=fresh_observation,
  )
  return {'success':bool(result.get('success')),'target':target,'activation_result':result,'semantic_target_verified':True}
