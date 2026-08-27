"""Native Arena desktop window (PySide6 / Qt) — now modularized.

The visual language mirrors the web UI: a floating, breathing presence orb in the
Arena dark theme, plus BEANIE branding, quick actions, and bottom navigation.

This file is now a thin composition root (MainWindow + run) that imports from
modularized packages:

- desktop/theme.py — THEME_COLORS, BG_*, ACCENT, PRESENCE_COLORS, apply_theme, _is_system_dark
- desktop/styles.py — _button_style, _input_style, _textarea_style
- desktop/widgets/orb.py — PresenceOrbWidget
- desktop/widgets/sidebar.py — LeftSidebar
- desktop/widgets/context.py — ContextPanel
- desktop/workers.py — ChatWorker, HealthWorker, LocationWorker, VisionWorker, CameraThread
- desktop/pages/beanie.py — BeaniePage
- desktop/pages/chat.py — ChatPage
- desktop/pages/message_bubble.py — MessageBubble
- desktop/pages/files.py — FilesPage
- desktop/pages/pansophy.py — PansophyPage
- desktop/pages/projects.py — ProjectsPage
- desktop/pages/settings.py — SettingsPage
- desktop/pages/code.py — CodePage
- desktop/pages/vision.py — VisionPage
- desktop/pages/tools.py — ToolsPage

This closes the code-quality debt G8 (monolithic 2000-line file) while keeping
backward compatibility: `from desktop.app import MainWindow` still works.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtCore import QPointF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.chat_client import DesktopChatClient
from desktop.settings import DesktopSettings
from desktop.voice_client import DesktopAudioPlayer, DesktopVoiceClient

# Theme + styles (modularized)
from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, apply_theme
from desktop.styles import _button_style

# Widgets + workers (modularized)
from desktop.widgets.orb import PresenceOrbWidget
from desktop.widgets.sidebar import LeftSidebar
from desktop.widgets.context import ContextPanel
from desktop.workers import HealthWorker

# Pages (modularized)
from desktop.pages.beanie import BeaniePage
from desktop.pages.chat import ChatPage
from desktop.pages.files import FilesPage
from desktop.pages.pansophy import PansophyPage
from desktop.pages.projects import ProjectsPage
from desktop.pages.settings import SettingsPage
from desktop.pages.code import CodePage
from desktop.pages.vision import VisionPage
from desktop.pages.tools import ToolsPage
from desktop.pages.lora import LoraPage
from desktop.pages.owner_control import OwnerControlPage

# For backward compatibility, re-export theme globals and helpers that old code might import from desktop.app
from desktop.theme import THEME_COLORS, PRESENCE_COLORS, PRESENCE_DURATIONS, _lighten, _is_system_dark, _resolved_theme_name
from desktop.styles import _input_style, _textarea_style
from desktop.workers import ChatWorker, LocationWorker, VisionWorker, CameraThread, CV2_AVAILABLE
from desktop.pages.message_bubble import MessageBubble


class MainWindow(QMainWindow):
    # Marshal mic amplitude from the capture thread onto the GUI thread.
    _level_signal = Signal(float)
    # Marshal chat events from the WS recv thread onto the GUI thread.
    _chat_token_signal = Signal(str, bool)
    _chat_list_signal = Signal(list)
    _chat_history_signal = Signal(str, list)
    _chat_created_signal = Signal(str, str)
    _chat_error_signal = Signal(str)
    # Marshal voice events from the voice WS recv thread onto the GUI thread
    # (the _on_voice_* handlers mutate widgets, which must only happen on the
    # GUI thread).
    _voice_transcript_signal = Signal(str, bool)
    _voice_reply_signal = Signal(str)
    _voice_error_signal = Signal(str)
    _voice_state_signal = Signal(str)

    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.setWindowTitle("Arena — Beanie")
        self.resize(920, 720)
        self.setMinimumSize(520, 420)  # freely resizable, both directions

        self.settings = DesktopSettings()
        # Persisted server URL overrides the CLI default when set.
        saved_url = self.settings.get("server_url")
        base_url = saved_url if saved_url and saved_url != "http://localhost:8000" else base_url

        self.client = ArenaBackendClient(
            base_url=base_url,
            api_key=str(self.settings.get("api_key") or ""),
        )

        # Hydrate the theme from the backend's shared settings (short timeout so
        # an offline backend doesn't block launch), then apply it BEFORE any
        # widget is constructed so the whole window renders in the right palette.
        # This makes the "backend-driven" theme actually two-way: a theme change
        # made on web/Android now re-themes the desktop on next launch.
        # Supports 'system' which follows OS dark mode.
        try:
            shared = self.client.get_shared_settings(timeout=3.0)
            backend_theme = shared.get("theme")
            if backend_theme in ("dark", "light", "system"):
                self.settings.set("theme", backend_theme)
        except BackendConnectionError:
            pass  # backend offline — keep the locally-persisted theme
        apply_theme(self.settings.get("theme") or "dark")

        self._chat_worker: Optional[ChatWorker] = None

        # Voice (talk to Beanie) — streams mic PCM to the backend. The callbacks
        # fire on the voice client's recv thread, so they only emit signals here;
        # the actual UI mutation happens in the _on_voice_* slots (GUI thread).
        ws_url = base_url.replace("http://", "ws://").rstrip("/") + "/ws"
        # Plays the backend's streamed Piper reply audio (replaces local pyttsx3,
        # which caused double speech). Created before the voice client so its
        # push() can be wired directly as the audio callback.
        self.audio_player = DesktopAudioPlayer()
        self.voice = DesktopVoiceClient(ws_url=ws_url, conversation_id="desktop-voice")
        self.voice.on_reply = lambda text: self._voice_reply_signal.emit(text)
        self.voice.on_transcript = lambda text, final: self._voice_transcript_signal.emit(text, final)
        self.voice.on_error = lambda err: self._voice_error_signal.emit(err)
        self.voice.on_voice_state = lambda state: self._voice_state_signal.emit(state)
        # Streamed Piper audio arrives on the WS recv thread; the player consumes
        # it via a thread-safe queue, so no GUI-thread marshalling is needed.
        self.voice.on_audio = self.audio_player.push
        self.voice.on_level = self._on_voice_level
        self._listening = False

        # Chat (ChatGPT-style, same WS protocol as web/Android).
        self.chat_client = DesktopChatClient(ws_url=ws_url, conversation_id="desktop-chat")
        self.chat_client.on_connected = self._on_chat_connected
        self.chat_client.on_token = lambda t, d: self._chat_token_signal.emit(t, d)
        self.chat_client.on_conversation_list = lambda c: self._chat_list_signal.emit(c)
        self.chat_client.on_history = lambda cid, h: self._chat_history_signal.emit(cid, h)
        self.chat_client.on_created = lambda cid, t: self._chat_created_signal.emit(cid, t)
        self.chat_client.on_error = lambda e: self._chat_error_signal.emit(e)
        self.current_conv_id = "desktop-chat"

        self._chat_token_signal.connect(self._handle_chat_token)
        self._chat_list_signal.connect(self._handle_conversation_list)
        self._chat_history_signal.connect(self._handle_conversation_history)
        self._chat_created_signal.connect(self._handle_conversation_created)
        self._chat_error_signal.connect(self._handle_chat_error)

        self._voice_transcript_signal.connect(self._on_voice_transcript)
        self._voice_reply_signal.connect(self._on_voice_reply)
        self._voice_error_signal.connect(self._on_voice_error)
        self._voice_state_signal.connect(self._on_voice_state)

        # Pages
        self.beanie = BeaniePage(on_talk=self._toggle_talk, on_quick_action=self._quick_action)
        self.chat = ChatPage(on_send=self._send_message, on_voice=self._toggle_talk)
        self.pansophy = PansophyPage(self.client)
        self.files = FilesPage(self.client)
        self.code = CodePage(self.client)
        self.vision = VisionPage(self.client)
        self.projects_page = ProjectsPage(self.client)
        self.lora_page = LoraPage(self.client)
        self.owner_control_page = OwnerControlPage(self.client)
        self.settings_page = SettingsPage(
            self.settings,
            self.client,
            on_save=self._on_save_server_url,
            on_theme_change=self._on_theme_changed,
        )
        self.tools = ToolsPage(self.client)

        # Cross-thread: capture thread emits → orb.set_level runs on GUI thread.
        self._level_signal.connect(self.beanie.orb.set_level)

        # Left sidebar (ChatGPT-style)
        self.sidebar = LeftSidebar(
            on_new_chat=self._new_chat,
            on_select_conversation=self._select_conversation,
            on_nav=self._nav_to_key,
            on_conversation=self._on_conversation_mode,
        )
        self._level_signal.connect(self.sidebar.orb.set_level)

        # Center stack (Chat is the default view)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.chat)         # index 0
        self.stack.addWidget(self.pansophy)     # index 1
        self.stack.addWidget(self.files)        # index 2
        self.stack.addWidget(self.code)         # index 3
        self.stack.addWidget(self.settings_page)  # index 4
        self.stack.addWidget(self.beanie)       # index 5
        self.stack.addWidget(self.tools)        # index 6
        self.stack.addWidget(self.vision)       # index 7
        self.stack.addWidget(self.projects_page)  # index 8
        self.stack.addWidget(self.lora_page)      # index 9
        self.stack.addWidget(self.owner_control_page)  # index 10
        self.stack.setCurrentIndex(0)

        # Right context panel
        self.context = ContextPanel()

        # Three-column ChatGPT-style layout
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.sidebar)
        central_layout.addWidget(self.stack, stretch=1)
        central_layout.addWidget(self.context)
        self.setCentralWidget(central)

        # Dark theme
        self.setStyleSheet(f"QMainWindow {{ background: {BG_PRIMARY}; }}")
        self._setup_tray()
        self._check_health()
        self.chat_client.connect()

    # ── System tray ─────────────────────────────────────────────────────────
    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Arena — Beanie")

        menu = QMenu()
        show_action = QAction("Show / Hide", self)
        show_action.triggered.connect(self._toggle_visible)
        menu.addAction(show_action)

        talk_action = QAction("Talk to Beanie", self)
        talk_action.triggered.connect(self._toggle_talk)
        menu.addAction(talk_action)

        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _tray_icon(self) -> QIcon:
        # Draw the presence orb as the tray icon.
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(32, 32)
        grad = QRadialGradient(QPointF(23, 23), 28)
        grad.setColorAt(0.0, _lighten(ACCENT, 0.6))
        grad.setColorAt(0.6, QColor(ACCENT))
        grad.setColorAt(1.0, QColor(ACCENT).darker(160))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, 26, 26)
        p.end()
        return QIcon(pix)

    def _toggle_visible(self) -> None:
        self.setVisible(not self.isVisible())

    @Slot()
    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visible()

    def _quit(self) -> None:
        self._stop_voice()
        self.chat_client.close()
        self.tray.hide()
        self.client.close()
        QApplication.instance().quit()

    # ── Navigation ──
    def _nav_to_key(self, key: str) -> None:
        index = {
            "chat": 0, "pansophy": 1, "files": 2, "code": 3,
            "settings": 4, "beanie": 5, "tools": 6, "images": 7,
            "projects": 8, "lora": 9, "owner_control": 10,
        }.get(key, 0)
        self.stack.setCurrentIndex(index)
        if key == "tools":
            self.tools.refresh_status()
        elif key == "owner_control":
            self.owner_control_page.refresh()

    def _on_save_server_url(self, url: str) -> None:
        self.tray.showMessage(
            "Beanie", f"Server URL saved: {url}\nRestart the app to reconnect.",
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )

    def _on_theme_changed(self, theme: str) -> None:
        """Live theme switch (G4): re-skin the whole desktop instantly."""
        normalized = apply_theme(theme)
        # Persist locally too
        self.settings.set("theme", theme if theme in ("dark", "light", "system") else normalized)
        self._refresh_all_themes()
        self.tray.showMessage(
            "Beanie", f"Theme: {theme} — applied live.",
            QSystemTrayIcon.MessageIcon.Information, 2000,
        )

    def _refresh_all_themes(self) -> None:
        """Re-apply stylesheets to every widget using current globals (G4 live theme)."""
        self.setStyleSheet(f"QMainWindow {{ background: {BG_PRIMARY}; }}")
        # Sidebar + context
        try:
            self.sidebar.refresh_theme()
        except Exception:
            pass
        try:
            self.context.refresh_theme()
        except Exception:
            pass
        # Pages
        for page in [
            self.beanie, self.chat, self.pansophy, self.files, self.code,
            self.settings_page, self.tools, self.vision, self.projects_page,
            self.lora_page, self.owner_control_page,
        ]:
            try:
                if hasattr(page, "refresh_theme"):
                    page.refresh_theme()
            except Exception:
                pass
        # Tray icon uses ACCENT — regenerate so it matches new theme
        try:
            self.tray.setIcon(self._tray_icon())
        except Exception:
            pass
        # Force repaint
        self.update()

    def _set_status(self, status: str) -> None:
        """Update the orb on both the Beanie page and the sidebar."""
        self.beanie.set_status(status)
        self.sidebar.set_orb_status(status)

    # ── Health ──
    def _check_health(self) -> None:
        self._health_worker = HealthWorker(self.client, self)
        self._health_worker.online.connect(self._on_online)
        self._health_worker.offline.connect(self._on_offline)
        self._health_worker.start()

    @Slot()
    def _on_online(self) -> None:
        self._set_status("idle")
        self.sidebar.set_status(True)
        self.beanie.set_message("I'm here.")
        self.context.set_text("● Online\n\nConnected to the backend.")

    @Slot(str)
    def _on_offline(self, err: str) -> None:
        self._set_status("offline")
        self.sidebar.set_status(False)
        self.beanie.set_message("Offline — start the backend.")
        self.context.set_text(f"● Offline\n\n{err}")

    # ── Chat (ChatGPT-style) ──
    def _on_chat_connected(self) -> None:
        self.chat_client.list_conversations()

    def _new_chat(self) -> None:
        self.chat_client.create_conversation()

    def _select_conversation(self, cid: str) -> None:
        self.current_conv_id = cid
        self.chat.clear_messages()
        self.chat_client.get_history(cid)

    def _send_message(self, content: str) -> None:
        self.chat.append_message("user", content)
        self._set_status("thinking")
        self.chat.set_voice_status("thinking")
        self.beanie.set_message("Thinking…")
        self.chat_client.send_user_message(self.current_conv_id, content)

    @Slot(str, bool)
    def _handle_chat_token(self, token: str, done: bool) -> None:
        self.chat.stream_token(token, done)
        if done:
            self._set_status("idle")
            self.chat.set_voice_status("idle")
            self.beanie.set_message("I'm here.")

    @Slot(list)
    def _handle_conversation_list(self, conversations: list) -> None:
        self.sidebar.set_conversations(conversations)

    @Slot(str, list)
    def _handle_conversation_history(self, cid: str, history: list) -> None:
        if cid != self.current_conv_id:
            return
        self.chat.clear_messages()
        for role, content in history:
            self.chat.append_message(role, content)

    @Slot(str, str)
    def _handle_conversation_created(self, cid: str, title: str) -> None:
        self.current_conv_id = cid
        self.chat.clear_messages()
        self.chat_client.list_conversations()

    @Slot(str)
    def _handle_chat_error(self, err: str) -> None:
        self.chat.append_message("assistant", f"⚠ {err}")
        self._set_status("offline")
        self.beanie.set_message("Connection error.")

    # ── Quick actions / talk ──
    def _quick_action(self, action: str) -> None:
        # Map quick actions to chat prompts (simplest useful behavior).
        prompts = {
            "continue_project": "What were we working on? Continue the project.",
            "whats_new": "What's new in my system?",
            "research": "Research the latest on my current project.",
            "talk": "",
        }
        prompt = prompts.get(action, "")
        if prompt:
            self._nav_to_key("chat")
            self._send_message(prompt)

    def _toggle_talk(self) -> None:
        if self._listening:
            self._stop_voice()
        else:
            self._start_voice()

    def _on_conversation_mode(self, active: bool) -> None:
        """Toggle continuous conversation mode (always-on mic)."""
        if active:
            self._start_voice()
        else:
            self._stop_voice()

    def _start_voice(self) -> None:
        if self.voice.start():
            self._listening = True
            self.audio_player.start()
            self._set_status("listening")
            self.chat.set_voice_status("listening")
            self.sidebar.set_conversation_mode(True)
            self.beanie.set_message("Listening…")
            if self.settings.get("notifications_enabled"):
                self.tray.showMessage("Arena", "Conversation mode on — I'm listening.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _stop_voice(self) -> None:
        if self._listening:
            self.voice.stop()
            self.audio_player.stop()
            self._listening = False
            self._set_status("idle")
            self.chat.set_voice_status("idle")
            self.sidebar.set_conversation_mode(False)
            self.beanie.set_message("I'm here.")

    # ── Voice callbacks ─────────────────────────────────────────────────────
    @Slot(str, bool)
    def _on_voice_transcript(self, text: str, is_final: bool) -> None:
        if is_final and text.strip():
            self.chat.append_message("user", text.strip())

    @Slot(str)
    def _on_voice_reply(self, text: str) -> None:
        self.chat.append_message("assistant", text)
        # The reply is spoken by the backend (Piper) and streamed back to us as
        # audio; the "speaking" state is driven by the backend's voice_state
        # broadcasts, not here. Only raise a desktop notification (best-effort).
        if self.settings.get("notifications_enabled") and not self.isVisible():
            self.tray.showMessage("Arena", (text[:160] + "…") if len(text) > 160 else text, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_voice_level(self, level: float) -> None:
        self._level_signal.emit(level)

    @Slot(str)
    def _on_voice_state(self, state: str) -> None:
        """Reflect the backend voice pipeline state onto the orb + banner.

        Backend VoiceState values: idle, listening, recording, processing,
        thinking, speaking. We collapse recording→listening and processing→
        thinking, since the desktop orb distinguishes those four presence states.
        """
        orb_state = {
            "recording": "listening",
            "processing": "thinking",
        }.get(state, state)
        if orb_state not in ("listening", "thinking", "speaking", "idle"):
            orb_state = "idle"
        self._set_status(orb_state)
        self.chat.set_voice_status(orb_state)
        if orb_state == "listening":
            self.beanie.set_message("Listening…")
        elif orb_state == "thinking":
            self.beanie.set_message("Thinking…")
        elif orb_state == "speaking":
            self.beanie.set_message("Speaking…")
        elif orb_state == "idle":
            self.beanie.set_message("I'm here.")
        # The backend streams the reply audio around the "speaking" state; the
        # player consumes it on its own thread, so nothing extra to do here.

    @Slot(str)
    def _on_voice_error(self, err: str) -> None:
        self.chat.append_message("assistant", f"⚠ {err}")
        self._stop_voice()

    def closeEvent(self, event) -> None:
        self._stop_voice()
        self.chat_client.close()
        self.tools._stop_camera()
        self.client.close()
        # Minimize to tray instead of quitting (unless the user chose Quit).
        if self.settings.get("minimize_to_tray") and self.tray.isVisible():
            event.ignore()
            self.hide()
            if self.settings.get("notifications_enabled"):
                self.tray.showMessage("Arena", "Still running in the tray.", QSystemTrayIcon.MessageIcon.Information, 2000)
            return
        super().closeEvent(event)


def run(base_url: str = "http://localhost:8000") -> int:
    app = QApplication(sys.argv)
    window = MainWindow(base_url=base_url)
    window.show()
    return app.exec()



if __name__ == "__main__":
    raise SystemExit(run())
