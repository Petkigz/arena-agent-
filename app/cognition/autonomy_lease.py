"""Atomic SQLite lease preventing overlapping autonomous cycles."""
from __future__ import annotations
import sqlite3
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4

def _now():return datetime.now(timezone.utc)
class AutonomyCycleLease:
 def __init__(self,path):
  self.path=str(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:c.execute('CREATE TABLE IF NOT EXISTS autonomy_leases (lease_name TEXT PRIMARY KEY,holder TEXT,acquired_at TEXT,expires_at TEXT)');c.commit()
 def acquire(self,lease_name='periodic_cycle',ttl_seconds=900):
  holder=f'lease_{uuid4().hex[:16]}';now=_now();expires=now+timedelta(seconds=max(30,int(ttl_seconds)))
  with sqlite3.connect(self.path,timeout=10,isolation_level=None) as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT holder,expires_at FROM autonomy_leases WHERE lease_name=?',(lease_name,)).fetchone()
   if row:
    try:active=datetime.fromisoformat(row[1])>now
    except ValueError:active=False
    if active:c.execute('ROLLBACK');return {'acquired':False,'holder':row[0],'reason':'Another autonomous cycle holds the lease'}
   c.execute('INSERT OR REPLACE INTO autonomy_leases VALUES (?,?,?,?)',(lease_name,holder,now.isoformat(),expires.isoformat()));c.execute('COMMIT')
  return {'acquired':True,'holder':holder,'lease_name':lease_name,'expires_at':expires.isoformat()}
 def heartbeat(self,holder,lease_name='periodic_cycle',ttl_seconds=900):
  expires=_now()+timedelta(seconds=max(30,int(ttl_seconds)))
  with sqlite3.connect(self.path) as c:r=c.execute('UPDATE autonomy_leases SET expires_at=? WHERE lease_name=? AND holder=?',(expires.isoformat(),lease_name,holder));c.commit();return r.rowcount==1
 def release(self,holder,lease_name='periodic_cycle'):
  with sqlite3.connect(self.path) as c:r=c.execute('DELETE FROM autonomy_leases WHERE lease_name=? AND holder=?',(lease_name,holder));c.commit();return r.rowcount==1
