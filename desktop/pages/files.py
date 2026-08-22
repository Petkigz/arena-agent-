"""FilesPage — extracted from monolithic app.py."""

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



class FilesPage(QWidget):
    """File search — mirrors the web Files page."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel("Files")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Search files…")
        self.input.setStyleSheet(_input_style())
        self.input.returnPressed.connect(self._search)
        row.addWidget(self.input, 1)
        self._search_btn = QPushButton("Search")
        self._search_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._search_btn.clicked.connect(self._search)
        row.addWidget(self._search_btn)
        layout.addLayout(row)

        self.results = QListWidget()
        self.results.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        layout.addWidget(self.results, 1)

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.input.setStyleSheet(_input_style())
        self._search_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.results.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )

    def _search(self) -> None:
        q = self.input.text().strip()
        if not q:
            return
        self.results.clear()
        try:
            res = self._client.search_files(q)
            results = res if isinstance(res, list) else res.get("results", [])
            for item in results[:100]:
                self.results.addItem(str(item.get("name") or item.get("path") or item))
            if not results:
                self.results.addItem("(no results)")
        except BackendConnectionError as e:
            self.results.addItem(f"⚠ {e}")

