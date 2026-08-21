"""Native Arena desktop window (PySide6 / Qt).

Phase 1: connection status + text chat against the unified backend.

Hardware tabs (camera, location, voice, files) are added in later phases; this
module establishes the window shell, the backend client wiring, and the chat flow.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError


class ChatWorker(QThread):
    """Send a chat message to the backend off the UI thread and emit the reply."""

    reply_ready = Signal(str)
    error_ready = Signal(str)

    def __init__(self, client: ArenaBackendClient, content: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._content = content

    def run(self) -> None:
        try:
            text = self._client.chat_text(self._content)
            self.reply_ready.emit(text)
        except BackendConnectionError as e:
            self.error_ready.emit(str(e))


class HealthWorker(QThread):
    """Probe backend health off the UI thread."""

    online = Signal()
    offline = Signal(str)

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        try:
            if self._client.is_online():
                self.online.emit()
            else:
                self.offline.emit("Backend responded but is not healthy.")
        except BackendConnectionError as e:
            self.offline.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.setWindowTitle("Arena — Local Assistant")
        self.resize(760, 560)

        self.client = ArenaBackendClient(base_url=base_url)
        self._chat_worker: Optional[ChatWorker] = None

        # ── status bar ──
        self.status_label = QLabel("Connecting…")
        self.statusBar().addWidget(self.status_label)

        # ── central widget: tabs ──
        tabs = QTabWidget()
        tabs.addTab(self._build_chat_tab(), "Chat")
        tabs.addTab(self._build_placeholder_tab("Camera / Location / Files come next."), "Hardware")
        self.setCentralWidget(tabs)

        self._check_health()

    # ── UI builders ─────────────────────────────────────────────────────────
    def _build_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setPlaceholderText("Ask Arena anything…")
        layout.addWidget(self.chat_log)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message…")
        self.input.returnPressed.connect(self._send_message)
        row.addWidget(self.input)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send_message)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

        return tab

    def _build_placeholder_tab(self, text: str) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return tab

    # ── backend actions ─────────────────────────────────────────────────────
    def _check_health(self) -> None:
        self.status_label.setText("Connecting…")
        self._health_worker = HealthWorker(self.client, self)
        self._health_worker.online.connect(self._on_online)
        self._health_worker.offline.connect(self._on_offline)
        self._health_worker.start()

    @Slot()
    def _on_online(self) -> None:
        self.status_label.setText("Connected")
        self.status_label.setStyleSheet("color: #10b981;")

    @Slot(str)
    def _on_offline(self, err: str) -> None:
        self.status_label.setText(f"Offline — {err}")
        self.status_label.setStyleSheet("color: #ef4444;")

    def _send_message(self) -> None:
        content = self.input.text().strip()
        if not content:
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return

        self.input.clear()
        self._append_chat("You", content)

        self._chat_worker = ChatWorker(self.client, content, self)
        self._chat_worker.reply_ready.connect(self._on_reply)
        self._chat_worker.error_ready.connect(self._on_chat_error)
        self._chat_worker.start()

    @Slot(str)
    def _on_reply(self, text: str) -> None:
        self._append_chat("Arena", text)

    @Slot(str)
    def _on_chat_error(self, err: str) -> None:
        self._append_chat("System", f"⚠ {err}")

    def _append_chat(self, speaker: str, text: str) -> None:
        self.chat_log.append(f"<b>{speaker}:</b>")
        self.chat_log.append(text)
        self.chat_log.append("")

    def closeEvent(self, event) -> None:
        self.client.close()
        super().closeEvent(event)


def run(base_url: str = "http://localhost:8000") -> int:
    app = QApplication(sys.argv)
    window = MainWindow(base_url=base_url)
    window.show()
    return app.exec()
