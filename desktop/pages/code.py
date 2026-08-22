"""CodePage — extracted from monolithic app.py."""

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



class CodePage(QWidget):
    """Code execution — mirrors the web Code page (uses the backend sandbox)."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel("Code")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        self.code = QTextEdit()
        self.code.setPlaceholderText("Enter Python code…")
        self.code.setStyleSheet(_textarea_style())
        layout.addWidget(self.code, 1)

        self._run_btn = QPushButton("Run")
        self._run_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._run_btn.clicked.connect(self._run)
        layout.addWidget(self._run_btn)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(_textarea_style())
        self.output.setFixedHeight(140)
        layout.addWidget(self.output)

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.code.setStyleSheet(_textarea_style())
        self.output.setStyleSheet(_textarea_style())
        self._run_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))

    def _run(self) -> None:
        code = self.code.toPlainText().strip()
        if not code:
            return
        self.output.setPlainText("Running…")
        try:
            res = self._client.execute_code(code, "python")
            out = res.get("output") or res.get("stdout") or res.get("result") or str(res)
            if res.get("isolated") is False:
                out = "⚠ Ran without isolation (a plain temp dir, not a container/VM). Install Docker or WSL2.\n\n" + str(out)
            if res.get("error"):
                out = str(out) + "\n\nError: " + str(res["error"])
            self.output.setPlainText(str(out))
        except BackendConnectionError as e:
            self.output.setPlainText(f"⚠ {e}")

