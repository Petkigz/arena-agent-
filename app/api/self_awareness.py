"""Evidence-linked functional self-awareness API.

Extracted verbatim from app/main.py (composition refactor step 10c). Claims
require evidence; narration never creates self-knowledge; no consciousness or
subjective-identity claims are made or implied by these surfaces.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

router = APIRouter()

# ── request models ──────────────────────────────────────────────────────────
class IdentityCheckpointRequest(BaseModel):
    expected_change_types: List[str] = Field(default_factory=list)
    owner_change_evidence: List[str] = Field(default_factory=list)
    owner_decision_id: Optional[str] = Field(None, min_length=1, max_length=100)

class ExplicitCommitmentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_id: str = Field(min_length=1, max_length=200)


class RecoveryDecisionRequest(BaseModel):
    status: str
    note: str = ""


class RecoveryActionRequest(BaseModel):
    action_type: str = Field(min_length=1)
    payload: Dict[str, Any]
    reason: str = Field(min_length=1)



# ── endpoints ───────────────────────────────────────────────────────────────
@router.get("/self-awareness")
def self_awareness_endpoint(refresh: bool = Query(True)):
    """Return evidence-backed self-claims, agency records, and performance."""
    from dataclasses import asdict
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance()
    snapshot = (
        runtime.refresh_self_knowledge()["snapshot"]
        if refresh else runtime.self_knowledge.snapshot()
    )
    return {
        "success": True,
        "self_knowledge": snapshot,
        "performance_self_model": asdict(runtime.self_model.generate_report()),
        "competence_calibration": runtime.confidence_calibrator.longitudinal_report(),
        "disclaimer": (
            "Functional evidence-linked self-knowledge only; this does not "
            "demonstrate consciousness, sentience, emotion, or subjective experience."
        ),
    }


@router.get("/self-awareness/claims/history")
def self_claim_history_endpoint(
    predicate: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    from app.cognition.runtime import CognitiveRuntime

    claims = CognitiveRuntime.get_instance().self_knowledge.history(predicate, limit)
    return {"success": True, "claims": [claim.to_dict() for claim in claims]}


@router.get("/self-awareness/belief-revisions")
def self_belief_revisions_endpoint(
    predicate: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    from app.cognition.runtime import CognitiveRuntime

    revisions = CognitiveRuntime.get_instance().self_knowledge.recent_revisions(
        predicate, limit
    )
    return {"success": True, "revisions": [item.to_dict() for item in revisions]}


@router.get("/self-awareness/agency")
def self_agency_history_endpoint(limit: int = Query(100, ge=1, le=1000)):
    from app.cognition.runtime import CognitiveRuntime

    records = CognitiveRuntime.get_instance().self_knowledge.recent_attributions(limit)
    return {"success": True, "attributions": [record.to_dict() for record in records]}


@router.post("/self-awareness/identity-checkpoint")
def identity_continuity_checkpoint_endpoint(req:Optional[IdentityCheckpointRequest]=None):
    from app.cognition.runtime import CognitiveRuntime
    runtime=CognitiveRuntime.get_instance();req=req or IdentityCheckpointRequest()
    runtime.refresh_self_knowledge(); runtime.refresh_embodied_boundary(); runtime.refresh_commitments()
    continuity=runtime.checkpoint_identity_continuity(req.expected_change_types,owner_decision_id=req.owner_decision_id)
    recovery=None
    if not continuity["continuous"]:
        recovery=runtime.self_recovery.save(continuity,owner_evidence=req.owner_change_evidence).to_dict()
    return {"success":True,"continuity":continuity,"recovery_assessment":recovery}


@router.get("/self-awareness/recovery")
def list_recovery_assessments_endpoint(status_filter: Optional[str]=Query(None,alias="status"),limit:int=Query(200,ge=1,le=1000)):
    from app.cognition.runtime import CognitiveRuntime
    items=CognitiveRuntime.get_instance().self_recovery.list(status_filter,limit)
    return {"success":True,"assessments":[item.to_dict() for item in items]}


@router.post("/self-awareness/recovery/{assessment_id}/decision")
def decide_recovery_assessment_endpoint(assessment_id:str,req:RecoveryDecisionRequest):
    from app.cognition.runtime import CognitiveRuntime
    try: item=CognitiveRuntime.get_instance().self_recovery.decide(assessment_id,req.status,req.note)
    except KeyError as exc: raise HTTPException(status_code=404,detail="Recovery assessment not found") from exc
    except ValueError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    return {"success":True,"assessment":item.to_dict()}


@router.post("/self-awareness/recovery/{assessment_id}/request-action-approval")
def request_recovery_action_endpoint(assessment_id:str,req:RecoveryActionRequest):
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.approval_store import approval_store
    runtime=CognitiveRuntime.get_instance()
    if not any(item.assessment_id==assessment_id for item in runtime.self_recovery.list(limit=1000)):
        raise HTTPException(status_code=404,detail="Recovery assessment not found")
    approval=approval_store.add(f"recovery:{assessment_id}",req.action_type,req.payload,req.reason,goal_text=f"Recover from identity discontinuity {assessment_id}")
    item=runtime.self_recovery.mark_action_requested(assessment_id,f"approval:{approval.action_id}")
    return {"success":True,"assessment":item.to_dict(),"approval":approval.to_dict(),"executed":False}


@router.get("/self-awareness/embodied-boundary")
def embodied_boundary_endpoint(refresh: bool = Query(True)):
    from app.cognition.runtime import CognitiveRuntime
    runtime = CognitiveRuntime.get_instance()
    if refresh:
        runtime.refresh_embodied_boundary()
    return {"success": True, "boundary": runtime.embodied_boundary.snapshot()}


@router.get("/self-awareness/commitments")
def self_commitments_endpoint(
    refresh: bool = Query(True),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(500, ge=1, le=2000),
):
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance()
    if refresh:
        runtime.refresh_commitments()
    try:
        commitments = runtime.commitments.list(status_filter, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "commitments": [item.to_dict() for item in commitments]}


@router.post("/self-awareness/commitments")
def create_explicit_commitment_endpoint(req: ExplicitCommitmentRequest):
    """Record an explicit owner commitment; model prose cannot call this implicitly."""
    from app.cognition.runtime import CognitiveRuntime

    commitment = CognitiveRuntime.get_instance().commitments.upsert(
        req.title, source_type="explicit_owner", source_id=req.source_id,
        status="active", evidence=[f"owner_api:{req.source_id}"],
    )
    return {"success": True, "commitment": commitment.to_dict()}


@router.get("/self-awareness/introspection/{trace_id}")
def grounded_introspection_endpoint(trace_id: str):
    from app.cognition.commitment_ledger import GroundedIntrospection

    result = GroundedIntrospection.explain_trace(settings.DB_PATH, trace_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Trace not found"))
    return result
