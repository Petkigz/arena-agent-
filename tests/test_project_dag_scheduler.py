"""Persistent project DAG scheduler integration and approval recovery."""

from unittest.mock import patch

from app.cognition.approval_store import ApprovalStore
from app.cognition.goal_decomposer import GoalDecomposer, SubGoalStatus
from app.cognition.owner_control import OwnerControlStore
from app.cognition.plan_control import PlanReviewStore
from app.cognition.project_manager import ProjectManager, ProjectStatus
from app.cognition.project_scheduler import ProjectDAGScheduler


class _Runtime:
    hardware_self_model = None
    advanced_cognition = None

    def __init__(self, results):
        self.results = list(results)
        self.proposals = []

    def execute_authorized_proposal(self, proposal, **kwargs):
        self.proposals.append(proposal)
        return self.results.pop(0)


def _system(tmp_path, auto_schedule=True):
    decomposer = GoalDecomposer(str(tmp_path / "decomp.db"))
    manager = ProjectManager(str(tmp_path / "projects.db"))
    decomposition = decomposer.decompose(
        "Research and report",
        custom_steps=[
            {"description": "Collect evidence", "action_type": "web_search", "depends_on": []},
            {"description": "Write report", "action_type": "formulate_answer", "depends_on": [0]},
        ],
    )
    project = manager.create_project(
        "Research",
        decomposition_id=decomposition.project_id,
        context={"auto_schedule": auto_schedule},
        milestones=[
            {"description": sg.description, "source_sub_goal_id": sg.sub_goal_id}
            for sg in decomposition.sub_goals
        ],
    )
    decomposer.add_update_listener(
        lambda updated, _sub_goal: manager.reconcile_decomposition(updated)
    )
    return decomposer, manager, decomposition, project, ProjectDAGScheduler(decomposer, manager)


def _verified():
    return {
        "success": True,
        "request_success": True,
        "execution_success": True,
        "goal_verified": True,
        "goal_lifecycle_state": "achieved",
        "executed_actions": ["Observed result"],
    }


def test_scheduler_executes_dependency_ready_steps_across_cycles(tmp_path):
    decomposer, manager, decomposition, project, scheduler = _system(tmp_path)
    runtime = _Runtime([_verified(), _verified()])

    first = scheduler.run_project(runtime, project.project_id, max_steps=1)
    assert first["executed"][0]["status"] == "completed"
    assert decomposition.sub_goals[0].status == SubGoalStatus.COMPLETED
    assert decomposition.sub_goals[1].status == SubGoalStatus.PENDING
    assert manager.get_project(project.project_id).progress_percent == 50.0

    second = scheduler.run_project(runtime, project.project_id, max_steps=1)
    assert second["executed"][0]["status"] == "completed"
    assert decomposition.sub_goals[1].status == SubGoalStatus.COMPLETED
    assert manager.get_project(project.project_id).status == ProjectStatus.COMPLETED
    assert [proposal.action_type for proposal in runtime.proposals] == [
        "web_search", "formulate_answer"
    ]


def test_tool_success_without_verification_waits_for_evidence_and_is_not_retried(tmp_path):
    _, manager, decomposition, project, scheduler = _system(tmp_path)
    runtime = _Runtime([{
        "success": True,
        "execution_success": True,
        "goal_verified": False,
        "verification_unknown": True,
        "goal_lifecycle_state": "waiting_for_evidence",
    }])

    result = scheduler.run_project(runtime, project.project_id)
    assert result["executed"][0]["status"] == "waiting_evidence"
    assert decomposition.sub_goals[0].status == SubGoalStatus.WAITING_EVIDENCE
    assert manager.get_project(project.project_id).progress_percent == 0.0

    again = scheduler.run_project(runtime, project.project_id)
    assert again["executed"] == []
    assert len(runtime.proposals) == 1


def test_sensitive_step_waits_then_resumes_with_exact_authorization(tmp_path):
    decomposer = GoalDecomposer(str(tmp_path / "decomp.db"))
    manager = ProjectManager(str(tmp_path / "projects.db"))
    decomposition = decomposer.decompose(
        "Send report",
        custom_steps=[{
            "description": "Send approved report",
            "action_type": "send_email",
            "payload": {"to": "owner@example.test", "body": "report"},
            "depends_on": [],
        }],
    )
    project = manager.create_project(
        "Send",
        decomposition_id=decomposition.project_id,
        milestones=[{
            "description": decomposition.sub_goals[0].description,
            "source_sub_goal_id": decomposition.sub_goals[0].sub_goal_id,
        }],
    )
    decomposer.add_update_listener(
        lambda updated, _sub_goal: manager.reconcile_decomposition(updated)
    )
    scheduler = ProjectDAGScheduler(decomposer, manager)
    approvals = ApprovalStore()
    runtime = _Runtime([
        {
            "success": False,
            "execution_success": False,
            "goal_verified": False,
            "requires_approval": True,
            "reason": "Level 3 requires approval",
        },
        _verified(),
    ])

    with patch("app.cognition.approval_store.approval_store", approvals):
        first = scheduler.run_project(runtime, project.project_id)
        assert first["executed"][0]["status"] == "waiting_approval"
        sub_goal = decomposition.sub_goals[0]
        assert sub_goal.status == SubGoalStatus.WAITING_APPROVAL
        action_id = sub_goal.result["approval_action_id"]
        request = approvals.decide(action_id, approved=True)
        assert request.authorization_id

        second = scheduler.run_project(runtime, project.project_id)

    assert second["executed"][0]["status"] == "completed"
    assert runtime.proposals[-1].authorization_id == request.authorization_id
    assert manager.get_project(project.project_id).status == ProjectStatus.COMPLETED


def test_approve_each_plan_reviews_exact_actions_and_owner_edits(tmp_path):
    _, _, decomposition, project, scheduler = _system(tmp_path)
    runtime = _Runtime([_verified()])
    policy = OwnerControlStore(tmp_path / "control.json")
    policy.update({"mode": "approve_each_plan"})
    reviews = PlanReviewStore(tmp_path / "reviews.db")

    with (
        patch("app.cognition.owner_control.owner_control_store", policy),
        patch("app.cognition.plan_control.plan_review_store", reviews),
    ):
        waiting = scheduler.run_project(runtime, project.project_id)
        assert waiting["status"] == "waiting_plan_approval"
        assert runtime.proposals == []

        review = reviews.get(f"project_dag_{project.project_id}")
        first_step = review.snapshot["steps"][0]
        assert first_step["action_type"] == "web_search"
        assert first_step["source_sub_goal_id"] == decomposition.sub_goals[0].sub_goal_id

        edited_steps = list(review.snapshot["steps"])
        edited_steps[0] = {
            **edited_steps[0],
            "action_type": "search_files",
            "payload": {"query": "owner-approved local evidence"},
        }
        edited = reviews.edit(review.plan_id, review.revision, edited_steps)
        reviews.decide(edited.plan_id, edited.revision, approved=True)

        executed = scheduler.run_project(runtime, project.project_id)

    assert executed["executed"][0]["status"] == "completed"
    assert runtime.proposals[0].action_type == "search_files"
    assert runtime.proposals[0].payload["query"] == "owner-approved local evidence"


def test_periodic_scheduler_only_runs_owner_enabled_projects(tmp_path):
    _, _, _, disabled_project, scheduler = _system(tmp_path, auto_schedule=False)
    runtime = _Runtime([_verified()])

    cycle = scheduler.run_cycle(runtime)

    assert cycle["projects_processed"] == 0
    assert runtime.proposals == []
    assert disabled_project.context["auto_schedule"] is False
