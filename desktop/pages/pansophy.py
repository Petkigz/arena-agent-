"""PansophyPage — extracted from monolithic app.py."""

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



class PansophyPage(QWidget):
    """Knowledge / memory — mirrors the web Pansophy page (list view)."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel("Pansophy")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self._refresh_btn.clicked.connect(self._load)
        layout.addWidget(self._refresh_btn)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )
        layout.addWidget(self.list, 1)
        self._load()

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self._refresh_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )

    def _load(self) -> None:
        self.list.clear()
        # Knowledge graph (entities + relationships) from the world model.
        try:
            graph = self._client.knowledge_graph()
            entities = graph.get("entities") or []
            relationships = graph.get("relationships") or []
            self.list.addItem(f"── Knowledge Graph — {len(entities)} entities, {len(relationships)} links ──")
            for e in entities[:150]:
                self.list.addItem(f"• {e.get('name')}  [{e.get('type')}]")
            for r in relationships[:150]:
                self.list.addItem(f"↳ {r.get('predicate')} ({r.get('subject_id', '')[:8]} → {r.get('object_id', '')[:8]})")
            if not entities and not relationships:
                self.list.addItem("(knowledge graph is empty)")
        except BackendConnectionError as e:
            self.list.addItem(f"⚠ knowledge graph: {e}")

        # Memories (vector memory).
        try:
            memories = self._client.list_memories()
            self.list.addItem(f"── Memories ({len(memories)}) ──")
            for m in memories[:150]:
                text = m.get("title") or m.get("content") or str(m)
                self.list.addItem(f"• {text}")
            if not memories:
                self.list.addItem("(no memories yet)")
        except BackendConnectionError as e:
            self.list.addItem(f"⚠ memories: {e}")

