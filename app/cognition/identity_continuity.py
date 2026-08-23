"""Restart-aware continuity checks for Arena's functional identity state."""
from __future__ import annotations
import hashlib,json,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,Optional
from uuid import uuid4

def _now(): return datetime.now(timezone.utc).isoformat()
def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

class IdentityContinuityLedger:
    """Detect state discontinuity; never claims a human-like persistent self."""
    def __init__(self,path:str|Path):
        self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS identity_checkpoints (id TEXT PRIMARY KEY, boot_id TEXT, created_at TEXT, state_json TEXT, digest TEXT)"); c.commit()
    def checkpoint(self,state:Dict[str,Any],boot_id:str)->Dict[str,Any]:
        normalized={
          "claim_predicates":sorted(state.get("claim_predicates",[])),
          "active_commitment_sources":sorted(state.get("active_commitment_sources",[])),
          "interface_ids":sorted(state.get("interface_ids",[])),
          "tool_count":int(state.get("tool_count",0)),
          "owner_policy_revision":int(state.get("owner_policy_revision",0)),
        }
        with sqlite3.connect(self.path) as c:
            row=c.execute("SELECT boot_id,state_json,digest FROM identity_checkpoints ORDER BY created_at DESC LIMIT 1").fetchone()
            previous=json.loads(row[1]) if row else None
            issues=[]
            if previous:
                missing=sorted(set(previous["claim_predicates"])-set(normalized["claim_predicates"]))
                if missing: issues.append({"type":"missing_self_claims","items":missing})
                missing_interfaces=sorted(set(previous["interface_ids"])-set(normalized["interface_ids"]))
                if missing_interfaces: issues.append({"type":"missing_interfaces","items":missing_interfaces})
                if normalized["tool_count"]<previous["tool_count"]: issues.append({"type":"capability_count_decreased","before":previous["tool_count"],"after":normalized["tool_count"]})
                if normalized["owner_policy_revision"]<previous["owner_policy_revision"]: issues.append({"type":"owner_policy_revision_rollback"})
            cid=f"identity_{uuid4().hex[:16]}"; digest=_hash(normalized)
            c.execute("INSERT INTO identity_checkpoints VALUES (?,?,?,?,?)",(cid,boot_id,_now(),json.dumps(normalized),digest)); c.commit()
        return {"checkpoint_id":cid,"continuous":not issues,"issues":issues,"state_digest":digest,"previous_exists":previous is not None,
          "note":"Functional state continuity only; not persistence of consciousness or subjective identity."}
