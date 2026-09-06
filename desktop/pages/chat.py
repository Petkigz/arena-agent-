"""ChatPage — extracted."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget, QFrame

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, PRESENCE_COLORS
from desktop.styles import _button_style, _composer_style
from desktop.widgets.working_context import WorkingContextCard
from desktop.pages.message_bubble import MessageBubble
from desktop.widgets.orb import PresenceOrbWidget

class ChatPage(QWidget):
    """ChatGPT-style conversation: message bubbles + composer (sidebar lives in MainWindow).

    Messages are individual widgets in a scroll area, so assistant bubbles show
    the animated presence orb inline instead of an HTML "● Beanie" text label.
    """

    def __init__(self, on_send, on_voice, parent=None):
        super().__init__(parent)
        self._on_send = on_send
        self._on_voice = on_voice

        self._bubbles: List[MessageBubble] = []
        self._streaming_bubble: Optional[MessageBubble] = None
        self._streaming = ""

        right = QVBoxLayout(self)
        right.setContentsMargins(16, 12, 16, 12)
        right.setSpacing(8)

        # Beanie-first header: the conversation title is context, not the
        # product identity. This mirrors the web and Android top bars.
        header = QFrame()
        header.setObjectName("beanieChatHeader")
        header.setStyleSheet(
            f"QFrame#beanieChatHeader {{ background: {BG_SECONDARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 12px; }}"
        )
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 8, 12, 8)
        header_row.setSpacing(10)
        self.header_orb = PresenceOrbWidget(diameter=30)
        header_row.addWidget(self.header_orb)
        identity = QVBoxLayout()
        identity.setSpacing(0)
        self._header_name = QLabel("Beanie")
        self._header_name.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        identity.addWidget(self._header_name)
        header_meta = QHBoxLayout()
        header_meta.setSpacing(5)
        self._header_status = QLabel("● Offline")
        self._header_status.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        self._header_conversation = QLabel("Current conversation")
        self._header_conversation.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        header_meta.addWidget(self._header_status)
        header_meta.addWidget(QLabel("·"))
        header_meta.addWidget(self._header_conversation)
        identity.addLayout(header_meta)
        header_row.addLayout(identity, stretch=1)
        self._header_subtitle = QLabel("Personal AI Assistant")
        self._header_subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        header_row.addWidget(self._header_subtitle)
        right.addWidget(header)

        # Scrollable message list (widget-based, so orbs animate in place).
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"background: {BG_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;")

        self.container = QWidget()
        self.container.setStyleSheet(f"background: {BG_PRIMARY};")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(12, 12, 12, 12)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch(1)  # push bubbles to the top; new ones insert above it
        self.scroll.setWidget(self.container)
        right.addWidget(self.scroll, stretch=1)

        # Floating voice-state banner (hidden unless listening/thinking/speaking).
        self.voice_banner = QLabel()
        self.voice_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_banner.hide()
        right.addWidget(self.voice_banner)

        # Inline working-context card (design review section 4): while Beanie
        # works, the conversation itself carries the context — no permanent
        # side column. Hidden collapses out of the layout entirely.
        self.working_card = WorkingContextCard()
        right.addWidget(self.working_card)

        composer = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message Beanie…")
        self.input.setStyleSheet(_composer_style())
        self.input.returnPressed.connect(self._submit)
        composer.addWidget(self.input, stretch=1)

        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(44, 40)
        self.mic_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.mic_btn.clicked.connect(self._on_voice)
        composer.addWidget(self.mic_btn)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(44, 40)
        self.send_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.send_btn.clicked.connect(self._submit)
        composer.addWidget(self.send_btn)

        right.addLayout(composer)

    # ── events ──────────────────────────────────────────────────────────────
    def _submit(self) -> None:
        content = self.input.text().strip()
        if content:
            self._on_send(content)
            self.input.clear()

    def clear_messages(self) -> None:
        for bubble in self._bubbles:
            bubble.deleteLater()
        if self._streaming_bubble is not None:
            self._streaming_bubble.deleteLater()
        self._bubbles = []
        self._streaming_bubble = None
        self._streaming = ""

    def append_message(self, role: str, content: str) -> None:
        bubble = MessageBubble(role, content)
        self._bubbles.append(bubble)
        self._insert_bubble(bubble)

    def show_user_message(self, message_id: str, content: str) -> None:
        """Render a user message that came from another client (cross-room sync)."""
        bubble = MessageBubble("user", content)
        self._insert_bubble(bubble)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    def stream_token(self, token: str, done: bool) -> None:
        if self._streaming_bubble is None:
            self._streaming_bubble = MessageBubble("assistant", "")
            self._streaming_bubble.set_status("thinking")
            self._insert_bubble(self._streaming_bubble)
        self._streaming += token
        self._streaming_bubble.set_text(self._streaming)
        if done:
            self._streaming_bubble.set_status("idle")
            self._bubbles.append(self._streaming_bubble)
            self._streaming_bubble = None
            self._streaming = ""
        self._scroll_to_bottom()

    def set_conversation_title(self, title: str) -> None:
        self._header_conversation.setText(title or "Current conversation")
        self._header_conversation.setToolTip(title or "Current conversation")

    def set_connection_status(self, online: bool, detail: str = "") -> None:
        label = "Online" if online else "Offline"
        if detail:
            label += f" · {detail}"
        color = PRESENCE_COLORS.get("success") if online else TEXT_MUTED
        self._header_orb.set_status("idle" if online else "offline")
        self._header_status.setText(f"● {label}")
        self._header_status.setStyleSheet(f"font-size: 12px; color: {color};")

    def refresh_theme(self) -> None:
        self.scroll.setStyleSheet(f"background: {BG_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;")
        self.findChild(QFrame, "beanieChatHeader").setStyleSheet(
            f"QFrame#beanieChatHeader {{ background: {BG_SECONDARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 12px; }}"
        )
        self.container.setStyleSheet(f"background: {BG_PRIMARY};")
        self.input.setStyleSheet(_composer_style())
        self.mic_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.send_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.working_card.refresh_theme()
        for bubble in self._bubbles:
            bubble.refresh_theme()
        if self._streaming_bubble is not None:
            self._streaming_bubble.refresh_theme()

    def show_working_context(self, context: dict) -> None:
        """Show the inline working-context card (partial context is fine)."""
        self.working_card.set_context(context or {})

    def hide_working_context(self) -> None:
        self.working_card.clear()

    def set_voice_status(self, status: str) -> None:
        """Show/hide the floating voice-state banner."""
        labels = {
            "listening": "Listening…",
            "recording": "Listening…",
            "processing": "Thinking…",
            "thinking": "Thinking…",
            "speaking": "Speaking…",
        }
        colors = {
            "listening": PRESENCE_COLORS["listening"],
            "recording": PRESENCE_COLORS["listening"],
            "processing": PRESENCE_COLORS["thinking"],
            "thinking": PRESENCE_COLORS["thinking"],
            "speaking": PRESENCE_COLORS["speaking"],
        }
        if status not in labels:
            self.voice_banner.hide()
            self.header_orb.set_status("idle" if status != "offline" else "offline")
            return
        self.header_orb.set_status(status)
        label = labels[status]
        color = colors[status]
        self.voice_banner.setText(f'<span style="color:{color};">●</span>  {label}')
        self.voice_banner.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 9999px; padding: 8px 16px;"
        )
        self.voice_banner.show()

    # ── internals ───────────────────────────────────────────────────────────
    def _insert_bubble(self, bubble: MessageBubble) -> None:
        # Insert above the trailing stretch (which sits at the last index).
        self.list_layout.insertWidget(self.list_layout.count() - 1, bubble)

    def _scroll_to_bottom(self) -> None:
        # Defer to the next event-loop tick so the layout has settled first.
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

