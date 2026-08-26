"""Verified multi-monitor topology and coordinate transforms."""
from __future__ import annotations
import hashlib,json
from typing import Any,Dict,List
class DisplayTopologyTool:
 _snapshot=None
 @classmethod
 def capture(cls):
  try:
   import mss
   with mss.mss() as sct: raw=sct.monitors[1:]
  except Exception as exc:return {'success':False,'available':False,'error':str(exc),'monitors':[]}
  monitors=[]
  for i,m in enumerate(raw):monitors.append({'display_id':f'display_{i}','x':int(m['left']),'y':int(m['top']),'width':int(m['width']),'height':int(m['height']),'scale':None,'scale_verified':False})
  digest=hashlib.sha256(json.dumps(monitors,sort_keys=True).encode()).hexdigest();cls._snapshot={'monitors':monitors,'digest':digest}
  note='Physical pixel topology observed; DPI scale remains unknown until native scale evidence is supplied.'
  native=cls.probe_native_scale()
  if native is not None:
   # Native evidence applies to the primary monitor (the screen DC source).
   cls.ingest_verified_scale(monitors[0]['display_id'] if monitors else 'display_0',native['scale'],native['evidence'])
   monitors=cls._snapshot['monitors'];digest=cls._snapshot['digest']
   note=f"Native DPI evidence ({native['source']}): primary-monitor scale {native['scale']} verified; other monitors remain unknown."
  return {'success':True,'available':True,'monitors':monitors,'topology_sha256':digest,'native_scale_probe':native,'note':note}

 @staticmethod
 def probe_native_scale():
  """Native Windows DPI evidence via GDI (no dependencies).

  GetDeviceCaps(LOGPIXELSX) on the screen DC gives the system DPI — the
  primary monitor's scale. Returns None wherever evidence cannot be
  observed; scales are never guessed.
  """
  import sys
  if sys.platform!='win32':return None
  try:
   import ctypes
   user32=ctypes.windll.user32;gdi32=ctypes.windll.gdi32
   hdc=user32.GetDC(0)
   try:dpi=int(gdi32.GetDeviceCaps(hdc,88))  # LOGPIXELSX
   finally:user32.ReleaseDC(0,hdc)
   if dpi and dpi>0:
    scale=round(dpi/96.0,4)
    if scale>0:return {'dpi':dpi,'scale':scale,'source':'native_gdi_logpixelsx','evidence':[f'GetDeviceCaps(LOGPIXELSX)={dpi}',f'scale:{scale}']}
  except Exception:return None
  return None

 @classmethod
 def ingest_verified_scale(cls,display_id,scale,evidence):
  if not cls._snapshot:return {'success':False,'error':'Capture display topology first'}
  if not evidence or float(scale)<=0:return {'success':False,'error':'Positive scale and evidence required'}
  for m in cls._snapshot['monitors']:
   if m['display_id']==display_id:m['scale']=float(scale);m['scale_verified']=True;m['scale_evidence']=list(evidence);return {'success':True,'monitor':m}
  return {'success':False,'error':'Display not found'}
 @classmethod
 def transform_window_point(cls,display_id,window_region,local_x,local_y):
  if not cls._snapshot:return {'success':False,'error':'Display topology unavailable'}
  monitor=next((m for m in cls._snapshot['monitors'] if m['display_id']==display_id),None)
  if not monitor:return {'success':False,'error':'Display not found'}
  if not monitor.get('scale_verified'):return {'success':False,'error':'DPI scale is unverified; refusing coordinate transform'}
  x=int(window_region['x']+float(local_x)*monitor['scale']);y=int(window_region['y']+float(local_y)*monitor['scale'])
  inside=monitor['x']<=x<monitor['x']+monitor['width'] and monitor['y']<=y<monitor['y']+monitor['height']
  return {'success':inside,'x':x,'y':y,'display_id':display_id,'inside_display':inside,'topology_sha256':cls._snapshot['digest']}
