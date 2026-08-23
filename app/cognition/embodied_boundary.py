"""Evidence-linked boundary between Arena, owner, devices, and environment.

This is a control/sensor topology, not a body or consciousness claim. Interface
ownership and causal control remain unknown unless explicit authority and
observation evidence exist.
"""
from __future__ import annotations
import json, sqlite3, threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now(): return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class BoundaryInterface:
    interface_id: str; kind: str; boundary: str; can_read: bool; can_write: bool
    available: Optional[bool]; evidence: List[str]; updated_at: str
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class BoundaryEvent:
    event_id: str; interface_id: str; event_type: str; actor: str
    execution_id: Optional[str]; authorized: bool; observed: bool
    confidence: float; evidence: List[str]; created_at: str; reason: str
    def to_dict(self): return asdict(self)

class EmbodiedBoundaryModel:
    BOUNDARIES = {"arena_interface", "owner_device", "external_environment", "shared", "unknown"}
    ACTORS = {"arena", "owner", "external", "unknown"}
    def __init__(self, db_path: str | Path):
        self.db_path=str(db_path); Path(self.db_path).parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS boundary_interfaces
            (interface_id TEXT PRIMARY KEY, kind TEXT, boundary TEXT, can_read INTEGER,
             can_write INTEGER, available INTEGER, evidence_json TEXT, updated_at TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS boundary_events
            (event_id TEXT PRIMARY KEY, interface_id TEXT, event_type TEXT, actor TEXT,
             execution_id TEXT, authorized INTEGER, observed INTEGER, confidence REAL,
             evidence_json TEXT, created_at TEXT, reason TEXT)"""); c.commit()

    def register(self, interface_id: str, kind: str, boundary: str, *, can_read=False,
                 can_write=False, available: Optional[bool]=None, evidence: List[str]):
        if boundary not in self.BOUNDARIES or not evidence: raise ValueError("Boundary and evidence are required")
        item=BoundaryInterface(interface_id,kind,boundary,can_read,can_write,available,list(evidence),_now())
        with self._lock, sqlite3.connect(self.db_path) as c:
            c.execute("INSERT OR REPLACE INTO boundary_interfaces VALUES (?,?,?,?,?,?,?,?)",
              (interface_id,kind,boundary,int(can_read),int(can_write),None if available is None else int(available),json.dumps(evidence),item.updated_at)); c.commit()
        return item

    def record_event(self, interface_id: str, event_type: str, *, actor="unknown",
                     execution_id=None, authorized=False, observed=False, evidence=None):
        evidence=[str(x) for x in (evidence or []) if str(x).strip()]
        if actor not in self.ACTORS: raise ValueError("Unknown actor")
        # Arena control requires all three links; an action command alone proves nothing.
        if actor=="arena" and execution_id and authorized and observed and evidence:
            confidence, reason=.9,"Authorized controlled execution produced observed interface evidence."
        elif actor in ("owner","external") and evidence:
            confidence, reason=.9,f"Explicit {actor} provenance was observed."
        else:
            actor="unknown"; confidence=.2
            reason="Interface event lacks authority, execution, or observation evidence."
        event=BoundaryEvent(f"boundary_{uuid4().hex[:16]}",interface_id,event_type,actor,
          execution_id,authorized,observed,confidence,evidence,_now(),reason)
        with self._lock, sqlite3.connect(self.db_path) as c:
            c.execute("INSERT INTO boundary_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (event.event_id,event.interface_id,event.event_type,event.actor,event.execution_id,
               int(event.authorized),int(event.observed),event.confidence,json.dumps(evidence),event.created_at,event.reason)); c.commit()
        return event

    def interfaces(self):
        with sqlite3.connect(self.db_path) as c: rows=c.execute("SELECT * FROM boundary_interfaces ORDER BY interface_id").fetchall()
        return [BoundaryInterface(r[0],r[1],r[2],bool(r[3]),bool(r[4]),None if r[5] is None else bool(r[5]),json.loads(r[6]),r[7]) for r in rows]
    def events(self, limit=100):
        with sqlite3.connect(self.db_path) as c: rows=c.execute("SELECT * FROM boundary_events ORDER BY created_at DESC LIMIT ?",(max(1,min(limit,1000)),)).fetchall()
        return [BoundaryEvent(r[0],r[1],r[2],r[3],r[4],bool(r[5]),bool(r[6]),float(r[7]),json.loads(r[8]),r[9],r[10]) for r in rows]
    def snapshot(self):
        return {"interfaces":[x.to_dict() for x in self.interfaces()],"events":[x.to_dict() for x in self.events(30)],
          "note":"Control/sensor boundary model only; not a biological body or subjective embodiment."}
