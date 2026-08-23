"""Verified sub-goal outcomes automatically drive persistent project milestones."""

from app.cognition.goal_decomposer import GoalDecomposer, SubGoalStatus
from app.cognition.project_manager import ProjectManager, ProjectStatus


def _linked(tmp_path):
    decomposer = GoalDecomposer(db_path=str(tmp_path / "decompositions.db"))
    manager = ProjectManager(db_path=str(tmp_path / "projects.db"))
    decomposition = decomposer.decompose(
        "Research and report",
        custom_steps=[
            {"description": "Collect evidence", "action_type": "web_search", "depends_on": []},
            {"description": "Write report", "action_type": "formulate_answer", "depends_on": [0]},
        ],
    )
    project = manager.create_project(
        "Research project",
        decomposition_id=decomposition.project_id,
        milestones=[
            {"description": sg.description, "source_sub_goal_id": sg.sub_goal_id}
            for sg in decomposition.sub_goals
        ],
    )
    manager.start_session(project.project_id)
    decomposer.add_update_listener(
        lambda updated, _sub_goal: manager.reconcile_decomposition(updated)
    )
    return decomposer, manager, decomposition, project


def test_unverified_completion_does_not_reach_milestone(tmp_path):
    decomposer, manager, decomposition, project = _linked(tmp_path)
    first = decomposition.sub_goals[0]

    decomposer.update_sub_goal(
        decomposition.project_id,
        first.sub_goal_id,
        SubGoalStatus.COMPLETED,
        result={
            "status": "done",
            "execution_success": True,
            "verification_status": "satisfied",  # text alone is not verifier authority
        },
    )

    updated = manager.get_project(project.project_id)
    assert updated.milestones[0].status == "pending"
    assert updated.progress_percent == 0.0


def test_verified_completion_reaches_linked_milestone_and_records_session(tmp_path):
    decomposer, manager, decomposition, project = _linked(tmp_path)
    first = decomposition.sub_goals[0]

    decomposer.update_sub_goal(
        decomposition.project_id,
        first.sub_goal_id,
        SubGoalStatus.COMPLETED,
        result={
            "execution_success": True,
            "goal_verified": True,
            "verification_status": "satisfied",
            "evidence": [{"source": "direct_probe", "value": "found"}],
        },
    )

    updated = manager.get_project(project.project_id)
    milestone = updated.milestones[0]
    assert milestone.status == "reached"
    assert milestone.reached_at is not None
    assert first.description in updated.current_session.tasks_completed
    assert updated.progress_percent == 50.0


def test_reconciliation_is_idempotent(tmp_path):
    decomposer, manager, decomposition, project = _linked(tmp_path)
    first = decomposition.sub_goals[0]
    result = {"verified_success": True, "verification_status": "verified"}

    decomposer.update_sub_goal(
        decomposition.project_id, first.sub_goal_id, SubGoalStatus.COMPLETED, result=result
    )
    initial_reached_at = manager.get_project(project.project_id).milestones[0].reached_at
    summary = manager.reconcile_decomposition(decomposition)

    updated = manager.get_project(project.project_id)
    assert summary["milestones_reached"] == 0
    assert updated.milestones[0].reached_at == initial_reached_at
    assert updated.current_session.tasks_completed.count(first.description) == 1


def test_failed_sub_goal_blocks_project_and_is_persisted(tmp_path):
    decomposer, manager, decomposition, project = _linked(tmp_path)
    first = decomposition.sub_goals[0]

    decomposer.update_sub_goal(
        decomposition.project_id,
        first.sub_goal_id,
        SubGoalStatus.FAILED,
        error="Probe failed",
    )

    updated = manager.get_project(project.project_id)
    assert updated.status == ProjectStatus.BLOCKED
    assert updated.milestones[0].status == "failed"
    assert first.description in updated.current_session.tasks_failed

    restored = ProjectManager(db_path=str(tmp_path / "projects.db"))
    persisted = restored.get_project(project.project_id)
    assert persisted.milestones[0].source_sub_goal_id == first.sub_goal_id
    assert persisted.milestones[0].status == "failed"


def test_all_verified_milestones_complete_project(tmp_path):
    decomposer, manager, decomposition, project = _linked(tmp_path)

    for sub_goal in decomposition.sub_goals:
        decomposer.update_sub_goal(
            decomposition.project_id,
            sub_goal.sub_goal_id,
            SubGoalStatus.COMPLETED,
            result={"verified_success": True},
        )

    updated = manager.get_project(project.project_id)
    assert updated.status == ProjectStatus.COMPLETED
    assert updated.completed_at is not None
    assert updated.progress_percent == 100.0
