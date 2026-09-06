"""MessageBubble — extracted."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from desktop.theme import BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY, ACCENT
from desktop.widgets.orb import PresenceOrbWidget

class MessageBubble(QWidget):
    """A single chat bubble.

    Assistant bubbles carry a small animated presence orb beside them (matching
    the web/Android layout where the Beanie orb sits next to assistant messages);
    user bubbles are right-aligned blue bubbles. Rendered as real widgets — not
    HTML — so the orb is a live QPainter animation rather than a text glyph.
    """

    MAX_WIDTH = 560

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self._role = role
        self._orb: Optional[PresenceOrbWidget] = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setMaximumWidth(self.MAX_WIDTH)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setCursor(Qt.CursorShape.IBeamCursor)

        if role == "user":
            self.label.setStyleSheet(
                f"background: {ACCENT}; color: #FFFFFF; padding: 10px 16px;"
                f" border-radius: 16px; font-size: 14px;"
            )
            row.addStretch(1)
            row.addWidget(self.label)
        else:
            self._orb = PresenceOrbWidget(diameter=30)
            self.label.setStyleSheet(
                f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; padding: 10px 16px;"
                f" border: 1px solid {BG_SURFACE}; border-radius: 16px; font-size: 14px;"
            )
            row.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignTop)
            row.addStretch(1)

        self.set_text(content)

    def set_text(self, content: str) -> None:
        self.label.setText(content)

    def set_status(self, status: str) -> None:
        if self._orb is not None:
            self._orb.set_status(status)

    def refresh_theme(self) -> None:
        if self._role == "user":
            self.label.setStyleSheet(
                f"background: {ACCENT}; color: #FFFFFF; padding: 10px 16px;"
                f" border-radius: 16px; font-size: 14px;"
            )
        else:
            self.label.setStyleSheet(
                f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; padding: 10px 16px;"
                f" border: 1px solid {BG_SURFACE}; border-radius: 16px; font-size: 14px;"
            )

