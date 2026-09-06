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
    """Right context panel: connection + hardware (Goal/Memory/Knowledge are web-only).

    Progressive context (round-21c): collapsible, so context is available on
    demand instead of being a permanent third column. The collapsed state is a
    slim rail with just the expand chevron; the choice persists via settings.
    """

    EXPANDED_WIDTH = 240
    COLLAPSED_WIDTH = 36

    def __init__(self, parent=None, collapsed: bool = False, on_collapsed=None):
        super().__init__(parent)
        self._on_collapsed = on_collapsed
        self._collapsed = False
        self.setFixedWidth(self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH)
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BG_SURFACE};")
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

        self.body = QLabel("Checking…")
        self.body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.body, stretch=1)

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
        self.body.setVisible(not collapsed)
        if collapsed:
            self.layout().setContentsMargins(6, 12, 6, 12)
        else:
            self.layout().setContentsMargins(16, 16, 16, 16)
        if notify and self._on_collapsed is not None:
            self._on_collapsed(collapsed)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_text(self, text: str) -> None:
        self.body.setText(text)

    def refresh_theme(self) -> None:
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BG_SURFACE};")
        self._title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        self._toggle_btn.setStyleSheet(self._toggle_style())
        self.body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")

