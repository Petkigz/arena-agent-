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
    def __init__(self,path:str|Path,owner_decisions=None):
        self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        self.owner_decisions=owner_decisions
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS identity_checkpoints (id TEXT PRIMARY KEY, boot_id TEXT, created_at TEXT, state_json TEXT, digest TEXT)"); c.commit()
            try:
                c.execute("ALTER TABLE identity_checkpoints ADD COLUMN owner_decision_id TEXT"); c.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
    def checkpoint(self,state:Dict[str,Any],boot_id:str,expected_change_types:Optional[list[str]]=None,owner_decision_id:Optional[str]=None)->Dict[str,Any]:
        # Expected changes are owner-authority claims: they are only honored
        # when bound to a valid, unused, unrevoked owner decision whose payload
        # authorizes exactly the claimed change types. Without that binding the
        # claim fails closed — the changes stay recorded as findings instead of
        # being silently excused.
        claimed=list(dict.fromkeys(str(t) for t in (expected_change_types or [])))
        validation:Optional[Dict[str,Any]]=None
        honored:list[str]=[]
        if claimed:
            if not owner_decision_id:
                validation={"valid":False,"decision_id":None,"reasons":["missing_owner_decision"],
                            "note":"expected_change_types requires a signed owner decision; failing closed."}
            elif self.owner_decisions is None:
                validation={"valid":False,"decision_id":owner_decision_id,"reasons":["decision_store_unavailable"],
                            "note":"No owner-decision store is configured; expected changes cannot be verified."}
            else:
                validation=self.owner_decisions.validate(
                    owner_decision_id,
                    decision_type="expected_identity_change",
                    claimed_change_types=claimed,
                )
            if validation.get("valid"):
                honored=claimed
        normalized={
          "claim_predicates":sorted(state.get("claim_predicates",[])),
          "claim_digests":dict(sorted((state.get("claim_digests") or {}).items())),
          "active_commitment_sources":sorted(state.get("active_commitment_sources",[])),
          "interface_ids":sorted(state.get("interface_ids",[])),
          "interface_availability":dict(sorted((state.get("interface_availability") or {}).items())),
          "provider_model":state.get("provider_model"),
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
                changed_claims=sorted(k for k,v in previous.get("claim_digests",{}).items() if k in normalized["claim_digests"] and normalized["claim_digests"][k]!=v)
                if changed_claims:issues.append({"type":"changed_self_claim_values","items":changed_claims})
                missing_commitments=sorted(set(previous.get("active_commitment_sources",[]))-set(normalized["active_commitment_sources"]))
                if missing_commitments:issues.append({"type":"missing_active_commitments","items":missing_commitments})
                missing_interfaces=sorted(set(previous["interface_ids"])-set(normalized["interface_ids"]))
                if missing_interfaces: issues.append({"type":"missing_interfaces","items":missing_interfaces})
                changed_interfaces=sorted(k for k,v in previous.get("interface_availability",{}).items() if k in normalized["interface_availability"] and normalized["interface_availability"][k]!=v)
                if changed_interfaces:issues.append({"type":"interface_availability_changed","items":changed_interfaces})
                if previous.get("provider_model")!=normalized.get("provider_model"):issues.append({"type":"provider_model_changed","before":previous.get("provider_model"),"after":normalized.get("provider_model")})
                if normalized["tool_count"]<previous["tool_count"]: issues.append({"type":"capability_count_decreased","before":previous["tool_count"],"after":normalized["tool_count"]})
                if normalized["owner_policy_revision"]<previous["owner_policy_revision"]: issues.append({"type":"owner_policy_revision_rollback"})
            cid=f"identity_{uuid4().hex[:16]}"; digest=_hash(normalized)
            c.execute("INSERT INTO identity_checkpoints VALUES (?,?,?,?,?,?)",(cid,boot_id,_now(),json.dumps(normalized),digest,owner_decision_id if validation and validation.get("valid") else None)); c.commit()
        expected_types=set(honored);expected=[item for item in issues if item.get('type') in expected_types];unexpected=[item for item in issues if item.get('type') not in expected_types]
        return {"checkpoint_id":cid,"continuous":not unexpected,"issues":unexpected,"expected_changes":expected,"expected_change_validation":validation,"owner_decision_id":owner_decision_id if validation and validation.get("valid") else None,"state_changed":bool(issues),"state_digest":digest,"previous_exists":previous is not None,
          "note":"Functional state continuity only; expected changes are honored only when bound to a valid single-use owner decision. This is not persistence of consciousness or subjective identity."}
