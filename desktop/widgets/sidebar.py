"""LeftSidebar — extracted from monolithic app.py."""

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



class LeftSidebar(QFrame):
    """ChatGPT-style left sidebar: Beanie identity + New Chat + conversation list + nav."""

    def __init__(self, on_new_chat, on_select_conversation, on_nav, on_conversation, parent=None):
        super().__init__(parent)
        self._on_select_conversation = on_select_conversation
        self._on_conversation = on_conversation
        self._nav_buttons: List[QPushButton] = []
        self.setFixedWidth(240)
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-right: 1px solid {BG_SURFACE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Beanie identity (orb + name + status)
        ident = QHBoxLayout()
        self.orb = PresenceOrbWidget(diameter=36)
        ident.addWidget(self.orb)
        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        self._name_label = QLabel("Beanie")
        self._name_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY};")
        name_col.addWidget(self._name_label)
        self.status_label = QLabel("● Offline")
        self.status_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        name_col.addWidget(self.status_label)
        ident.addLayout(name_col)
        ident.addStretch(1)
        layout.addLayout(ident)

        # New chat
        self._new_chat_btn = QPushButton("+ New Chat")
        self._new_chat_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._new_chat_btn.clicked.connect(on_new_chat)
        layout.addWidget(self._new_chat_btn)

        # Conversation mode — continuous, hands-free listening (native-only:
        # browsers can't hold the mic open like this).
        self.conversation_btn = QPushButton("🎙 Conversation Mode")
        self.conversation_btn.setCheckable(True)
        self.conversation_btn.setStyleSheet(
            _button_style(BG_SURFACE, TEXT_PRIMARY)
            + f"QPushButton:checked {{ background: {ACCENT}; color: #FFFFFF; }}"
        )
        self.conversation_btn.toggled.connect(self._on_conversation)
        layout.addWidget(self.conversation_btn)

        # Conversation list
        self._chats_label = QLabel("Chats")
        self._chats_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 600;")
        layout.addWidget(self._chats_label)
        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet(
            f"background: transparent; color: {TEXT_PRIMARY}; border: none;"
            f" QListWidget::item {{ padding: 8px; border-radius: 6px; }}"
            f" QListWidget::item:selected {{ background: {BG_SURFACE}; }}"
        )
        self.conv_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.conv_list, stretch=1)

        # Navigation (mirrors the web sidebar: Chats / Pansophy / Files / Code / Settings / Projects)
        for label, key in [
            ("Chats", "chat"), ("Pansophy", "pansophy"), ("Files", "files"),
            ("Code", "code"), ("Images", "images"), ("Projects", "projects"),
            ("Settings", "settings"), ("Beanie", "beanie"), ("Tools", "tools"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
            btn.clicked.connect(lambda _=False, k=key: on_nav(k))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

    def _on_item_clicked(self, item) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self._on_select_conversation(cid)

    def set_conversations(self, conversations) -> None:
        self.conv_list.clear()
        for cid, title in conversations:
            from PySide6.QtWidgets import QListWidgetItem
            from PySide6.QtCore import Qt
            item = QListWidgetItem(title or "Conversation")
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.conv_list.addItem(item)

    def set_status(self, connected: bool) -> None:
        color = "#10B981" if connected else TEXT_MUTED
        self.status_label.setText("● Online" if connected else "● Offline")
        self.status_label.setStyleSheet(f"font-size: 12px; color: {color};")

    def set_orb_status(self, status: str) -> None:
        self.orb.set_status(status)

    def set_conversation_mode(self, active: bool) -> None:
        self.conversation_btn.blockSignals(True)
        self.conversation_btn.setChecked(active)
        self.conversation_btn.blockSignals(False)

    def refresh_theme(self) -> None:
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-right: 1px solid {BG_SURFACE};")
        self._name_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY};")
        self._chats_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 600;")
        self._new_chat_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.conversation_btn.setStyleSheet(
            _button_style(BG_SURFACE, TEXT_PRIMARY)
            + f"QPushButton:checked {{ background: {ACCENT}; color: #FFFFFF; }}"
        )
        self.conv_list.setStyleSheet(
            f"background: transparent; color: {TEXT_PRIMARY}; border: none;"
            f" QListWidget::item {{ padding: 8px; border-radius: 6px; }}"
            f" QListWidget::item:selected {{ background: {BG_SURFACE}; }}"
        )
        for btn in self._nav_buttons:
            btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))

