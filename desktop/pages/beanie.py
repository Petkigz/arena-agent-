"""BeaniePage — extracted from monolithic app.py."""

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



class BeaniePage(QWidget):
    """The home screen — floating orb + BEANIE branding + quick actions."""

    def __init__(self, on_talk, on_quick_action, parent=None):
        super().__init__(parent)
        self._on_talk = on_talk
        self._on_quick_action = on_quick_action
        self._quick_buttons: List[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addStretch(1)

        # Orb
        self.orb = PresenceOrbWidget(diameter=200)
        orb_row = QHBoxLayout()
        orb_row.addStretch(1)
        orb_row.addWidget(self.orb)
        orb_row.addStretch(1)
        layout.addLayout(orb_row)

        # Branding
        self._title = QLabel("BEANIE")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(f"font-size: 30px; font-weight: 800; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        self._subtitle = QLabel("Personal AI")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._subtitle)

        self.message = QLabel("I'm here.")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(f"font-size: 13px; color: {TEXT_MUTED}; font-style: italic;")
        layout.addWidget(self.message)

        layout.addSpacing(12)

        # Quick actions (2-col grid)
        self.quick_actions = [
            ("Continue project", "continue_project"),
            ("What's new?", "whats_new"),
            ("Research", "research"),
            ("Talk to me", "talk"),
        ]
        grid = QHBoxLayout()
        for i in range(0, 4, 2):
            col = QVBoxLayout()
            for label, action in self.quick_actions[i:i + 2]:
                btn = QPushButton(label)
                btn.setMinimumHeight(56)
                btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
                btn.clicked.connect(lambda _=False, a=action: self._on_quick_action(a))
                self._quick_buttons.append(btn)
                col.addWidget(btn)
            grid.addLayout(col)
        layout.addLayout(grid)

        layout.addSpacing(8)

        # Talk button
        self._talk_btn = QPushButton("🎙  Talk to Beanie")
        self._talk_btn.setMinimumHeight(56)
        self._talk_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._talk_btn.clicked.connect(self._on_talk)
        layout.addWidget(self._talk_btn)

        layout.addStretch(1)

    def set_message(self, text: str) -> None:
        self.message.setText(text)

    def set_status(self, status: str) -> None:
        self.orb.set_status(status)

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 30px; font-weight: 800; color: {TEXT_PRIMARY};")
        self._subtitle.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        self.message.setStyleSheet(f"font-size: 13px; color: {TEXT_MUTED}; font-style: italic;")
        for btn in self._quick_buttons:
            btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self._talk_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))

