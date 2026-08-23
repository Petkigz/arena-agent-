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
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
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
        self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_btn)
        layout.addLayout(actions)

        columns = QHBoxLayout()
        self.approvals = self._section(columns, "Pending exact-action approvals")
        self.plans = self._section(columns, "Plan reviews")
        self.executions = self._section(columns, "Execution history")
        layout.addLayout(columns, 1)

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

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFixedHeight(150)
        layout.addWidget(self.detail)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        for widget in (self.approvals, self.plans, self.executions):
            widget.itemClicked.connect(self._show_detail)
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

    def refresh(self):
        try:
            policy = self._client.owner_control().get("policy", {})
            self._paused = bool(policy.get("paused", False))
            self.mode.setCurrentText(str(policy.get("mode", "approve_every_action")))
            self.safety.setValue(int(policy.get("max_autonomous_safety_level", 0)))
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
            self.status.setText("Owner-control state refreshed")
        except Exception as exc:
            self.status.setText(f"Could not load Owner Control: {exc}")

    def _save_policy(self):
        try:
            self._client.update_owner_control({
                "mode": self.mode.currentText(),
                "max_autonomous_safety_level": self.safety.value(),
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
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(_button_style(ACCENT if button is self.pause_btn else BG_SURFACE, TEXT_PRIMARY))
