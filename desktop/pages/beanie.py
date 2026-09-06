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
from desktop.styles import _button_style, _composer_style, _input_style, _textarea_style
from desktop.widgets.orb import PresenceOrbWidget
from desktop.workers import ChatWorker, HealthWorker, LocationWorker, VisionWorker, CameraThread, CV2_AVAILABLE



class BeaniePage(QWidget):
    """The home screen — Beanie present, a landing composer, subtle suggestions.

    Restrained per the design review (round-21d): Beanie is the identity layer,
    not a voice-assistant landing page. Giant quick-action tiles were replaced
    by subtle text chips; the mic lives in the composer; a greeting replaces
    the branding tagline.
    """

    def __init__(self, on_talk, on_quick_action, on_submit=None, parent=None):
        super().__init__(parent)
        self._on_talk = on_talk
        self._on_quick_action = on_quick_action
        self._on_submit = on_submit
        self._quick_buttons: List[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addStretch(1)

        # Orb — Beanie's presence (the identity layer)
        self.orb = PresenceOrbWidget(diameter=200)
        orb_row = QHBoxLayout()
        orb_row.addStretch(1)
        orb_row.addWidget(self.orb)
        orb_row.addStretch(1)
        layout.addLayout(orb_row)

        # Identity + greeting
        self._title = QLabel("Beanie")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(f"font-size: 30px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        self._subtitle = QLabel(self._greeting())
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._subtitle)

        self.message = QLabel("What are we working on today?")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; font-style: italic;")
        layout.addWidget(self.message)

        layout.addSpacing(16)

        # Landing composer — "Ask Beanie anything…" with the mic inline.
        if self._on_submit is not None:
            composer = QHBoxLayout()
            self.input = QLineEdit()
            self.input.setPlaceholderText("Ask Beanie anything…")
            self.input.setStyleSheet(_composer_style())
            self.input.returnPressed.connect(self._submit)
            composer.addWidget(self.input, stretch=1)

            self.mic_btn = QPushButton("🎙")
            self.mic_btn.setFixedSize(44, 44)
            self.mic_btn.setStyleSheet(self._round_icon_style())
            self.mic_btn.clicked.connect(self._on_talk)
            composer.addWidget(self.mic_btn)

            self.send_btn = QPushButton("➤")
            self.send_btn.setFixedSize(44, 44)
            self.send_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
            self.send_btn.clicked.connect(self._submit)
            composer.addWidget(self.send_btn)

            composer_row = QHBoxLayout()
            composer_row.addStretch(1)
            composer_row.addLayout(composer)
            composer_row.addStretch(1)
            layout.addLayout(composer_row)
        else:  # no submit wiring (tests): keep the mic entry point anyway
            self.input = None
            self.mic_btn = None
            self.send_btn = None

        layout.addSpacing(8)

        # Subtle suggestions (dramatically reduced from the old 56px tiles)
        self.quick_actions = [
            ("Continue project", "continue_project"),
            ("What's new?", "whats_new"),
            ("Research", "research"),
            ("Talk to me", "talk"),
        ]
        chips = QHBoxLayout()
        chips.addStretch(1)
        for label, action in self.quick_actions:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._chip_style())
            btn.clicked.connect(lambda _=False, a=action: self._on_quick_action(a))
            self._quick_buttons.append(btn)
            chips.addWidget(btn)
        chips.addStretch(1)
        layout.addLayout(chips)

        layout.addStretch(1)

    # ── styles ─────────────────────────────────────────────────────────────
    @staticmethod
    def _greeting() -> str:
        import datetime

        hour = datetime.datetime.now().hour
        if hour < 12:
            return "Good morning."
        if hour < 18:
            return "Good afternoon."
        return "Good evening."

    def _chip_style(self) -> str:
        return (
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
            f" border: none; border-radius: 8px; padding: 6px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {BG_SURFACE}; color: {TEXT_PRIMARY}; }}"
        )

    def _round_icon_style(self) -> str:
        return (
            f"QPushButton {{ background: {BG_SURFACE}; color: {TEXT_PRIMARY};"
            f" border: none; border-radius: 12px; font-size: 16px; }}"
            f"QPushButton:hover {{ background: {_lighten(BG_SURFACE, 0.15).name()}; }}"
        )

    # ── behavior ───────────────────────────────────────────────────────────
    def _submit(self) -> None:
        if self.input is None:
            return
        text = self.input.text().strip()
        if text and self._on_submit is not None:
            self.input.clear()
            self._on_submit(text)

    def set_message(self, text: str) -> None:
        self.message.setText(text)

    def set_status(self, status: str) -> None:
        self.orb.set_status(status)

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 30px; font-weight: 700; color: {TEXT_PRIMARY};")
        self._subtitle.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        self.message.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; font-style: italic;")
        for btn in self._quick_buttons:
            btn.setStyleSheet(self._chip_style())
        if self.mic_btn is not None:
            self.mic_btn.setStyleSheet(self._round_icon_style())
        if self.send_btn is not None:
            self.send_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))

