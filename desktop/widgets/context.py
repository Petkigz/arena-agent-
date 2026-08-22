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
from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, PRESENCE_COLORS, PRESENCE_DURATIONS, _lighten
from desktop.styles import _button_style, _input_style, _textarea_style
from desktop.widgets.orb import PresenceOrbWidget
from desktop.workers import ChatWorker, HealthWorker, LocationWorker, VisionWorker, CameraThread, CV2_AVAILABLE



class ContextPanel(QFrame):
    """Right context panel: connection + hardware (Goal/Memory/Knowledge are web-only)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BG_SURFACE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._title = QLabel("Context")
        self._title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        self.body = QLabel("Checking…")
        self.body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.body, stretch=1)

    def set_text(self, text: str) -> None:
        self.body.setText(text)

    def refresh_theme(self) -> None:
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BG_SURFACE};")
        self._title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")

