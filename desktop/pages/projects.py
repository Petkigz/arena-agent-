"""ProjectsPage — extracted from monolithic app.py."""

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
from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, PRESENCE_COLORS, PRESENCE_DURATIONS, _lighten
from desktop.styles import _button_style, _input_style, _textarea_style
from desktop.widgets.orb import PresenceOrbWidget
from desktop.workers import ChatWorker, HealthWorker, LocationWorker, VisionWorker, CameraThread, CV2_AVAILABLE



class ProjectsPage(QWidget):
    """Projects — long-horizon + multi-session tracking (P2 AGI).

    Mirrors web ProjectsPage but backed by backend's ProjectManager (persistent).
    Shows projects created via cognitive runtime decomposition (complex goals → sub-goals).
    """

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel("Projects")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("New project name…")
        self.input.setStyleSheet(_input_style())
        row.addWidget(self.input, 1)
        self.create_btn = QPushButton("Create")
        self.create_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.create_btn.clicked.connect(self._create)
        row.addWidget(self.create_btn)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.refresh_btn.clicked.connect(self._load)
        row.addWidget(self.refresh_btn)
        layout.addLayout(row)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        layout.addWidget(self.list, 1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet(_textarea_style())
        self.detail.setFixedHeight(120)
        layout.addWidget(self.detail)

        self.list.itemClicked.connect(self._on_item_clicked)

        self._load()

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.input.setStyleSheet(_input_style())
        self.create_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.refresh_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        self.detail.setStyleSheet(_textarea_style())

    def _load(self) -> None:
        self.list.clear()
        try:
            data = self._client.list_projects()
            projects = data.get("projects", []) if isinstance(data, dict) else []
            for p in projects[:100]:
                label = f"{p.get('name','')} — {p.get('progress_percent',0)}% ({p.get('status','')})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, p.get("project_id",""))
                self.list.addItem(item)
            if not projects:
                self.list.addItem("(no projects yet — complex goals auto-create them)")
        except Exception as e:
            self.list.addItem(f"⚠ {e}")

    def _create(self) -> None:
        name = self.input.text().strip()
        if not name:
            return
        try:
            self._client.create_project(name, description=name)
            self.input.clear()
            self._load()
        except Exception as e:
            self.detail.setPlainText(f"⚠ Could not create: {e}")

    def _on_item_clicked(self, item) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        if not pid:
            return
        try:
            data = self._client.get_project(pid)
            proj = data.get("project", {})
            resume = data.get("resume_context", {})
            decomp = data.get("decomposition", {})
            detail_lines = [
                f"Project: {proj.get('name','')}",
                f"Status: {proj.get('status','')} — {proj.get('progress_percent',0)}% ",
                f"Milestones: {len(proj.get('milestones',[]))}",
                f"Sessions: {proj.get('sessions',0)}",
                f"\nResume: {resume.get('progress_percent','')}% — pending: {resume.get('pending_milestones',[])[:3]}",
                f"\nDecomposition: {decomp.get('progress_percent','')}% — next: {decomp.get('next_actions',[])[:2]}",
            ]
            self.detail.setPlainText("\n".join(str(x) for x in detail_lines))
        except Exception as e:
            self.detail.setPlainText(f"⚠ {e}")

