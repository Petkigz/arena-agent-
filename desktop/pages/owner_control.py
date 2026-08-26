"""Native desktop Owner Control page.

The page keeps recommendation/approval/execution separate: approving a pending
exact action issues authorization but never executes it; executing an approved
plan requires a different button. Cancellation and rollback requests are also
explicit owner actions.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.styles import _button_style, _input_style, _textarea_style
from desktop.theme import ACCENT, BG_SURFACE, TEXT_MUTED, TEXT_PRIMARY


class OwnerControlPage(QWidget):
    MODES = [
        "observe_only", "suggest_only", "approve_every_action",
        "approve_each_plan", "bounded_autonomy", "custom",
    ]

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._paused = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self.title = QLabel("Owner Control")
        layout.addWidget(self.title)
        self.explanation = QLabel(
            "Approval authorizes only the exact recommendation. It does not execute it. "
            "Plan execution, cancellation, and rollback are separate actions."
        )
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)

        policy_row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(self.MODES)
        policy_row.addWidget(QLabel("Mode"))
        policy_row.addWidget(self.mode, 1)
        self.safety = QSpinBox()
        self.safety.setRange(0, 2)
        policy_row.addWidget(QLabel("Autonomous safety ceiling"))
        policy_row.addWidget(self.safety)
        self.exploration = QSpinBox()
        self.exploration.setRange(0, 10)
        policy_row.addWidget(QLabel("Exploration cap"))
        policy_row.addWidget(self.exploration)
        layout.addLayout(policy_row)

        actions = QHBoxLayout()
        self.save_btn = QPushButton("Save policy")
        self.save_btn.clicked.connect(self._save_policy)
        actions.addWidget(self.save_btn)
        self.pause_btn = QPushButton("Emergency pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        actions.addWidget(self.pause_btn)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._manual_refresh)
        actions.addWidget(self.refresh_btn)
        layout.addLayout(actions)

        columns = QHBoxLayout()
        self.approvals = self._section(columns, "Pending exact-action approvals")
        self.plans = self._section(columns, "Plan reviews")
        self.executions = self._section(columns, "Execution history")
        layout.addLayout(columns, 1)

        authorization_row = QHBoxLayout()
        authorization_column = QVBoxLayout()
        authorization_column.addWidget(QLabel("Active exact-scope authorizations"))
        self.authorizations = QListWidget()
        self.authorizations.setFixedHeight(95)
        authorization_column.addWidget(self.authorizations)
        authorization_row.addLayout(authorization_column, 1)
        self.execute_authorization_btn = QPushButton("Execute selected authorization")
        self.execute_authorization_btn.clicked.connect(self._execute_authorization)
        authorization_row.addWidget(self.execute_authorization_btn)
        self.revoke_authorization_btn = QPushButton("Revoke selected authorization")
        self.revoke_authorization_btn.clicked.connect(self._revoke_authorization)
        authorization_row.addWidget(self.revoke_authorization_btn)
        layout.addLayout(authorization_row)

        approval_actions = QHBoxLayout()
        self.approve_btn = QPushButton("Approve selected")
        self.approve_btn.clicked.connect(lambda: self._decide_approval(True))
        approval_actions.addWidget(self.approve_btn)
        self.reject_btn = QPushButton("Reject selected")
        self.reject_btn.clicked.connect(lambda: self._decide_approval(False))
        approval_actions.addWidget(self.reject_btn)
        self.plan_approve_btn = QPushButton("Approve plan")
        self.plan_approve_btn.clicked.connect(lambda: self._decide_plan(True))
        approval_actions.addWidget(self.plan_approve_btn)
        self.plan_reject_btn = QPushButton("Reject plan")
        self.plan_reject_btn.clicked.connect(lambda: self._decide_plan(False))
        approval_actions.addWidget(self.plan_reject_btn)
        self.plan_execute_btn = QPushButton("Execute approved plan")
        self.plan_execute_btn.clicked.connect(self._execute_plan)
        approval_actions.addWidget(self.plan_execute_btn)
        layout.addLayout(approval_actions)

        execution_actions = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel selected execution")
        self.cancel_btn.clicked.connect(self._cancel_execution)
        execution_actions.addWidget(self.cancel_btn)
        self.rollback_btn = QPushButton("Request rollback approval")
        self.rollback_btn.clicked.connect(self._request_rollback)
        execution_actions.addWidget(self.rollback_btn)
        layout.addLayout(execution_actions)

        # ── Autonomy operations ──────────────────────────────────────────────
        # Newest owner surfaces: goal queue + schedules, run timeline with
        # commitment/recovery links, preemption reconciliation, concurrency
        # budget, and signed owner decisions for expected identity changes.
        self.autonomy_tabs = QTabWidget()
        self.autonomy_tabs.addTab(self._build_goals_tab(), "Goals & schedule")
        self.autonomy_tabs.addTab(self._build_runs_tab(), "Runs & timeline")
        self.autonomy_tabs.addTab(self._build_preemptions_tab(), "Preemptions")
        self.autonomy_tabs.addTab(self._build_budgets_tab(), "Budgets & decisions")
        self.autonomy_tabs.addTab(self._build_cognition_tab(), "Cognition")
        layout.addWidget(self.autonomy_tabs, 1)

        layout.addWidget(QLabel("Selected plan steps JSON (editable before execution)"))
        self.plan_editor = QTextEdit()
        self.plan_editor.setFixedHeight(170)
        layout.addWidget(self.plan_editor)
        self.save_plan_edits_btn = QPushButton("Save selected plan as a new revision")
        self.save_plan_edits_btn.clicked.connect(self._save_plan_edits)
        layout.addWidget(self.save_plan_edits_btn)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFixedHeight(150)
        layout.addWidget(self.detail)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        for widget in (self.approvals, self.executions, self.authorizations):
            widget.itemClicked.connect(self._show_detail)
        self.plans.itemClicked.connect(self._show_plan_detail)
        self.refresh_theme()
        self.refresh()

    @staticmethod
    def _section(parent_layout, title):
        column = QVBoxLayout()
        column.addWidget(QLabel(title))
        listing = QListWidget()
        column.addWidget(listing, 1)
        parent_layout.addLayout(column, 1)
        return listing

    @staticmethod
    def _data(item):
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected(self, listing):
        return self._data(listing.currentItem())

    def _show_detail(self, item):
        data = self._data(item)
        self.detail.setPlainText(json.dumps(data or {}, indent=2, ensure_ascii=False))

    def _show_plan_detail(self, item):
        plan = self._data(item) or {}
        self.detail.setPlainText(json.dumps(plan, indent=2, ensure_ascii=False))
        steps = plan.get("snapshot", {}).get("steps", [])
        self.plan_editor.setPlainText(json.dumps(steps, indent=2, ensure_ascii=False))

    # ── autonomy operations: tab construction ───────────────────────────────

    def _build_goals_tab(self):
        tab = QWidget()
        column = QVBoxLayout(tab)
        self.goals = QListWidget()
        column.addWidget(QLabel("Autonomous goal queue (owner priorities are authoritative)"))
        column.addWidget(self.goals, 1)
        goal_buttons = QHBoxLayout()
        self.goal_approve_btn = QPushButton("Approve for planning")
        self.goal_approve_btn.clicked.connect(lambda: self._decide_goal(True))
        goal_buttons.addWidget(self.goal_approve_btn)
        self.goal_reject_btn = QPushButton("Reject goal")
        self.goal_reject_btn.clicked.connect(lambda: self._decide_goal(False))
        goal_buttons.addWidget(self.goal_reject_btn)
        self.goal_defer_btn = QPushButton("Defer goal")
        self.goal_defer_btn.clicked.connect(self._defer_goal)
        goal_buttons.addWidget(self.goal_defer_btn)
        self.goal_execute_next_btn = QPushButton("Execute next approved goal")
        self.goal_execute_next_btn.clicked.connect(self._execute_next_goal)
        goal_buttons.addWidget(self.goal_execute_next_btn)
        self.allocation_btn = QPushButton("Show allocation preview")
        self.allocation_btn.clicked.connect(self._show_allocation)
        goal_buttons.addWidget(self.allocation_btn)
        column.addLayout(goal_buttons)

        directive = QHBoxLayout()
        self.goal_title = QLineEdit()
        self.goal_title.setPlaceholderText("Directive title")
        directive.addWidget(self.goal_title, 2)
        self.goal_priority = QComboBox()
        self.goal_priority.addItems(["critical", "high", "normal", "low"])
        directive.addWidget(self.goal_priority)
        self.goal_create_btn = QPushButton("Create directive")
        self.goal_create_btn.clicked.connect(self._create_goal)
        directive.addWidget(self.goal_create_btn)
        column.addLayout(directive)

        schedule = QHBoxLayout()
        self.schedule_run_at = QLineEdit()
        self.schedule_run_at.setPlaceholderText("Next run ISO time (e.g. 2026-08-25T09:00:00)")
        schedule.addWidget(self.schedule_run_at, 2)
        self.schedule_recurrence = QComboBox()
        self.schedule_recurrence.addItems(["none", "daily", "weekly"])
        schedule.addWidget(self.schedule_recurrence)
        self.schedule_tz = QLineEdit("Africa/Kampala")
        schedule.addWidget(self.schedule_tz)
        self.schedule_create_btn = QPushButton("Schedule directive")
        self.schedule_create_btn.clicked.connect(self._create_schedule)
        schedule.addWidget(self.schedule_create_btn)
        column.addLayout(schedule)
        return tab

    def _build_runs_tab(self):
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.addWidget(QLabel("Autonomy run events (select one to load its cycle timeline with commitment/recovery links)"))
        self.runs = QListWidget()
        self.runs.itemClicked.connect(self._show_run_timeline)
        column.addWidget(self.runs, 1)
        column.addWidget(QLabel("Autonomy envelope JSON (optional limits; grants no new authority)"))
        self.envelope_editor = QTextEdit()
        self.envelope_editor.setFixedHeight(110)
        column.addWidget(self.envelope_editor)
        self.envelope_save_btn = QPushButton("Save envelope")
        self.envelope_save_btn.clicked.connect(self._save_envelope)
        column.addWidget(self.envelope_save_btn)
        return tab

    def _build_preemptions_tab(self):
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.addWidget(QLabel("Owner preemptions — reconcile before resume; verified steps are skipped, unknown halts for evidence"))
        self.preemptions = QListWidget()
        column.addWidget(self.preemptions, 1)
        preemption_buttons = QHBoxLayout()
        self.preemption_refresh_btn = QPushButton("Refresh selected")
        self.preemption_refresh_btn.clicked.connect(self._refresh_preemption)
        preemption_buttons.addWidget(self.preemption_refresh_btn)
        self.preemption_reconcile_btn = QPushButton("Reconcile (observation only)")
        self.preemption_reconcile_btn.clicked.connect(self._reconcile_preemption)
        preemption_buttons.addWidget(self.preemption_reconcile_btn)
        self.preemption_resume_btn = QPushButton("Request resume")
        self.preemption_resume_btn.clicked.connect(self._request_preemption_resume)
        preemption_buttons.addWidget(self.preemption_resume_btn)
        column.addLayout(preemption_buttons)
        create_row = QHBoxLayout()
        self.preempt_execution_id = QLineEdit()
        self.preempt_execution_id.setPlaceholderText("Execution ID to preempt")
        create_row.addWidget(self.preempt_execution_id, 2)
        self.preempt_urgent_goal = QLineEdit()
        self.preempt_urgent_goal.setPlaceholderText("Urgent goal ID")
        create_row.addWidget(self.preempt_urgent_goal, 2)
        self.preempt_plan_id = QLineEdit()
        self.preempt_plan_id.setPlaceholderText("Plan ID (optional)")
        create_row.addWidget(self.preempt_plan_id, 2)
        self.preempt_create_btn = QPushButton("Preempt execution")
        self.preempt_create_btn.clicked.connect(self._create_preemption)
        create_row.addWidget(self.preempt_create_btn)
        column.addLayout(create_row)
        return tab

    def _build_budgets_tab(self):
        tab = QWidget()
        column = QVBoxLayout(tab)
        self.budget_label = QLabel("Measured worker budget: unknown")
        self.budget_label.setWordWrap(True)
        column.addWidget(self.budget_label)
        budget_row = QHBoxLayout()
        self.budget_override = QCheckBox("Override worker budget")
        budget_row.addWidget(self.budget_override)
        self.budget_workers = QSpinBox()
        self.budget_workers.setRange(1, 256)
        budget_row.addWidget(self.budget_workers)
        self.budget_apply_btn = QPushButton("Apply budget")
        self.budget_apply_btn.clicked.connect(self._apply_budget)
        budget_row.addWidget(self.budget_apply_btn)
        self.budget_reset_btn = QPushButton("Reset to measured")
        self.budget_reset_btn.clicked.connect(self._reset_budget)
        budget_row.addWidget(self.budget_reset_btn)
        self.budget_receipts_btn = QPushButton("Show receipts")
        self.budget_receipts_btn.clicked.connect(self._show_budget_receipts)
        budget_row.addWidget(self.budget_receipts_btn)
        column.addLayout(budget_row)

        column.addWidget(QLabel("Signed owner decisions (expected identity changes; single-use, revocable)"))
        self.decisions = QListWidget()
        column.addWidget(self.decisions, 1)
        decision_row = QHBoxLayout()
        self.decision_types = QLineEdit()
        self.decision_types.setPlaceholderText("Expected change types, comma separated (e.g. provider_model_changed)")
        decision_row.addWidget(self.decision_types, 2)
        self.decision_issue_btn = QPushButton("Issue decision")
        self.decision_issue_btn.clicked.connect(self._issue_decision)
        decision_row.addWidget(self.decision_issue_btn)
        self.decision_revoke_btn = QPushButton("Revoke selected")
        self.decision_revoke_btn.clicked.connect(self._revoke_decision)
        decision_row.addWidget(self.decision_revoke_btn)
        column.addLayout(decision_row)
        return tab

    # ── cognition tab ────────────────────────────────────────────────────────

    def _build_cognition_tab(self):
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.addWidget(QLabel("Owner Charter (informs every cycle; policy gates remain the authority)"))
        self.charter_mission = QTextEdit()
        self.charter_mission.setFixedHeight(52)
        self.charter_mission.setPlaceholderText("Mission")
        column.addWidget(self.charter_mission)
        self.charter_priorities = QTextEdit()
        self.charter_priorities.setFixedHeight(66)
        self.charter_priorities.setPlaceholderText("Priorities — one per line, highest first")
        column.addWidget(self.charter_priorities)
        self.charter_directives = QTextEdit()
        self.charter_directives.setFixedHeight(66)
        self.charter_directives.setPlaceholderText("Standing directives — one per line")
        column.addWidget(self.charter_directives)
        charter_row = QHBoxLayout()
        self.charter_save_btn = QPushButton("Save charter")
        self.charter_save_btn.clicked.connect(self._save_charter)
        charter_row.addWidget(self.charter_save_btn)
        self.charter_label = QLabel("revision —")
        charter_row.addWidget(self.charter_label)
        column.addLayout(charter_row)

        column.addWidget(QLabel("Uncertainty questions (approve authorizes exactly; it never executes)"))
        self.questions = QListWidget()
        column.addWidget(self.questions, 1)
        question_row = QHBoxLayout()
        for label, answer in (("Approve exactly", "approve"), ("Deny", "deny"), ("Observe more", "observe")):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, a=answer: self._answer_question(a))
            question_row.addWidget(button)
        column.addLayout(question_row)

        column.addWidget(QLabel("Induced skills (mined from repeated verified successes; accept teaches, gates still apply)"))
        self.induced = QListWidget()
        column.addWidget(self.induced, 1)
        skill_row = QHBoxLayout()
        self.skill_accept_btn = QPushButton("Accept skill")
        self.skill_accept_btn.clicked.connect(lambda: self._decide_induced_skill(True))
        skill_row.addWidget(self.skill_accept_btn)
        self.skill_reject_btn = QPushButton("Reject")
        self.skill_reject_btn.clicked.connect(lambda: self._decide_induced_skill(False))
        skill_row.addWidget(self.skill_reject_btn)
        self.skill_scan_btn = QPushButton("Rescan")
        self.skill_scan_btn.clicked.connect(self._scan_induced_skills)
        skill_row.addWidget(self.skill_scan_btn)
        column.addLayout(skill_row)

        self.learning_label = QLabel("Learning progress: unknown")
        self.learning_label.setWordWrap(True)
        column.addWidget(self.learning_label)
        self.owner_model_label = QLabel("Owner patterns: not counted yet")
        self.owner_model_label.setWordWrap(True)
        column.addWidget(self.owner_model_label)
        return tab

    def _save_charter(self):
        try:
            patch = {
                "mission": self.charter_mission.toPlainText().strip(),
                "priorities": [line.strip() for line in self.charter_priorities.toPlainText().splitlines() if line.strip()],
                "standing_directives": [line.strip() for line in self.charter_directives.toPlainText().splitlines() if line.strip()],
            }
            result = self._client.update_owner_charter(patch)
            charter = result.get("charter", {})
            self.charter_label.setText(f"revision {charter.get('revision', '?')}")
            self.status.setText("Charter saved; it informs reasoning and grants no authority")
        except Exception as exc:
            self.status.setText(f"Charter save failed: {exc}")

    def _answer_question(self, answer):
        question = self._selected(self.questions)
        if not question:
            return
        try:
            result = self._client.answer_owner_question(question["question_id"], answer)
            if answer == "approve" and result.get("approval_action_id"):
                self.status.setText(f"Exact approval {result['approval_action_id']} created; nothing executed")
            else:
                self.status.setText(f"Answer recorded: {answer}")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Answer failed: {exc}")

    def _decide_induced_skill(self, accept):
        candidate = self._selected(self.induced)
        if not candidate:
            return
        try:
            if accept:
                self._client.accept_induced_skill(candidate["candidate_id"])
                self.status.setText("Skill accepted into the taught library; execution still passes all gates")
            else:
                self._client.reject_induced_skill(candidate["candidate_id"])
                self.status.setText("Candidate rejected")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Skill decision failed: {exc}")

    def _scan_induced_skills(self):
        try:
            result = self._client.scan_induced_skills()
            self.status.setText(f"Scan: {result.get('candidates_created', '?')} new candidate(s), {result.get('plans_scanned', '?')} plans")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Scan failed: {exc}")

    def _refresh_cognition(self):
        try:
            data = self._client.owner_charter()
            charter = data.get("charter", {})
            self.charter_label.setText(f"revision {charter.get('revision', 0)}")
            if not self.charter_mission.toPlainText().strip():
                self.charter_mission.setPlainText(str(charter.get("mission", "")))
                self.charter_priorities.setPlainText("\n".join(charter.get("priorities", [])))
                self.charter_directives.setPlainText("\n".join(charter.get("standing_directives", [])))
        except Exception as exc:
            self.status.setText(f"Could not load charter: {exc}")
        try:
            self.questions.clear()
            for question in self._client.owner_questions().get("questions", []):
                item = QListWidgetItem(
                    f"{question.get('action_type', '')} [{round(float(question.get('calibrated_confidence', 0)) * 100)}%] {question.get('question_text', '')[:70]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, question)
                self.questions.addItem(item)
        except Exception as exc:
            self.status.setText(f"Could not load questions: {exc}")
        try:
            self.induced.clear()
            for candidate in self._client.induced_skills().get("candidates", []):
                item = QListWidgetItem(
                    f"{candidate.get('skill_name', '')} [{candidate.get('occurrences', 0)}x → {' → '.join(candidate.get('action_sequence', [])[:3])}]"
                )
                item.setData(Qt.ItemDataRole.UserRole, candidate)
                self.induced.addItem(item)
        except Exception as exc:
            self.status.setText(f"Could not load induced skills: {exc}")
        try:
            targets = self._client.learning_progress().get("targets", [])
            if targets:
                rendered = "; ".join(
                    f"{t.get('action_type')}({t.get('status')}, value {t.get('learning_value', 0):.2f})"
                    for t in targets[:5]
                )
                self.learning_label.setText(f"Learning progress: {rendered}")
            else:
                self.learning_label.setText("Learning progress: no measured domains yet")
        except Exception as exc:
            self.learning_label.setText(f"Learning progress unavailable: {exc}")
        try:
            report = self._client.owner_model_report()
            approves = ", ".join(report.get("consistently_approves", [])[:4]) or "—"
            denies = ", ".join(report.get("consistently_denies", [])[:4]) or "—"
            self.owner_model_label.setText(f"Owner patterns (counted): approves {approves}; denies {denies}")
        except Exception as exc:
            self.owner_model_label.setText(f"Owner patterns unavailable: {exc}")

    # ── autonomy operations: data + handlers ────────────────────────────────

    def _refresh_autonomy(self):
        try:
            self.goals.clear()
            for goal in self._client.autonomous_goals().get("goals", []):
                item = QListWidgetItem(
                    f"{goal.get('title', goal.get('goal_id', ''))} [{goal.get('status', '')}/{goal.get('priority', '')}]"
                )
                item.setData(Qt.ItemDataRole.UserRole, goal)
                self.goals.addItem(item)
        except Exception as exc:
            self.status.setText(f"Could not load goal queue: {exc}")
        try:
            self.runs.clear()
            for event in self._client.autonomy_run_events(limit=100).get("events", []):
                item = QListWidgetItem(
                    f"{event.get('cycle_id', '')[:18]} {event.get('stage', '')} {event.get('created_at', '')[:19]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, event)
                self.runs.addItem(item)
        except Exception as exc:
            self.status.setText(f"Could not load run events: {exc}")
        try:
            envelope = self._client.autonomy_envelope().get("envelope", {})
            if not self.envelope_editor.toPlainText().strip():
                self.envelope_editor.setPlainText(json.dumps(envelope, indent=2, ensure_ascii=False))
        except Exception as exc:
            self.status.setText(f"Could not load autonomy envelope: {exc}")
        try:
            self.preemptions.clear()
            for preemption in self._client.preemptions().get("preemptions", []):
                item = QListWidgetItem(
                    f"{preemption.get('preemption_id', '')[:22]} [{preemption.get('status', '')}] {preemption.get('reason', '')[:40]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, preemption)
                self.preemptions.addItem(item)
        except Exception as exc:
            self.status.setText(f"Could not load preemptions: {exc}")
        try:
            budget = self._client.concurrency_budget().get("budget", {})
            self.budget_label.setText(
                "Measured worker budget: %s granted of %s configured (physical cap %s) — %s"
                % (
                    budget.get("workers_granted"), budget.get("configured_budget"),
                    budget.get("physical_thread_cap"),
                    "; ".join(budget.get("reasons", [])) or "no pressure scaling",
                )
            )
        except Exception as exc:
            self.budget_label.setText(f"Measured worker budget unavailable: {exc}")
        try:
            self.decisions.clear()
            for decision in self._client.owner_decisions().get("decisions", []):
                item = QListWidgetItem(
                    f"{decision.get('decision_id', '')[:20]} [{decision.get('status', '')}] "
                    + ",".join(decision.get("payload", {}).get("expected_change_types", []))
                )
                item.setData(Qt.ItemDataRole.UserRole, decision)
                self.decisions.addItem(item)
        except Exception as exc:
            self.status.setText(f"Could not load owner decisions: {exc}")

    def _decide_goal(self, approved):
        goal = self._selected(self.goals)
        if not goal:
            return
        try:
            self._client.decide_autonomous_goal(goal["goal_id"], approved)
            self.status.setText("Goal decision recorded; planning only — execution stays separate")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Goal decision failed: {exc}")

    def _defer_goal(self):
        goal = self._selected(self.goals)
        if not goal:
            return
        try:
            self._client.defer_autonomous_goal(goal["goal_id"])
            self.status.setText("Goal deferred by owner priority")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Defer failed: {exc}")

    def _execute_next_goal(self):
        try:
            result = self._client.execute_next_autonomous_goal()
            self.status.setText(f"Execute-next returned: {result.get('status', result.get('success'))}")
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Execute-next failed: {exc}")

    def _show_allocation(self):
        try:
            preview = self._client.allocation_preview()
            self.detail.setPlainText(json.dumps(preview, indent=2, ensure_ascii=False))
        except Exception as exc:
            self.status.setText(f"Allocation preview failed: {exc}")

    def _create_goal(self):
        title = self.goal_title.text().strip()
        if not title:
            self.status.setText("Directive title is required")
            return
        try:
            self._client.create_autonomous_goal(title, "", self.goal_priority.currentText())
            self.status.setText("Directive created; it authorizes planning only")
            self.goal_title.clear()
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Create directive failed: {exc}")

    def _create_schedule(self):
        title = self.goal_title.text().strip()
        run_at = self.schedule_run_at.text().strip()
        if not title or not run_at:
            self.status.setText("Directive title and next run time are required")
            return
        try:
            self._client.create_scheduled_directive(
                title, run_at, self.schedule_recurrence.currentText(), self.schedule_tz.text().strip() or "UTC"
            )
            self.status.setText("Scheduled directive created; it authorizes planning only")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Schedule creation failed: {exc}")

    def _show_run_timeline(self, item):
        event = self._data(item) or {}
        cycle_id = event.get("cycle_id")
        if not cycle_id:
            return
        try:
            timeline = self._client.autonomy_cycle_timeline(cycle_id)
            self.detail.setPlainText(json.dumps(timeline, indent=2, ensure_ascii=False))
        except Exception as exc:
            self.status.setText(f"Timeline load failed: {exc}")

    def _save_envelope(self):
        try:
            patch = json.loads(self.envelope_editor.toPlainText() or "{}")
            if not isinstance(patch, dict):
                raise ValueError("Envelope must be a JSON object")
            self._client.update_autonomy_envelope(patch)
            self.status.setText("Envelope saved; limits constrain future cycles and grant no new authority")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Envelope save failed: {exc}")

    def _create_preemption(self):
        execution_id = self.preempt_execution_id.text().strip()
        urgent = self.preempt_urgent_goal.text().strip()
        if not execution_id or not urgent:
            self.status.setText("Execution ID and urgent goal ID are required")
            return
        try:
            plan_id = self.preempt_plan_id.text().strip() or None
            self._client.create_preemption(execution_id, urgent, plan_id=plan_id)
            self.status.setText("Preemption requested; resume requires reconciliation")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Preemption creation failed: {exc}")

    def _refresh_preemption(self):
        preemption = self._selected(self.preemptions)
        if not preemption:
            return
        try:
            result = self._client.refresh_preemption(preemption["preemption_id"])
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Preemption refresh failed: {exc}")

    def _reconcile_preemption(self):
        preemption = self._selected(self.preemptions)
        if not preemption:
            return
        try:
            result = self._client.reconcile_preemption(preemption["preemption_id"])
            body = result.get("reconciliation", {})
            step_update = result.get("step_status_update", {})
            self.status.setText(
                "Reconciliation: %s — step now %s (nothing executed)"
                % (body.get("resume_recommendation"), step_update.get("status"))
            )
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Reconciliation failed: {exc}")

    def _request_preemption_resume(self):
        preemption = self._selected(self.preemptions)
        if not preemption:
            return
        try:
            result = self._client.request_preemption_resume(preemption["preemption_id"])
            self.status.setText("Resume requested; separately execute the approved plan")
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Resume request failed: {exc}")

    def _apply_budget(self):
        if not self.budget_override.isChecked():
            self.status.setText("Check 'Override worker budget' to set a fixed budget")
            return
        try:
            self._client.set_concurrency_budget(enabled=True, max_workers=self.budget_workers.value())
            self.status.setText("Owner worker budget applied (clamped to physical threads; critical pressure still wins)")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Budget apply failed: {exc}")

    def _reset_budget(self):
        try:
            self._client.set_concurrency_budget(enabled=True, max_workers=None)
            self.status.setText("Worker budget reset to measured defaults")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Budget reset failed: {exc}")

    def _show_budget_receipts(self):
        try:
            receipts = self._client.concurrency_receipts(limit=20)
            self.detail.setPlainText(json.dumps(receipts, indent=2, ensure_ascii=False))
        except Exception as exc:
            self.status.setText(f"Receipts load failed: {exc}")

    def _issue_decision(self):
        raw = [part.strip() for part in self.decision_types.text().split(",") if part.strip()]
        if not raw:
            self.status.setText("List at least one expected change type")
            return
        try:
            result = self._client.issue_owner_decision(raw)
            decision = result.get("decision", {})
            self.status.setText(
                "Decision %s issued (single-use); pass its ID to the identity checkpoint" % decision.get("decision_id")
            )
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Decision issue failed: {exc}")

    def _revoke_decision(self):
        decision = self._selected(self.decisions)
        if not decision:
            return
        try:
            self._client.revoke_owner_decision(decision["decision_id"])
            self.status.setText("Decision revoked")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Decision revoke failed: {exc}")

    def _manual_refresh(self):
        self.status.setText("")
        self.refresh()

    def refresh(self):
        try:
            policy = self._client.owner_control().get("policy", {})
            self._paused = bool(policy.get("paused", False))
            self.mode.setCurrentText(str(policy.get("mode", "approve_every_action")))
            self.safety.setValue(int(policy.get("max_autonomous_level", 0)))
            adaptive = self._client.adaptive_autonomy().get("profile", {})
            self.exploration.setValue(int(adaptive.get("owner_max_exploration_goals", 0)))
            self.pause_btn.setText("Resume under policy" if self._paused else "Emergency pause")

            self.approvals.clear()
            for approval in self._client.pending_approvals().get("approvals", []):
                item = QListWidgetItem(
                    f"{approval.get('action_type', '')}: {approval.get('reason', '')[:60]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, approval)
                self.approvals.addItem(item)

            self.authorizations.clear()
            for authorization in self._client.active_authorizations().get("authorizations", []):
                scope = "executable" if authorization.get("scope_recoverable") else "scope unavailable"
                item = QListWidgetItem(
                    f"{authorization.get('action_type', '')} [{scope}] expires {authorization.get('expires_at', '')}"
                )
                item.setData(Qt.ItemDataRole.UserRole, authorization)
                self.authorizations.addItem(item)

            self.plans.clear()
            for plan in self._client.reviewed_plans().get("plans", []):
                item = QListWidgetItem(
                    f"{plan.get('goal_title', plan.get('plan_id', ''))} [{plan.get('status', '')}] r{plan.get('revision', 0)}"
                )
                item.setData(Qt.ItemDataRole.UserRole, plan)
                self.plans.addItem(item)

            self.executions.clear()
            for execution in self._client.controlled_executions().get("executions", []):
                item = QListWidgetItem(
                    f"{execution.get('action_type', '')} [{execution.get('status', '')}]"
                )
                item.setData(Qt.ItemDataRole.UserRole, execution)
                self.executions.addItem(item)
            if not self.status.text():
                self.status.setText("Owner-control state refreshed")
        except Exception as exc:
            self.status.setText(f"Could not load Owner Control: {exc}")
        self._refresh_autonomy()
        self._refresh_cognition()

    def _save_policy(self):
        try:
            self._client.update_owner_control({
                "mode": self.mode.currentText(),
                "max_autonomous_level": self.safety.value(),
            })
            self._client.set_exploration_budget(self.exploration.value())
            self.status.setText("Policy saved; this did not authorize or execute an action")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Could not save policy: {exc}")

    def _toggle_pause(self):
        try:
            self._client.set_emergency_pause(not self._paused)
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Could not change pause state: {exc}")

    def _decide_approval(self, approved):
        approval = self._selected(self.approvals)
        if not approval:
            return
        try:
            self._client.decide_approval(approval["action_id"], approved, "Desktop owner decision")
            self.status.setText(
                "Exact recommendation authorized; nothing executed"
                if approved else "Recommendation rejected"
            )
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Approval decision failed: {exc}")

    def _execute_authorization(self):
        authorization = self._selected(self.authorizations)
        if not authorization:
            return
        if not authorization.get("scope_recoverable"):
            self.status.setText(
                "This direct grant has no recoverable reviewed payload; execute it only from the client that issued it"
            )
            return
        try:
            result = self._client.execute_authorized(
                authorization["authorization_id"], authorization["action_type"],
                authorization["payload"], authorization.get("plan_id"),
            )
            self.status.setText(
                "Execution returned: tool success=%s, goal verified=%s, verification unknown=%s"
                % (
                    result.get("execution_success"), result.get("goal_verified"),
                    result.get("verification_unknown"),
                )
            )
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Authorized execution failed: {exc}")

    def _revoke_authorization(self):
        authorization = self._selected(self.authorizations)
        if not authorization:
            return
        try:
            self._client.revoke_authorization(authorization["authorization_id"])
            self.status.setText("Authorization revoked without execution")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Could not revoke authorization: {exc}")

    def _save_plan_edits(self):
        plan = self._selected(self.plans)
        if not plan:
            return
        try:
            steps = json.loads(self.plan_editor.toPlainText())
            if not isinstance(steps, list) or not steps:
                raise ValueError("Plan steps must be a non-empty JSON array")
            result = self._client.edit_plan(
                plan["plan_id"], int(plan["revision"]), steps
            )
            updated = result.get("plan", {})
            self.status.setText(
                f"Plan edits saved as revision {updated.get('revision', '?')}; not approved or executed"
            )
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Could not save plan edits: {exc}")

    def _decide_plan(self, approved):
        plan = self._selected(self.plans)
        if not plan:
            return
        try:
            self._client.decide_plan(
                plan["plan_id"], int(plan["revision"]), approved, "Desktop owner decision"
            )
            self.status.setText("Plan decision recorded; no plan was executed")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Plan decision failed: {exc}")

    def _execute_plan(self):
        plan = self._selected(self.plans)
        if not plan:
            return
        try:
            result = self._client.execute_plan(plan["plan_id"])
            self.status.setText(
                f"Separate plan execution request returned: {result.get('plan_status', result.get('success'))}"
            )
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Plan execution failed: {exc}")

    def _cancel_execution(self):
        execution = self._selected(self.executions)
        if not execution:
            return
        try:
            self._client.cancel_execution(execution["execution_id"])
            self.status.setText("Cooperative cancellation requested; prior side effects may exist")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Cancellation request failed: {exc}")

    def _request_rollback(self):
        execution = self._selected(self.executions)
        if not execution:
            return
        try:
            self._client.request_rollback(execution["execution_id"])
            self.status.setText("Rollback compensation added to approvals; it was not executed")
            self.refresh()
        except Exception as exc:
            self.status.setText(f"Rollback request failed: {exc}")

    def refresh_theme(self):
        self.title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.explanation.setStyleSheet(f"color: {TEXT_MUTED};")
        self.status.setStyleSheet(f"color: {TEXT_MUTED};")
        self.mode.setStyleSheet(_input_style())
        self.detail.setStyleSheet(_textarea_style())
        self.plan_editor.setStyleSheet(_textarea_style())
        self.envelope_editor.setStyleSheet(_textarea_style())
        self.goal_title.setStyleSheet(_input_style())
        self.schedule_run_at.setStyleSheet(_input_style())
        self.schedule_tz.setStyleSheet(_input_style())
        self.preempt_execution_id.setStyleSheet(_input_style())
        self.preempt_urgent_goal.setStyleSheet(_input_style())
        self.preempt_plan_id.setStyleSheet(_input_style())
        self.decision_types.setStyleSheet(_input_style())
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(_button_style(ACCENT if button is self.pause_btn else BG_SURFACE, TEXT_PRIMARY))
