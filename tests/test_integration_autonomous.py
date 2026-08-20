"""
Phase 6: Integration & Autonomous Operation Tests.

6A: Goal Decomposition — sub-goal DAGs, dependency tracking, execution order
6B: Multi-Session Projects — persistent projects, session tracking, resume context
6C: Autonomous Operation — task queue, approval, escalation, progress reporting
"""

import pytest
from app.cognition.goal_decomposer import (
    GoalDecomposer, GoalDecomposition, SubGoal, SubGoalStatus
)
from app.cognition.project_manager import (
    ProjectManager, Project, ProjectStatus, SessionRecord, Milestone
)
from app.cognition.autonomous_operator import (
    AutonomousOperator, AutonomousTask, TaskApproval, EscalationReason,
    Escalation, ProgressReport
)


# ── 6A: Goal Decomposition ──────────────────────────────────────────


class TestGoalDecomposition:

    def test_decompose_with_template(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Set up development environment",
            template="setup_environment"
        )
        assert decomp.total_sub_goals == 4
        assert decomp.sub_goals[0].description == "Check system prerequisites"
        assert decomp.sub_goals[1].description == "Install required packages"
        # Second step depends on first
        assert decomp.sub_goals[1].depends_on == [decomp.sub_goals[0].sub_goal_id]

    def test_decompose_with_custom_steps(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Custom task",
            custom_steps=[
                {"description": "Step A", "action_type": "search_files", "depends_on": []},
                {"description": "Step B", "action_type": "web_search", "depends_on": [0]},
                {"description": "Step C", "action_type": "formulate_answer", "depends_on": [0, 1]},
            ]
        )
        assert decomp.total_sub_goals == 3
        assert decomp.sub_goals[2].depends_on == [
            decomp.sub_goals[0].sub_goal_id,
            decomp.sub_goals[1].sub_goal_id,
        ]

    def test_auto_detect_setup_template(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose("Install and configure the dev environment")
        assert decomp.total_sub_goals == 4  # setup_environment template

    def test_auto_detect_research_template(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose("Research and report on AI trends")
        assert decomp.total_sub_goals == 3  # research_and_report template

    def test_get_ready_sub_goals(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Test",
            custom_steps=[
                {"description": "A", "action_type": "search_files", "depends_on": []},
                {"description": "B", "action_type": "search_files", "depends_on": []},
                {"description": "C", "action_type": "web_search", "depends_on": [0, 1]},
            ]
        )
        ready = decomp.get_ready_sub_goals()
        assert len(ready) == 2  # A and B are ready, C depends on them

    def test_get_ready_after_completion(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Test",
            custom_steps=[
                {"description": "A", "action_type": "search_files", "depends_on": []},
                {"description": "B", "action_type": "web_search", "depends_on": [0]},
            ]
        )

        # Complete step A
        decomposer.update_sub_goal(
            decomp.project_id, decomp.sub_goals[0].sub_goal_id,
            SubGoalStatus.COMPLETED, result={"status": "done"}
        )

        # Now B should be ready
        ready = decomp.get_ready_sub_goals()
        assert len(ready) == 1
        assert ready[0].description == "B"

    def test_progress_tracking(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Test",
            custom_steps=[
                {"description": "A", "action_type": "a", "depends_on": []},
                {"description": "B", "action_type": "b", "depends_on": []},
                {"description": "C", "action_type": "c", "depends_on": []},
                {"description": "D", "action_type": "d", "depends_on": []},
            ]
        )
        assert decomp.progress_percent == 0.0

        decomposer.update_sub_goal(decomp.project_id, decomp.sub_goals[0].sub_goal_id, SubGoalStatus.COMPLETED)
        assert decomp.progress_percent == 25.0

        decomposer.update_sub_goal(decomp.project_id, decomp.sub_goals[1].sub_goal_id, SubGoalStatus.COMPLETED)
        assert decomp.progress_percent == 50.0

    def test_blocked_dependents_on_failure(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Test",
            custom_steps=[
                {"description": "A", "action_type": "a", "depends_on": []},
                {"description": "B", "action_type": "b", "depends_on": [0]},
                {"description": "C", "action_type": "c", "depends_on": [1]},
            ]
        )

        # Fail step A
        decomposer.update_sub_goal(
            decomp.project_id, decomp.sub_goals[0].sub_goal_id,
            SubGoalStatus.FAILED, error="Could not complete"
        )

        # B and C should be blocked
        blocked = decomposer.mark_dependents_blocked(decomp.project_id, decomp.sub_goals[0].sub_goal_id)
        assert len(blocked) == 2

    def test_execution_order_topological_sort(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Test",
            custom_steps=[
                {"description": "A", "action_type": "a", "depends_on": []},
                {"description": "B", "action_type": "b", "depends_on": [0]},
                {"description": "C", "action_type": "c", "depends_on": [0]},
                {"description": "D", "action_type": "d", "depends_on": [1, 2]},
            ]
        )
        order = decomp.get_execution_order()
        names = [sg.description for sg in order]
        assert names[0] == "A"
        assert "D" == names[-1]  # D is last (depends on B and C)

    def test_progress_report(self, tmp_path):
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        decomp = decomposer.decompose(
            "Build feature",
            custom_steps=[
                {"description": "Design", "action_type": "a", "depends_on": []},
                {"description": "Implement", "action_type": "b", "depends_on": [0]},
                {"description": "Test", "action_type": "c", "depends_on": [1]},
            ]
        )
        decomposer.update_sub_goal(decomp.project_id, decomp.sub_goals[0].sub_goal_id, SubGoalStatus.COMPLETED)

        report = decomposer.get_progress_report(decomp.project_id)
        assert report is not None
        assert report["progress_percent"] == pytest.approx(33.3, abs=0.1)
        assert report["completed"] == 1
        assert len(report["next_actions"]) == 1  # "Implement" is next

    def test_persistence(self, tmp_path):
        db_path = str(tmp_path / "decomp.db")
        d1 = GoalDecomposer(db_path=db_path)
        decomp = d1.decompose("Test project", custom_steps=[
            {"description": "Step 1", "action_type": "a", "depends_on": []},
        ])
        project_id = decomp.project_id

        d2 = GoalDecomposer(db_path=db_path)
        loaded = d2.get_project(project_id)
        assert loaded is not None
        assert loaded.total_sub_goals == 1


# ── 6B: Multi-Session Projects ───────────────────────────────────────


class TestProjectManager:

    def test_create_project(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        project = pm.create_project(
            name="Build Dashboard",
            description="Create a web dashboard for task management",
            priority="high",
            milestones=["Design complete", "Backend done", "Frontend done", "Deployed"],
            tags=["web", "dashboard"]
        )
        assert project.name == "Build Dashboard"
        assert project.status == ProjectStatus.ACTIVE
        assert project.milestones_total == 4
        assert pm.total_projects() == 1

    def test_session_lifecycle(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        project = pm.create_project("Test Project")

        session = pm.start_session(project.project_id)
        assert session is not None
        assert session.ended_at is None

        # Record work
        pm.record_task_completion(project.project_id, session.session_id, "Designed schema")
        pm.record_task_completion(project.project_id, session.session_id, "Created API routes")
        pm.record_task_failure(project.project_id, session.session_id, "Deploy failed")
        pm.record_decision(project.project_id, session.session_id, "Use PostgreSQL over SQLite")

        ended = pm.end_session(project.project_id, session.session_id, notes="Good progress")
        assert ended is not None
        assert ended.ended_at is not None
        assert len(ended.tasks_completed) == 2
        assert len(ended.tasks_failed) == 1

    def test_milestone_tracking(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        project = pm.create_project(
            "Test", milestones=["Phase 1", "Phase 2", "Phase 3"]
        )
        assert project.progress_percent == 0.0

        pm.reach_milestone(project.project_id, project.milestones[0].milestone_id, "Phase 1 done!")
        loaded = pm.get_project(project.project_id)
        assert loaded.progress_percent == pytest.approx(33.3, abs=0.1)
        assert loaded.milestones_reached == 1

    def test_resume_context(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        project = pm.create_project(
            "Resume Test",
            description="Test resume functionality",
            milestones=["Step 1", "Step 2"],
            context={"database": "postgres", "port": 5432}
        )

        # Simulate a session with work done
        session = pm.start_session(project.project_id)
        pm.record_task_completion(project.project_id, session.session_id, "Set up database")
        pm.record_decision(project.project_id, session.session_id, "Use connection pooling")
        pm.end_session(project.project_id, session.session_id, "DB setup complete")
        pm.reach_milestone(project.project_id, project.milestones[0].milestone_id)

        # Get resume context
        ctx = pm.get_resume_context(project.project_id)
        assert ctx is not None
        assert ctx["project_name"] == "Resume Test"
        assert ctx["total_sessions"] == 1
        assert ctx["last_session"]["tasks_completed"] == ["Set up database"]
        assert ctx["last_session"]["decisions"] == ["Use connection pooling"]
        assert ctx["pending_milestones"] == ["Step 2"]
        assert ctx["context"]["database"] == "postgres"

    def test_complete_project(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        project = pm.create_project("Quick Task")
        pm.complete_project(project.project_id)

        loaded = pm.get_project(project.project_id)
        assert loaded.status == ProjectStatus.COMPLETED
        assert loaded.completed_at is not None

    def test_active_projects_filter(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        p1 = pm.create_project("Active 1")
        p2 = pm.create_project("Active 2")
        p3 = pm.create_project("Completed")
        pm.complete_project(p3.project_id)

        active = pm.get_active_projects()
        assert len(active) == 2

    def test_projects_by_tag(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        pm.create_project("P1", tags=["web", "frontend"])
        pm.create_project("P2", tags=["web", "backend"])
        pm.create_project("P3", tags=["mobile"])

        web_projects = pm.get_projects_by_tag("web")
        assert len(web_projects) == 2

    def test_context_update(self, tmp_path):
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        project = pm.create_project("Test", context={"version": 1})
        pm.update_context(project.project_id, {"version": 2, "deploy_url": "https://app.com"})

        loaded = pm.get_project(project.project_id)
        assert loaded.context["version"] == 2
        assert loaded.context["deploy_url"] == "https://app.com"

    def test_persistence_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "projects.db")
        pm1 = ProjectManager(db_path=db_path)
        project = pm1.create_project("Persistent Project", milestones=["M1"])
        session = pm1.start_session(project.project_id)
        pm1.record_task_completion(project.project_id, session.session_id, "Done something")

        pm2 = ProjectManager(db_path=db_path)
        assert pm2.total_projects() == 1
        loaded = pm2.get_project(project.project_id)
        assert loaded.name == "Persistent Project"
        assert loaded.total_sessions == 1
        assert loaded.total_tasks_completed == 1


# ── 6C: Autonomous Operation ─────────────────────────────────────────


class TestAutonomousOperator:

    def test_check_approval_default_actions(self):
        op = AutonomousOperator()
        assert op.check_approval("search_files") == TaskApproval.APPROVED
        assert op.check_approval("web_search") == TaskApproval.APPROVED
        assert op.check_approval("diagnostic") == TaskApproval.APPROVED

    def test_check_approval_unapproved_action(self):
        op = AutonomousOperator()
        assert op.check_approval("run_command") == TaskApproval.REQUIRES_APPROVAL
        assert op.check_approval("send_sms") == TaskApproval.REQUIRES_APPROVAL

    def test_approve_and_deny_actions(self):
        op = AutonomousOperator()
        op.approve_action("run_command")
        assert op.check_approval("run_command") == TaskApproval.APPROVED

        op.deny_action("run_command")
        assert op.check_approval("run_command") == TaskApproval.REQUIRES_APPROVAL

    def test_queue_and_get_next_task(self):
        op = AutonomousOperator()
        op.queue_task("Find report", "search_files", {"query": "report"})
        op.queue_task("Search web", "web_search", {"query": "trends"})

        task = op.get_next_task()
        assert task is not None
        assert task.approval == TaskApproval.APPROVED

    def test_priority_ordering(self):
        op = AutonomousOperator()
        op.queue_task("Low priority", "search_files", priority="low")
        op.queue_task("Critical", "search_files", priority="critical")
        op.queue_task("Normal", "search_files", priority="normal")

        task = op.get_next_task()
        assert task.priority == "critical"

    def test_unapproved_tasks_not_executed(self):
        op = AutonomousOperator()
        op.queue_task("Run script", "run_command", {"cmd": "ls"})

        # run_command is not approved
        task = op.get_next_task()
        assert task is None  # No approved tasks

        pending = op.get_pending_approval_tasks()
        assert len(pending) == 1

    def test_record_completion(self):
        op = AutonomousOperator()
        task = op.queue_task("Find report", "search_files")
        assert op.record_completion(task.task_id)
        assert len(op._completed) == 1
        assert len(op._task_queue) == 0

    def test_record_failure(self):
        op = AutonomousOperator()
        task = op.queue_task("Find report", "search_files")
        op.record_failure(task.task_id, "File not found")
        assert len(op._failed) == 1

    def test_escalation_after_repeated_failures(self):
        op = AutonomousOperator(max_consecutive_failures=3)
        for i in range(3):
            task = op.queue_task(f"Task {i}", "search_files")
            op.record_failure(task.task_id, f"Failed {i}")

        # Third failure should trigger escalation
        esc = op.record_failure(
            op.queue_task("Task 3", "search_files").task_id,
            "Failed again"
        )
        assert esc is not None
        assert esc.reason == EscalationReason.REPEATED_FAILURE

    def test_no_escalation_below_threshold(self):
        op = AutonomousOperator(max_consecutive_failures=5)
        for i in range(3):
            task = op.queue_task(f"Task {i}", "search_files")
            op.record_failure(task.task_id, "Failed")

        # 3 failures < 5 threshold → no escalation
        unresolved = op.get_unresolved_escalations()
        assert len(unresolved) == 0

    def test_success_resets_consecutive_failures(self):
        op = AutonomousOperator(max_consecutive_failures=3)
        for i in range(2):
            task = op.queue_task(f"Fail {i}", "search_files")
            op.record_failure(task.task_id, "Failed")

        # Success resets counter
        task = op.queue_task("Success", "search_files")
        op.record_completion(task.task_id)
        assert op._consecutive_failures == 0

    def test_manual_escalation(self):
        op = AutonomousOperator()
        esc = op.escalate(
            reason=EscalationReason.UNCERTAIN,
            description="Not sure how to proceed with this task",
            suggested_action="Please provide more context"
        )
        assert esc.reason == EscalationReason.UNCERTAIN
        assert not esc.resolved

    def test_resolve_escalation(self):
        op = AutonomousOperator()
        esc = op.escalate(
            reason=EscalationReason.BLOCKED,
            description="Permission denied"
        )
        assert op.resolve_escalation(esc.escalation_id, "Granted permission")
        unresolved = op.get_unresolved_escalations()
        assert len(unresolved) == 0

    def test_progress_report(self):
        op = AutonomousOperator(report_interval_tasks=2)
        op.queue_task("Task 1", "search_files")
        op.queue_task("Task 2", "web_search")
        op.start_autonomous_session()

        t1 = op.get_next_task()
        op.record_completion(t1.task_id)
        t2 = op.get_next_task()
        op.record_completion(t2.task_id)

        assert op.should_report()
        report = op.generate_report()
        assert report.tasks_completed == 2
        assert report.overall_progress == 1.0

    def test_audit_trail(self):
        op = AutonomousOperator()
        op.queue_task("Task 1", "search_files")
        task = op.get_next_task()
        op.record_completion(task.task_id)

        trail = op.get_audit_trail()
        assert len(trail) >= 2  # queue + execute

    def test_session_lifecycle(self):
        op = AutonomousOperator()
        assert not op.is_operating
        op.start_autonomous_session()
        assert op.is_operating
        op.stop_autonomous_session("all tasks completed")
        assert not op.is_operating

    def test_status_report(self):
        op = AutonomousOperator()
        op.queue_task("T1", "search_files")
        op.queue_task("T2", "run_command")  # unapproved

        status = op.get_status()
        assert status["queue_size"] == 2
        assert status["approved_in_queue"] == 1
        assert status["pending_approval"] == 1

    def test_persistence_audit_trail(self, tmp_path):
        db_path = str(tmp_path / "autonomous.db")
        op1 = AutonomousOperator(db_path=db_path)
        op1.queue_task("Task", "search_files")
        task = op1.get_next_task()
        op1.record_completion(task.task_id)

        op2 = AutonomousOperator(db_path=db_path)
        trail = op2.get_audit_trail()
        assert len(trail) >= 2


# ── Phase 6 Integration ──────────────────────────────────────────────


class TestPhase6Integration:

    def test_decomposition_feeds_project_and_operator(self, tmp_path):
        """Goal decomposition → Project → Autonomous execution."""
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        op = AutonomousOperator()

        # Decompose a goal
        decomp = decomposer.decompose(
            "Research AI trends",
            custom_steps=[
                {"description": "Search local files", "action_type": "search_files", "depends_on": []},
                {"description": "Search web", "action_type": "web_search", "depends_on": []},
                {"description": "Synthesize report", "action_type": "formulate_answer", "depends_on": [0, 1]},
            ]
        )

        # Create project linked to decomposition
        project = pm.create_project(
            "Research AI Trends",
            decomposition_id=decomp.project_id,
            milestones=["Research complete", "Report delivered"]
        )

        # Start session
        session = pm.start_session(project.project_id)

        # Queue ready sub-goals in autonomous operator
        ready = decomp.get_ready_sub_goals()
        for sg in ready:
            op.queue_task(sg.description, sg.action_type, sg.payload, project_id=project.project_id)

        # Execute approved tasks
        while True:
            task = op.get_next_task()
            if not task:
                break
            op.record_completion(task.task_id)
            pm.record_task_completion(project.project_id, session.session_id, task.description)

            # Update decomposition
            for sg in decomp.sub_goals:
                if sg.description == task.description and sg.status == SubGoalStatus.PENDING:
                    decomposer.update_sub_goal(
                        decomp.project_id, sg.sub_goal_id, SubGoalStatus.COMPLETED
                    )
                    break

        # Check progress
        assert op._completed  # Tasks were completed
        report = decomposer.get_progress_report(decomp.project_id)
        assert report["completed"] >= 2  # At least the two independent steps

    def test_full_autonomous_project_lifecycle(self, tmp_path):
        """Create project → decompose → execute autonomously → complete."""
        decomposer = GoalDecomposer(db_path=str(tmp_path / "decomp.db"))
        pm = ProjectManager(db_path=str(tmp_path / "projects.db"))
        op = AutonomousOperator()

        # Setup
        decomp = decomposer.decompose(
            "Setup project",
            custom_steps=[
                {"description": "Check prereqs", "action_type": "diagnostic", "depends_on": []},
                {"description": "Search docs", "action_type": "search_files", "depends_on": [0]},
            ]
        )
        project = pm.create_project("Setup", decomposition_id=decomp.project_id)
        session = pm.start_session(project.project_id)
        op.start_autonomous_session()

        # Execute step 1
        sg1 = decomp.sub_goals[0]
        task1 = op.queue_task(sg1.description, sg1.action_type)
        op.record_completion(task1.task_id)
        decomposer.update_sub_goal(decomp.project_id, sg1.sub_goal_id, SubGoalStatus.COMPLETED)
        pm.record_task_completion(project.project_id, session.session_id, sg1.description)

        # Execute step 2 (now ready)
        ready = decomp.get_ready_sub_goals()
        assert len(ready) == 1
        sg2 = ready[0]
        task2 = op.queue_task(sg2.description, sg2.action_type)
        op.record_completion(task2.task_id)
        decomposer.update_sub_goal(decomp.project_id, sg2.sub_goal_id, SubGoalStatus.COMPLETED)
        pm.record_task_completion(project.project_id, session.session_id, sg2.description)

        # Complete
        assert decomp.is_complete
        assert decomp.is_success
        pm.complete_project(project.project_id)
        op.stop_autonomous_session("project completed")

        # Verify final state
        status = op.get_status()
        assert not status["is_operating"]
        assert status["completed"] == 2

        final_project = pm.get_project(project.project_id)
        assert final_project.status == ProjectStatus.COMPLETED
