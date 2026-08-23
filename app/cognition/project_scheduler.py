"""Persistent, resource-aware execution of ready project sub-goals.

The scheduler uses GoalDecomposition and ProjectManager as its durable state.
It executes exact sub-goal action/payload proposals through CognitiveRuntime's
full observation/verification loop and never marks progress from tool success.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict, List, Optional

from app.cognition.action_proposal import ActionProposal
from app.cognition.goal_decomposer import GoalDecomposer, SubGoal, SubGoalStatus
from app.cognition.project_manager import ProjectManager, ProjectStatus
from app.utils.logger import app_logger


class ProjectDAGScheduler:
    def __init__(
        self,
        goal_decomposer: GoalDecomposer,
        project_manager: ProjectManager,
    ) -> None:
        self.goal_decomposer = goal_decomposer
        self.project_manager = project_manager

    @staticmethod
    def _proposal_for(
        sub_goal: SubGoal,
        original_goal: str,
        reviewed_step: Optional[Any] = None,
    ) -> ActionProposal:
        action_type = (
            getattr(reviewed_step, "action_type", "") if reviewed_step is not None else ""
        ) or sub_goal.action_type
        reviewed_payload = (
            getattr(reviewed_step, "payload", None) if reviewed_step is not None else None
        )
        is_reviewed = isinstance(reviewed_payload, dict)
        payload = dict(reviewed_payload if is_reviewed else (sub_goal.payload or {}))
        description = (
            getattr(reviewed_step, "description", "") if reviewed_step is not None else ""
        ) or sub_goal.description
        if not is_reviewed:
            payload.setdefault("query", description)
            payload.setdefault("original_goal", original_goal)
            payload.setdefault("source_sub_goal_id", sub_goal.sub_goal_id)
        return ActionProposal(
            action_type=action_type,
            payload=payload,
            recommendation_reason=(
                f"Dependency-ready project sub-goal: {description}"
            ),
        )

    def _record_waiting_approval(
        self,
        project: Any,
        decomposition: Any,
        sub_goal: SubGoal,
        proposal: ActionProposal,
        gate_result: Dict[str, Any],
    ) -> None:
        from app.cognition.approval_store import approval_store

        request = approval_store.add(
            conversation_id=f"project:{project.project_id}",
            action_type=proposal.action_type,
            payload=proposal.payload,
            reason=gate_result.get("reason", "Project action requires owner approval"),
            goal_text=sub_goal.description,
            proposal_id=proposal.proposal_id,
            recommendation_reason=proposal.recommendation_reason,
            alternatives_considered=proposal.alternatives_considered,
            predicted_outcome=proposal.predicted_outcome,
        )
        self.goal_decomposer.update_sub_goal(
            decomposition.project_id,
            sub_goal.sub_goal_id,
            SubGoalStatus.WAITING_APPROVAL,
            result={
                "request_success": True,
                "execution_success": False,
                "goal_verified": False,
                "waiting_approval": True,
                "approval_action_id": request.action_id,
                "proposal_id": proposal.proposal_id,
                "action_type": proposal.action_type,
                "payload": proposal.payload,
            },
        )

    def _execute(
        self,
        cognitive_runtime: Any,
        project: Any,
        decomposition: Any,
        sub_goal: SubGoal,
        authorization_id: Optional[str] = None,
        reviewed_step: Optional[Any] = None,
    ) -> Dict[str, Any]:
        proposal = self._proposal_for(
            sub_goal, decomposition.original_goal, reviewed_step=reviewed_step
        )
        if isinstance(sub_goal.result, dict) and sub_goal.result.get("proposal_id"):
            proposal.proposal_id = str(sub_goal.result["proposal_id"])
        proposal.authorization_id = authorization_id

        # Persist IN_PROGRESS before touching the capability layer so restart
        # recovery can distinguish never-started from interrupted work.
        self.goal_decomposer.update_sub_goal(
            decomposition.project_id,
            sub_goal.sub_goal_id,
            SubGoalStatus.IN_PROGRESS,
            result={
                "request_success": True,
                "execution_success": False,
                "goal_verified": False,
                "scheduler_state": "executing",
                "proposal_id": proposal.proposal_id,
            },
        )
        result = cognitive_runtime.execute_authorized_proposal(
            proposal,
            user_text=(getattr(reviewed_step, "description", "") or sub_goal.description),
            complexity="fast",
            session_id=f"project_{project.project_id}_{sub_goal.sub_goal_id}",
            success_criteria_override=(
                list(getattr(reviewed_step, "success_criteria", []) or [])
                if reviewed_step is not None else None
            ),
            failure_conditions_override=(
                list(getattr(reviewed_step, "failure_conditions", []) or [])
                if reviewed_step is not None else None
            ),
        )

        if result.get("requires_approval"):
            self._record_waiting_approval(
                project, decomposition, sub_goal, proposal, result
            )
            return {"sub_goal_id": sub_goal.sub_goal_id, "status": "waiting_approval"}

        if result.get("goal_verified") is True:
            verified_result = dict(result)
            verified_result["verified_success"] = True
            self.goal_decomposer.update_sub_goal(
                decomposition.project_id,
                sub_goal.sub_goal_id,
                SubGoalStatus.COMPLETED,
                result=verified_result,
            )
            return {"sub_goal_id": sub_goal.sub_goal_id, "status": "completed"}

        lifecycle = str(result.get("goal_lifecycle_state", ""))
        if result.get("verification_unknown") or lifecycle == "waiting_for_evidence":
            self.goal_decomposer.update_sub_goal(
                decomposition.project_id,
                sub_goal.sub_goal_id,
                SubGoalStatus.WAITING_EVIDENCE,
                result=dict(result),
            )
            return {"sub_goal_id": sub_goal.sub_goal_id, "status": "waiting_evidence"}

        error = (
            result.get("reason")
            or result.get("assistant_reply")
            or "Sub-goal execution or verification failed"
        )
        self.goal_decomposer.update_sub_goal(
            decomposition.project_id,
            sub_goal.sub_goal_id,
            SubGoalStatus.FAILED,
            result=dict(result),
            error=str(error),
        )
        self.goal_decomposer.mark_dependents_blocked(
            decomposition.project_id, sub_goal.sub_goal_id
        )
        return {"sub_goal_id": sub_goal.sub_goal_id, "status": "failed", "error": str(error)}

    @staticmethod
    def _review_is_current(review: Optional[Any]) -> bool:
        if review is None:
            return True
        from app.cognition.plan_control import PlanReviewStatus, plan_review_store
        current = plan_review_store.get(review.plan_id)
        return bool(
            current
            and current.status == PlanReviewStatus.APPROVED
            and current.revision == review.revision
            and current.snapshot_sha256 == review.snapshot_sha256
        )

    def _resume_waiting_approvals(
        self,
        cognitive_runtime: Any,
        project: Any,
        decomposition: Any,
        remaining_budget: int,
        reviewed_steps: Optional[Dict[str, Any]] = None,
        plan_review: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        from app.cognition.approval_store import approval_store

        resumed: List[Dict[str, Any]] = []
        for sub_goal in decomposition.sub_goals:
            if len(resumed) >= remaining_budget:
                break
            if not self._review_is_current(plan_review):
                resumed.append({"status": "plan_approval_invalidated"})
                break
            if sub_goal.status != SubGoalStatus.WAITING_APPROVAL:
                continue
            action_id = (
                sub_goal.result.get("approval_action_id")
                if isinstance(sub_goal.result, dict)
                else None
            )
            request = approval_store.get(str(action_id)) if action_id else None
            if request is None:
                # Approval requests are intentionally memory-only. After restart,
                # return to PENDING and issue a fresh request without executing.
                self.goal_decomposer.update_sub_goal(
                    decomposition.project_id,
                    sub_goal.sub_goal_id,
                    SubGoalStatus.PENDING,
                    result={"scheduler_state": "approval_request_lost_after_restart"},
                )
                resumed.append({"sub_goal_id": sub_goal.sub_goal_id, "status": "approval_reset"})
            elif request.status == "denied":
                self.goal_decomposer.update_sub_goal(
                    decomposition.project_id,
                    sub_goal.sub_goal_id,
                    SubGoalStatus.FAILED,
                    result={"goal_verified": False, "approval_denied": True},
                    error="Owner denied project sub-goal action",
                )
                self.goal_decomposer.mark_dependents_blocked(
                    decomposition.project_id, sub_goal.sub_goal_id
                )
                resumed.append({"sub_goal_id": sub_goal.sub_goal_id, "status": "denied"})
            elif request.status == "approved" and request.authorization_id:
                resumed.append(self._execute(
                    cognitive_runtime,
                    project,
                    decomposition,
                    sub_goal,
                    authorization_id=request.authorization_id,
                    reviewed_step=(reviewed_steps or {}).get(sub_goal.sub_goal_id),
                ))
        return resumed

    @staticmethod
    def _review_payload(sub_goal: SubGoal, original_goal: str) -> Dict[str, Any]:
        payload = dict(sub_goal.payload or {})
        payload.setdefault("query", sub_goal.description)
        payload.setdefault("original_goal", original_goal)
        payload.setdefault("source_sub_goal_id", sub_goal.sub_goal_id)
        return payload

    def _plan_scope(self, project: Any, decomposition: Any):
        """Return (scope, reviewed-step map, review) for approve-each-plan mode."""
        from app.cognition.owner_control import (
            ControlMode,
            authorized_plan_scope,
            owner_control_store,
        )

        policy = owner_control_store.get_policy()
        if policy.mode != ControlMode.APPROVE_EACH_PLAN:
            return nullcontext(), {}, None

        from app.cognition.autonomous_goal_executor import (
            ExecutionPlan,
            ExecutionStep,
            TaskType,
        )
        from app.cognition.plan_control import PlanReviewStatus, plan_review_store

        plan = ExecutionPlan(
            plan_id=f"project_dag_{project.project_id}",
            goal_id=decomposition.project_id,
            goal_title=project.name,
            steps=[
                ExecutionStep(
                    step_id=sub_goal.sub_goal_id,
                    goal_id=decomposition.project_id,
                    description=sub_goal.description,
                    task_type=TaskType.ANALYSIS,
                    action_type=sub_goal.action_type,
                    payload=self._review_payload(sub_goal, decomposition.original_goal),
                    source_sub_goal_id=sub_goal.sub_goal_id,
                    depends_on=list(sub_goal.depends_on),
                    success_criteria=list(
                        (sub_goal.payload or {}).get("success_criteria", [])
                    ),
                    failure_conditions=list(
                        (sub_goal.payload or {}).get("failure_conditions", [])
                    ),
                )
                for sub_goal in decomposition.sub_goals
            ],
        )
        review = plan_review_store.get(plan.plan_id)
        if review is None:
            review = plan_review_store.submit(plan)
        if review.status != PlanReviewStatus.APPROVED:
            return nullcontext(), {}, review

        plan_review_store.apply_to_plan(plan)
        if not plan_review_store.is_current_approval(plan):
            return nullcontext(), {}, review
        reviewed_steps = {
            (step.source_sub_goal_id or step.step_id): step for step in plan.steps
        }
        return (
            authorized_plan_scope(plan.plan_id, policy.max_autonomous_level),
            reviewed_steps,
            review,
        )

    def run_project(
        self,
        cognitive_runtime: Any,
        project_id: str,
        max_steps: int = 1,
    ) -> Dict[str, Any]:
        """Run a bounded number of ready steps for one persistent project."""
        max_steps = max(1, min(10, int(max_steps)))
        project = self.project_manager.get_project(project_id)
        if project is None:
            return {"success": False, "error": "Project not found", "project_id": project_id}
        if not project.decomposition_id:
            return {"success": False, "error": "Project has no goal decomposition", "project_id": project_id}
        decomposition = self.goal_decomposer.get_project(project.decomposition_id)
        if decomposition is None:
            return {"success": False, "error": "Goal decomposition not found", "project_id": project_id}
        if project.status in (ProjectStatus.COMPLETED, ProjectStatus.ABANDONED):
            return {
                "success": True,
                "project_id": project_id,
                "status": project.status.value,
                "executed": [],
            }
        if project.current_session is None:
            self.project_manager.start_session(project.project_id)

        scope, reviewed_steps, review = self._plan_scope(project, decomposition)
        if review is not None and getattr(review.status, "value", review.status) != "approved":
            return {
                "success": True,
                "project_id": project_id,
                "decomposition_id": decomposition.project_id,
                "executed": [],
                "status": "waiting_plan_approval",
                "plan_review": review.to_dict(),
                "progress": self.goal_decomposer.get_progress_report(decomposition.project_id),
            }

        with scope:
            outcomes = self._resume_waiting_approvals(
                cognitive_runtime,
                project,
                decomposition,
                max_steps,
                reviewed_steps=reviewed_steps,
                plan_review=review,
            )
            budget = max_steps - len(outcomes)
            if budget > 0:
                schedule = decomposition.get_resource_aware_schedule(
                    hardware_self_model=getattr(cognitive_runtime, "hardware_self_model", None),
                    resource_manager=getattr(
                        getattr(cognitive_runtime, "advanced_cognition", None),
                        "resource_manager",
                        None,
                    ),
                )
                for sub_goal in schedule[:budget]:
                    if not self._review_is_current(review):
                        outcomes.append({"status": "plan_approval_invalidated"})
                        break
                    if sub_goal.status != SubGoalStatus.PENDING:
                        continue
                    outcomes.append(self._execute(
                        cognitive_runtime,
                        project,
                        decomposition,
                        sub_goal,
                        reviewed_step=reviewed_steps.get(sub_goal.sub_goal_id),
                    ))

        reconciliation = self.project_manager.reconcile_decomposition(decomposition)
        return {
            "success": True,
            "project_id": project_id,
            "decomposition_id": decomposition.project_id,
            "executed": outcomes,
            "reconciliation": reconciliation,
            "progress": self.goal_decomposer.get_progress_report(decomposition.project_id),
        }

    def run_cycle(
        self,
        cognitive_runtime: Any,
        max_projects: int = 3,
        max_steps_per_project: int = 1,
    ) -> Dict[str, Any]:
        """Resume a bounded set of active projects; safe to call every cycle."""
        results = []
        eligible = [
            project for project in self.project_manager.get_active_projects()
            if project.decomposition_id and project.context.get("auto_schedule") is True
        ]
        for project in eligible[:max(1, max_projects)]:
            try:
                results.append(self.run_project(
                    cognitive_runtime,
                    project.project_id,
                    max_steps=max_steps_per_project,
                ))
            except Exception as exc:
                app_logger.error(f"Project DAG scheduler failed for {project.project_id}: {exc}")
                results.append({
                    "success": False,
                    "project_id": project.project_id,
                    "error": str(exc),
                })
        return {
            "success": all(item.get("success") for item in results),
            "projects_processed": len(results),
            "results": results,
        }
