"""Owner-control autonomy API: goal queue, schedules, run timelines,
preemption reconciliation, concurrency budget, and signed owner decisions.

Extracted verbatim from app/main.py (composition refactor step 10a). These
endpoints keep the stage separation invariants: decisions authorize planning
only; execution is always a separate explicit action.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

router = APIRouter()

# ── request models ──────────────────────────────────────────────────────────
class ScheduledDirectiveRequest(BaseModel):
    title: str = Field(min_length=1,max_length=300)
    run_at: str
    description: str = Field(default="",max_length=2000)
    priority: str = "normal"
    recurrence: str = "none"
    missed_policy: str = "run_once"
    approve_for_planning: bool = True
    timezone_name: str = "UTC"

class ScheduleStatusRequest(BaseModel):
    status: str

class PreemptionRequest(BaseModel):
    execution_id: str = Field(min_length=1)
    urgent_goal_id: str = Field(min_length=1)
    interrupted_goal_id: Optional[str] = None
    plan_id: Optional[str] = None
    reason: str = "Urgent owner priority"

class OwnerAutonomousGoalRequest(BaseModel):
    title: str = Field(min_length=1,max_length=300)
    description: str = Field(default="",max_length=2000)
    priority: str = "normal"
    approve_for_planning: bool = True

class AutonomousGoalDecisionRequest(BaseModel):
    approved: bool

class AutonomousGoalPriorityRequest(BaseModel):
    priority: str

class AutonomyEnvelopeUpdate(BaseModel):
    cycles_enabled: Optional[bool] = None
    limits_enabled: Optional[bool] = None
    max_goal_executions_per_cycle: Optional[int] = Field(None, ge=0, le=20)
    max_project_steps_per_cycle: Optional[int] = Field(None, ge=0, le=20)
    max_projects_per_cycle: Optional[int] = Field(None, ge=0, le=20)
    max_cycle_seconds: Optional[int] = Field(None, ge=10, le=3600)
    minimum_seconds_between_cycles: Optional[int] = Field(None, ge=0, le=86400)
    max_consecutive_failures: Optional[int] = Field(None, ge=0, le=20)

class ConcurrencyBudgetUpdate(BaseModel):
    """Owner concurrency budget override. max_workers=null resets to measured defaults."""
    enabled: Optional[bool] = None
    max_workers: Optional[int] = Field(None, ge=1, le=256)

class OwnerDecisionRequest(BaseModel):
    decision_type: str = Field(default="expected_identity_change")
    expected_change_types: List[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)


class QuestionAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=20)  # approve | deny | observe
    note: str = Field(default="", max_length=2000)


# ── endpoints ───────────────────────────────────────────────────────────────
@router.get("/owner-control/autonomy-envelope")
def get_autonomy_envelope_endpoint():
    from app.cognition.runtime import CognitiveRuntime
    return {"success": True, "envelope": CognitiveRuntime.get_instance().autonomy_envelope.get().to_dict()}

@router.put("/owner-control/autonomy-envelope")
def update_autonomy_envelope_endpoint(req: AutonomyEnvelopeUpdate):
    from app.cognition.runtime import CognitiveRuntime
    policy=CognitiveRuntime.get_instance().autonomy_envelope.update(req.model_dump(exclude_none=True))
    return {"success": True, "envelope": policy.to_dict(), "note": "Limits constrain future cycles and grant no new authority."}

@router.get("/owner-control/concurrency-budget")
def get_concurrency_budget_endpoint():
    from app.utils.concurrency_governor import ConcurrencyGovernor
    measurement = ConcurrencyGovernor.measure()
    return {
        "success": True,
        "budget": measurement,
        "recent_receipts": ConcurrencyGovernor.recent_receipts(limit=10),
        "note": "Worker grants are measured from live RAM/CPU pressure; the owner override cannot bypass critical pressure gates.",
    }

@router.put("/owner-control/concurrency-budget")
def update_concurrency_budget_endpoint(req: ConcurrencyBudgetUpdate):
    from app.utils.concurrency_governor import concurrency_override_store, ConcurrencyGovernor
    try:
        override = concurrency_override_store.update(req.model_dump(exclude_unset=True))
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    measurement = ConcurrencyGovernor.measure()
    return {
        "success": True,
        "override": override.to_dict(),
        "budget": measurement,
        "note": "The owner budget is clamped to physical thread count and collapses to serial under critical RAM/CPU pressure.",
    }

@router.get("/owner-control/concurrency-budget/receipts")
def get_concurrency_receipts_endpoint(limit: int = 20):
    from app.utils.concurrency_governor import ConcurrencyGovernor
    return {"success": True, "receipts": ConcurrencyGovernor.recent_receipts(limit=max(1, min(limit, 200)))}

@router.post("/owner-control/autonomous-goals")
def create_owner_autonomous_goal_endpoint(req:OwnerAutonomousGoalRequest):
    from app.cognition.autonomous_goal_generator import AutonomousGoal,GoalPriority,GoalSource,IntrinsicMotivation
    from app.cognition.runtime import CognitiveRuntime
    try: priority=GoalPriority(req.priority)
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    runtime=CognitiveRuntime.get_instance()
    goal=AutonomousGoal(title=req.title,description=req.description,source=GoalSource.OWNER_DIRECTIVE,motivation=IntrinsicMotivation.HELPFULNESS,priority=priority,user_benefit="Explicit owner directive")
    runtime.goal_generator.add_goal(goal); runtime.goal_generator.evaluate_goal(goal)
    if req.approve_for_planning: goal=runtime.goal_generator.owner_decide_goal(goal.goal_id,True)
    return {"success":True,"goal":goal.to_dict(),"execution_authorized":False}

@router.post("/owner-control/autonomy-schedule")
def create_autonomy_schedule_endpoint(req:ScheduledDirectiveRequest):
    from app.cognition.runtime import CognitiveRuntime
    try:item=CognitiveRuntime.get_instance().autonomy_schedule.create(req.title,req.run_at,description=req.description,priority=req.priority,recurrence=req.recurrence,missed_policy=req.missed_policy,approve_for_planning=req.approve_for_planning,timezone_name=req.timezone_name)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return {"success":True,"schedule":item.to_dict(),"execution_authorized":False}

@router.get("/owner-control/autonomy-schedule")
def list_autonomy_schedule_endpoint(status_filter:Optional[str]=Query(None,alias="status"),limit:int=Query(500,ge=1,le=2000)):
    from app.cognition.runtime import CognitiveRuntime
    return {"success":True,"schedule":[x.to_dict() for x in CognitiveRuntime.get_instance().autonomy_schedule.list(status_filter,limit)]}

@router.post("/owner-control/autonomy-schedule/{schedule_id}/status")
def update_autonomy_schedule_status_endpoint(schedule_id:str,req:ScheduleStatusRequest):
    from app.cognition.runtime import CognitiveRuntime
    try:item=CognitiveRuntime.get_instance().autonomy_schedule.set_status(schedule_id,req.status)
    except KeyError as exc:raise HTTPException(status_code=404,detail="Schedule not found") from exc
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return {"success":True,"schedule":item.to_dict()}

@router.get("/owner-control/autonomy-runs/{cycle_id}/timeline")
def autonomy_cycle_timeline_endpoint(cycle_id:str,limit:int=Query(2000,ge=1,le=5000)):
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.autonomy_run_ledger import attach_cycle_links
    runtime=CognitiveRuntime.get_instance()
    events=runtime.autonomy_run_ledger.list(cycle_id=cycle_id,limit=limit)
    timeline=attach_cycle_links(list(reversed(events)),commitment_ledger=runtime.commitments,recovery_store=runtime.self_recovery)
    return {"success":True,"cycle_id":cycle_id,"timeline":timeline,"note":"commitment_links/recovery_assessment_ids are read-time joins over immutable events; recovery links mark temporal co-occurrence, not causation."}

@router.get("/owner-control/autonomy-runs")
def list_autonomy_run_events_endpoint(cycle_id:Optional[str]=Query(None),goal_id:Optional[str]=Query(None),limit:int=Query(500,ge=1,le=2000)):
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.autonomy_run_ledger import attach_cycle_links
    runtime=CognitiveRuntime.get_instance()
    events=runtime.autonomy_run_ledger.list(cycle_id=cycle_id,goal_id=goal_id,limit=limit)
    return {"success":True,"events":attach_cycle_links(events,commitment_ledger=runtime.commitments,recovery_store=runtime.self_recovery)}

@router.get("/owner-control/autonomous-goals/allocation-preview")
def preview_autonomous_goal_allocation_endpoint():
    from app.cognition.runtime import CognitiveRuntime
    runtime=CognitiveRuntime.get_instance()
    result=runtime.autonomy_allocator.select(runtime.goal_generator,runtime.hardware_self_model)
    return {"success":True,"selected":result["selected"],"rankings":result["rankings"],"note":"Preview only; no goal or action executed."}

@router.get("/owner-control/autonomous-goals")
def list_autonomous_goal_queue_endpoint(status_filter: Optional[str]=Query(None,alias="status"),limit:int=Query(100,ge=1,le=1000)):
    from app.cognition.autonomous_goal_generator import GoalStatus
    from app.cognition.runtime import CognitiveRuntime
    try: status=GoalStatus(status_filter) if status_filter else None
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    goals=CognitiveRuntime.get_instance().goal_generator.list_goals(status=status,limit=limit)
    return {"success":True,"goals":[goal.to_dict() for goal in goals],"note":"Goal approval permits planning only; actions remain separately gated."}

@router.post("/owner-control/autonomous-goals/{goal_id}/decision")
def decide_autonomous_goal_endpoint(goal_id:str,req:AutonomousGoalDecisionRequest):
    from app.cognition.runtime import CognitiveRuntime
    try: goal=CognitiveRuntime.get_instance().goal_generator.owner_decide_goal(goal_id,req.approved)
    except ValueError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    if not goal: raise HTTPException(status_code=404,detail="Autonomous goal not found")
    return {"success":True,"goal":goal.to_dict(),"execution_authorized":False}

@router.post("/owner-control/autonomous-goals/{goal_id}/defer")
def defer_autonomous_goal_endpoint(goal_id:str):
    from app.cognition.runtime import CognitiveRuntime
    try:goal=CognitiveRuntime.get_instance().goal_generator.owner_defer_goal(goal_id)
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    if not goal:raise HTTPException(status_code=404,detail="Autonomous goal not found")
    return {"success":True,"goal":goal.to_dict(),"executed":False}

@router.put("/owner-control/autonomous-goals/{goal_id}/priority")
def prioritize_autonomous_goal_endpoint(goal_id:str,req:AutonomousGoalPriorityRequest):
    from app.cognition.runtime import CognitiveRuntime
    try: goal=CognitiveRuntime.get_instance().goal_generator.owner_set_priority(goal_id,req.priority)
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    if not goal: raise HTTPException(status_code=404,detail="Autonomous goal not found")
    return {"success":True,"goal":goal.to_dict()}

@router.post("/owner-control/autonomous-goals/execute-next")
def execute_next_autonomous_goal_endpoint():
    from app.cognition.runtime import CognitiveRuntime
    runtime=CognitiveRuntime.get_instance()
    lease=runtime.autonomy_cycle_lease.acquire(ttl_seconds=900)
    if not lease.get("acquired"):
        raise HTTPException(status_code=409,detail=lease.get("reason","Autonomy lease unavailable"))
    try:
        plan=runtime.execute_autonomous_goal()
        return {"success":plan is not None,"plan":plan.to_dict() if plan else None,"note":"Every plan action still passes Owner Control and ActionGate."}
    finally:
        runtime.autonomy_cycle_lease.release(lease["holder"])

@router.post("/owner-control/preemptions")
def create_autonomy_preemption_endpoint(req:PreemptionRequest):
    from app.cognition.execution_control import execution_control_registry
    from app.cognition.runtime import CognitiveRuntime
    runtime=CognitiveRuntime.get_instance()
    urgent=runtime.goal_generator.owner_set_priority(req.urgent_goal_id,"critical")
    if urgent is None:raise HTTPException(status_code=404,detail="Urgent goal not found")
    record=execution_control_registry.request_cancel(req.execution_id)
    if record is None:raise HTTPException(status_code=404,detail="Execution not found")
    receipt=runtime.autonomy_preemptions.create(req.execution_id,req.urgent_goal_id,interrupted_goal_id=req.interrupted_goal_id,plan_id=req.plan_id,reason=req.reason)
    return {"success":True,"preemption":receipt.to_dict(),"note":"Cancellation requested; resume is separate and never repeats work automatically."}

@router.get("/owner-control/preemptions")
def list_autonomy_preemptions_endpoint(limit:int=Query(200,ge=1,le=1000)):
    from app.cognition.runtime import CognitiveRuntime
    return {"success":True,"preemptions":[x.to_dict() for x in CognitiveRuntime.get_instance().autonomy_preemptions.list(limit)]}

@router.post("/owner-control/preemptions/{preemption_id}/refresh")
def refresh_autonomy_preemption_endpoint(preemption_id:str):
    from app.cognition.execution_control import execution_control_registry
    from app.cognition.runtime import CognitiveRuntime
    store=CognitiveRuntime.get_instance().autonomy_preemptions; item=store.get(preemption_id)
    if not item:raise HTTPException(status_code=404,detail="Preemption not found")
    execution=execution_control_registry.get(item.execution_id)
    if not execution:raise HTTPException(status_code=404,detail="Execution not found")
    return {"success":True,"preemption":store.refresh(preemption_id,execution.to_dict()).to_dict()}

@router.post("/owner-control/preemptions/{preemption_id}/reconcile")
def reconcile_autonomy_preemption_endpoint(preemption_id:str):
    from app.cognition.action_proposal import ActionProposal
    from app.cognition.execution_control import execution_control_registry
    from app.cognition.plan_control import plan_review_store
    from app.cognition.plan_step_reconciliation import plan_step_reconciliation_store
    from app.cognition.runtime import CognitiveRuntime
    runtime=CognitiveRuntime.get_instance();store=runtime.autonomy_preemptions;item=store.get(preemption_id)
    if not item:raise HTTPException(status_code=404,detail="Preemption not found")
    previous=execution_control_registry.get_result(item.execution_id)
    execution=execution_control_registry.get(item.execution_id)
    review=plan_review_store.get(item.plan_id) if item.plan_id else None
    if not previous or not execution or not review:
        raise HTTPException(status_code=409,detail="Execution result and reviewed plan are required for observation-only reconciliation")
    # Bind the interrupted execution to ONE exact reviewed step. action_type
    # alone is not sufficient: multiple steps may share an action type. Payload
    # equality disambiguates; remaining ambiguity refuses rather than binding
    # the wrong step.
    candidates=[s for s in review.snapshot.get("steps",[]) if s.get("action_type")==execution.action_type]
    exact=[s for s in candidates if dict(s.get("payload") or {})==dict(previous.get("payload") or {})]
    if len(candidates)>1 and len(exact)==1: step=exact[0]
    elif len(candidates)==1: step=candidates[0]
    elif len(candidates)==0:
        raise HTTPException(status_code=409,detail="Could not bind interrupted execution to an exact reviewed step")
    else:
        raise HTTPException(status_code=409,detail=f"Ambiguous step binding: {len(candidates)} reviewed steps share action '{execution.action_type}' and the payload does not disambiguate")
    proposal=ActionProposal(action_type=step["action_type"],payload=dict(step.get("payload") or {}),plan_id=item.plan_id)
    result=runtime.verify_existing_proposal_outcome(proposal,review.goal_title,previous)
    if result.get("goal_verified"):recommendation="skip_verified_step_and_review_next"
    elif result.get("verification_unknown"):recommendation="wait_for_evidence"
    else:recommendation="create_fresh_replan"
    result["resume_recommendation"]=recommendation;result["executed"]=False
    # Apply the reconciliation to the exact plan step: completed steps are
    # skipped (never re-executed) on resume; unknown steps halt for evidence;
    # failed work requires a fresh plan revision.
    record=plan_step_reconciliation_store.apply(
        item.plan_id,step,recommendation,
        verification=result,preemption_id=preemption_id,execution_id=item.execution_id,
    )
    store.record_reconciliation(preemption_id,result)
    return {"success":True,"reconciliation":result,"step_status_update":record.to_dict()}

@router.get("/owner-control/plans/{plan_id}/step-reconciliations")
def get_plan_step_reconciliations_endpoint(plan_id: str):
    from app.cognition.plan_step_reconciliation import plan_step_reconciliation_store
    records = plan_step_reconciliation_store.for_plan(plan_id)
    return {
        "success": True,
        "plan_id": plan_id,
        "step_reconciliations": [r.to_dict() for r in records],
        "note": "completed steps are skipped on resume; unknown_pending_evidence and needs_fresh_replan halt for evidence or a fresh revision.",
    }

@router.post("/owner-control/preemptions/{preemption_id}/request-resume")
def request_autonomy_resume_endpoint(preemption_id:str):
    from app.cognition.runtime import CognitiveRuntime
    store=CognitiveRuntime.get_instance().autonomy_preemptions
    reconciliation=store.get_reconciliation(preemption_id)
    if not reconciliation:
        raise HTTPException(status_code=409,detail="Observation-only reconciliation is required before resume")
    if reconciliation.get("verification_unknown"):
        raise HTTPException(status_code=409,detail="Resume remains blocked while outcome evidence is unknown")
    try:item=store.request_resume(preemption_id)
    except KeyError as exc:raise HTTPException(status_code=404,detail="Preemption not found") from exc
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    return {"success":True,"preemption":item.to_dict(),"executed":False,"note":"Resume request recorded. Reconcile evidence, then separately execute the approved plan."}

@router.post("/owner-control/owner-decisions")
def issue_owner_decision_endpoint(req: OwnerDecisionRequest):
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.owner_decisions import DECISION_TYPES
    if req.decision_type != "expected_identity_change":
        return {"success": False, "error": f"Unsupported decision type; supported: {sorted(DECISION_TYPES)}"}
    if not req.expected_change_types:
        return {"success": False, "error": "expected_change_types must list the change types this decision authorizes"}
    decision = CognitiveRuntime.get_instance().owner_decisions.issue(
        "expected_identity_change",
        {"expected_change_types": req.expected_change_types},
        note=req.note,
    )
    return {
        "success": True, "decision": decision.to_dict(),
        "note": "Single-use, revocable, content-digested. Pass owner_decision_id to the identity-checkpoint that expects these changes.",
    }

@router.get("/owner-control/questions")
def list_owner_questions_endpoint(status: Optional[str] = Query("pending"), limit: int = Query(100, ge=1, le=500)):
    from app.cognition.uncertainty_questions import owner_question_store
    return {"success": True, "questions": [q.to_dict() for q in owner_question_store.list(status, limit)],
            "note": "approve creates an exact authorization; it never executes anything."}

@router.post("/owner-control/questions/{question_id}/answer")
def answer_owner_question_endpoint(question_id: str, req: QuestionAnswerRequest):
    from app.cognition.uncertainty_questions import owner_question_store
    result = owner_question_store.answer(question_id, req.answer.strip().lower(), req.note)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "Answer failed"))
    return result

@router.post("/owner-control/questions/{question_id}/cancel")
def cancel_owner_question_endpoint(question_id: str):
    from app.cognition.uncertainty_questions import owner_question_store
    result = owner_question_store.cancel(question_id)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "Cancel failed"))
    return result

@router.get("/owner-control/owner-decisions")
def list_owner_decisions_endpoint(limit: int = Query(200, ge=1, le=1000)):
    from app.cognition.runtime import CognitiveRuntime
    decisions = CognitiveRuntime.get_instance().owner_decisions.list(limit)
    return {"success": True, "decisions": [d.to_dict() for d in decisions]}

@router.post("/owner-control/owner-decisions/{decision_id}/revoke")
def revoke_owner_decision_endpoint(decision_id: str):
    from app.cognition.runtime import CognitiveRuntime
    try:
        decision = CognitiveRuntime.get_instance().owner_decisions.revoke(decision_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Decision not found")
    return {"success": True, "decision": decision.to_dict()}
