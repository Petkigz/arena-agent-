"""ContextPanel — extracted from monolithic app.py."""

from __future__ import annotations

import math
import sys
from typing import List, Optional

from PySide6.QtCore import Property, QBuffer, QEasingCurve, QIODevice, QPointF, QPropertyAnimation, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.settings import DesktopSettings
from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, PRESENCE_COLORS, PRESENCE_DURATIONS, _lighten
from desktop.styles import _button_style, _input_style, _textarea_style
from desktop.widgets.orb import PresenceOrbWidget
from desktop.workers import ChatWorker, HealthWorker, LocationWorker, VisionWorker, CameraThread, CV2_AVAILABLE



class ContextPanel(QFrame):
    """Live Context rail — the agent's mind, always visible (21l review).

    The desktop is the command center: the right rail shows what Beanie is
    doing — Mission, Working on, Memory, Tools — fed by the same context the
    inline working-context card composes from, plus the streamed action_step
    events the web renders as ActionSteps and Android as ToolActivity.
    One product, three shells: same sections, device-appropriate density.

    Progressive context (round-21c): collapsible; the choice persists via settings.
    """

    EXPANDED_WIDTH = 240
    COLLAPSED_WIDTH = 36

    def __init__(self, parent=None, collapsed: bool = False, on_collapsed=None):
        super().__init__(parent)
        self._on_collapsed = on_collapsed
        self._collapsed = False
        self.setFixedWidth(self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH)
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BORDER_SUBTLE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._title = QLabel("Context")
        self._title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        header.addWidget(self._title)
        header.addStretch(1)
        self._toggle_btn = QPushButton("▾")
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(self._toggle_style())
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        header.addWidget(self._toggle_btn)
        layout.addLayout(header)

        # ── Live Context sections (the agent's mind) ──
        self._sections: List[QWidget] = []
        self._section_heads: List[QLabel] = []
        self._section_values: List[QLabel] = []
        self._online = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(12)

        self._status_label = QLabel("● Checking…")
        self._status_detail = ""
        self._status_label.setStyleSheet(self._status_style(TEXT_MUTED))
        self._status_label.setWordWrap(True)
        inner_layout.addWidget(self._status_label)
        self._sections.append(self._status_label)

        self._mission = self._section(inner_layout, "MISSION", "No active mission")
        self._working = self._section(inner_layout, "WORKING ON", "—")
        self._memory = self._section(inner_layout, "MEMORY", "—")

        # Tools: the execution timeline (semantic, like web ActionSteps).
        self._tools_title = self._label("TOOLS", 12, True, TEXT_SECONDARY)
        inner_layout.addWidget(self._tools_title)
        self._sections.append(self._tools_title)
        self._tool_rows: List[QLabel] = []
        self._tool_state: List[List[str]] = []  # [label, status] — update by label
        self._tools_empty = self._label("Quiet", 12, False, TEXT_MUTED)
        inner_layout.addWidget(self._tools_empty)
        self._sections.append(self._tools_empty)

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        self.set_collapsed(collapsed, notify=False)

    # ── collapse (progressive context) ─────────────────────────────────────
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def _toggle_style(self) -> str:
        return (
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
            f" border: none; border-radius: 6px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {BG_SURFACE}; color: {TEXT_PRIMARY}; }}"
        )

    def set_collapsed(self, collapsed: bool, notify: bool = True) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH)
        self._toggle_btn.setText("▸" if collapsed else "▾")
        self._title.setVisible(not collapsed)
        for section in self._sections:
            section.setVisible(not collapsed)
        # Keep the status line readable in the collapsed rail.
        if collapsed:
            self._status_label.setStyleSheet(self._status_style(TEXT_MUTED))
        if collapsed:
            self.layout().setContentsMargins(6, 12, 6, 12)
        else:
            self.layout().setContentsMargins(16, 16, 16, 16)
        if notify and self._on_collapsed is not None:
            self._on_collapsed(collapsed)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    # ── Live Context API ────────────────────────────────────────────────────
    def _label(self, text: str, size: int, bold: bool, color: str) -> QLabel:
        label = QLabel(text)
        weight = "700" if bold else "400"
        label.setStyleSheet(f"font-size: {size}px; font-weight: {weight}; color: {color};")
        label.setWordWrap(True)
        return label

    def _status_style(self, color: str) -> str:
        return f"color: {color}; font-size: 12px; font-weight: 600;"

    def _section(self, parent_layout: QVBoxLayout, title: str, value: str) -> QLabel:
        head = self._label(title, 12, True, TEXT_SECONDARY)
        parent_layout.addWidget(head)
        self._sections.append(head)
        self._section_heads.append(head)
        body = self._label(value, 12, False, TEXT_PRIMARY)
        parent_layout.addWidget(body)
        self._sections.append(body)
        self._section_values.append(body)
        return body

    def set_status(self, online: bool, detail: str = "") -> None:
        self._online = online
        self._status_detail = detail
        color = PRESENCE_COLORS.get("success") if online else TEXT_MUTED
        text = "● Online" if online else "● Offline"
        if detail:
            text += f"\n{detail}"
        self._status_label.setText(text)
        self._status_label.setStyleSheet(self._status_style(color))

    def set_context(self, context: dict) -> None:
        """Same context dict the inline working-context card composes from."""
        self._mission.setText(str(context.get("objective") or "No active mission"))
        self._working.setText(str(context.get("project") or "—"))
        memories = context.get("memories") or 0
        self._memory.setText(f"{memories} relevant memories" if memories else "—")

    def clear_context(self) -> None:
        self.set_context({})

    def set_tool_activity(self, label: str, status: str) -> None:
        """Update-by-label — the same semantics as web ActionSteps/Android
        ToolActivity: a step streams in as in_progress, then completes."""
        if not label:
            return
        for row in self._tool_state:
            if row[0] == label:
                row[1] = status
                self._render_tools()
                return
        self._tool_state.append([label, status])
        if len(self._tool_state) > 4:  # the recent execution timeline
            self._tool_state.pop(0)
        self._render_tools()

    def clear_tools(self) -> None:
        self._tool_state = []
        self._render_tools()

    def _render_tools(self) -> None:
        # Rebuild the rows (≤4 labels — cheap and theme-safe).
        for row in self._tool_rows:
            row.deleteLater()
        self._tool_rows = []
        # Rows are inserted before the empty marker's position in the layout.
        layout = self._tools_empty.parentWidget().layout()
        idx = layout.indexOf(self._tools_empty)
        for i, (label, status) in enumerate(reversed(self._tool_state)):
            color, glyph = {
                "complete": (PRESENCE_COLORS.get("success"), "✓"),
                "in_progress": (PRESENCE_COLORS.get("thinking"), "⟳"),
                "error": (PRESENCE_COLORS.get("error"), "✗"),
            }.get(status, (TEXT_MUTED, "○"))
            row = self._label(f"{glyph}  {label}", 12, False, color)
            self._tool_rows.append(row)
            layout.insertWidget(idx + i, row)
            self._sections.append(row)
        self._tools_empty.setVisible(not self._tool_state)


    def refresh_theme(self) -> None:
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BORDER_SUBTLE};")
        self._title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        self._toggle_btn.setStyleSheet(self._toggle_style())
        if self._online is not None:
            self.set_status(self._online, getattr(self, "_status_detail", ""))
        for head in self._section_heads:
            head.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {TEXT_SECONDARY};")
        for value in self._section_values:
            value.setStyleSheet(f"font-size: 12px; font-weight: 400; color: {TEXT_PRIMARY};")
        self._tools_title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {TEXT_SECONDARY};")
        self._tools_empty.setStyleSheet(f"font-size: 12px; font-weight: 400; color: {TEXT_MUTED};")
        self._render_tools()

