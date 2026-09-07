"""MessageBubble — extracted."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop.theme import BG_SECONDARY, TEXT_PRIMARY, ACCENT, BORDER_SUBTLE
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
                f" border: 1px solid {BORDER_SUBTLE}; border-radius: 16px; font-size: 14px;"
            )
            # Assistant bubbles stack the text and (optionally) the response
            # review bar in one column so the review controls sit directly
            # under the exact reply they belong to.
            self._bubble_column = QVBoxLayout()
            self._bubble_column.setContentsMargins(0, 0, 0, 0)
            self._bubble_column.setSpacing(3)
            self._bubble_column.addWidget(self.label)
            column_holder = QWidget()
            column_holder.setLayout(self._bubble_column)
            row.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(column_holder, alignment=Qt.AlignmentFlag.AlignTop)
            row.addStretch(1)
            self._review_widget: Optional[QWidget] = None

        self.set_text(content)

    def attach_review_widget(self, widget: QWidget) -> bool:
        """Mount a Review-response bar under THIS exact reply.

        Returns False when the bubble already carries one or is not an
        assistant bubble — one review bar per reply, user replies have
        nothing to review.
        """
        if self._role != "assistant" or self._review_widget is not None:
            return False
        self._review_widget = widget
        self._bubble_column.addWidget(widget)
        return True

    def has_review_widget(self) -> bool:
        return self._review_widget is not None

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
                f" border: 1px solid {BORDER_SUBTLE}; border-radius: 16px; font-size: 14px;"
            )
            review = getattr(self, "_review_widget", None)
            if review is not None and hasattr(review, "refresh_theme"):
                review.refresh_theme()

