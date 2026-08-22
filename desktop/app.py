"""Native Arena desktop window.

Renders the SAME React UI as the web (QtWebEngineView) so desktop == web,
pixel-for-pixel — no parallel layout to drift out of sync. On top of that it
adds native-only capabilities the browser can't do:

- Auto-granted mic/camera permissions (no browser prompts).
- "Conversation Mode" (tray toggle): a native PyAudio mic that keeps listening
  continuously — no user gesture, no autoplay restriction — and speaks replies
  aloud natively (pyttsx3), then keeps listening.
- System tray + notifications.

The backend (app.server:app) must be running — it serves the React SPA and the
voice/WebSocket endpoints this window uses.
"""

from __future__ import annotations

import sys
import webbrowser

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from desktop.settings import DesktopSettings
from desktop.voice_client import DesktopVoiceClient

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    WEBENGINE_AVAILABLE = True
except Exception:  # noqa: BLE001 — PySide6-Addons not installed
    QWebEngineView = None  # type: ignore
    QWebEnginePage = None  # type: ignore
    WEBENGINE_AVAILABLE = False


ACCENT = "#3B82F6"


def _tray_icon() -> QIcon:
    """A simple blue orb for the system tray."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QRadialGradient(QPointF(23, 23), 28)
    grad.setColorAt(0.0, QColor("#7FB3FF"))
    grad.setColorAt(0.6, QColor(ACCENT))
    grad.setColorAt(1.0, QColor("#1E40AF"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(32, 32), 26, 26)
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.setWindowTitle("Beanie")
        self.resize(1200, 800)

        self.settings = DesktopSettings()
        saved_url = self.settings.get("server_url")
        base_url = saved_url if saved_url and saved_url != "http://localhost:8000" else base_url
        self.base_url = base_url.rstrip("/")

        # ── The web UI (exact same layout as the browser) ──
        if WEBENGINE_AVAILABLE:
            self.web = QWebEngineView()
            self.web.page().featurePermissionRequested.connect(self._on_feature_permission)
            self.web.setUrl(QUrl(self.base_url))
            self.setCentralWidget(self.web)
        else:
            self.setCentralWidget(self._fallback_widget())

        # ── Native conversation mode (continuous PyAudio mic → backend → TTS) ──
        ws_url = self.base_url.replace("http://", "ws://").rstrip("/") + "/ws"
        self.voice = DesktopVoiceClient(ws_url=ws_url, conversation_id="desktop-voice")
        self.voice.on_reply = self._on_voice_reply
        self.voice.on_error = self._on_voice_error
        self._listening = False

        self._setup_tray()

    # ── permissions (auto-grant mic/camera — "more permissions" than the web) ──
    def _on_feature_permission(self, origin: QUrl, feature) -> None:
        if feature in (
            QWebEnginePage.Feature.MediaAudioCapture,
            QWebEnginePage.Feature.MediaVideoCapture,
        ):
            self.web.page().setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            )

    def _fallback_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)
        msg = QLabel(
            "QtWebEngine isn't installed, so the embedded view can't load.\n\n"
            "Install it once with:\n    pip install PySide6-Addons\n\n"
            "Until then, open the web UI in your browser:"
        )
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color: #F1F5F9; font-size: 15px;")
        layout.addWidget(msg)
        open_btn = QPushButton(f"Open {self.base_url}")
        open_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #FFFFFF; border: none;"
            f" border-radius: 10px; padding: 10px 14px; font-weight: 600; }}"
        )
        open_btn.clicked.connect(lambda: webbrowser.open(self.base_url))
        layout.addWidget(open_btn)
        return widget

    # ── system tray + conversation mode ─────────────────────────────────────
    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(_tray_icon(), self)
        self.tray.setToolTip("Beanie")

        menu = QMenu()
        show_action = menu.addAction("Show / Hide")
        show_action.triggered.connect(self._toggle_visible)

        self.conversation_action = menu.addAction("🎙 Conversation Mode")
        self.conversation_action.setCheckable(True)
        self.conversation_action.triggered.connect(self._toggle_conversation_mode)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _toggle_conversation_mode(self) -> None:
        if self._listening:
            self._stop_conversation()
        else:
            self._start_conversation()

    def _start_conversation(self) -> None:
        if self.voice.start():
            self._listening = True
            self.conversation_action.setChecked(True)
            self.tray.setToolTip("Beanie — Conversation Mode (listening)")
            if self.settings.get("notifications_enabled"):
                self.tray.showMessage(
                    "Beanie", "Conversation mode on — I'm listening.", QSystemTrayIcon.MessageIcon.Information, 2000
                )

    def _stop_conversation(self) -> None:
        self.voice.stop()
        self._listening = False
        self.conversation_action.setChecked(False)
        self.tray.setToolTip("Beanie")

    def _on_voice_reply(self, text: str) -> None:
        # Speak natively — no browser autoplay restriction, then keep listening.
        self._speak(text)
        if self.settings.get("notifications_enabled") and not self.isVisible():
            self.tray.showMessage("Beanie", (text[:160] + "…") if len(text) > 160 else text, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_voice_error(self, err: str) -> None:
        self._listening = False
        self.conversation_action.setChecked(False)
        self.tray.showMessage("Beanie", f"Voice error: {err}", QSystemTrayIcon.MessageIcon.Warning, 3000)

    def _speak(self, text: str) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", int(175 * self.settings.get("voice_speed")))
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass

    # ── window / tray plumbing ──────────────────────────────────────────────
    def _toggle_visible(self) -> None:
        self.setVisible(not self.isVisible())

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visible()

    def _quit(self) -> None:
        self._stop_conversation()
        self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        # Minimize to tray instead of quitting (Quit lives in the tray menu).
        if self.tray.isVisible():
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)


def run(base_url: str = "http://localhost:8000") -> int:
    app = QApplication(sys.argv)
    window = MainWindow(base_url=base_url)
    window.show()
    return app.exec()
