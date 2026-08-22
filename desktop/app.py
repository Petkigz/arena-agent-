"""Native Arena desktop window (PySide6 / Qt) — matches the "Beanie" design.

The visual language mirrors the web UI: a floating, breathing presence orb in the
Arena dark theme (background #0F172A, surface #1E293B/#334155, presence colors
idle=#3B82F6 / working=#F59E0B / listening=#10B981 / speaking=#8B5CF6), plus
"BEANIE" branding, quick actions, and a bottom navigation (Beanie / Chat / Tools).

Hardware access (camera, location, files, status) is native — no browser.
"""

from __future__ import annotations

import math
import sys
from typing import List, Optional

from PySide6.QtCore import (
    Property,
    QBuffer,
    QEasingCurve,
    QIODevice,
    QPointF,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
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
from desktop.chat_client import DesktopChatClient
from desktop.settings import DesktopSettings
from desktop.voice_client import DesktopAudioPlayer, DesktopVoiceClient

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False


# ── Theme (mirrors frontend index.css dark + light palettes) ─────────────────
# The color globals below are mutated by apply_theme() BEFORE any widget is
# constructed, so pages read the active palette at build time. (Widgets bake
# these values into their QSS strings at construction, so switching theme in a
# running session requires a restart — apply_theme() is called at startup.)
THEME_COLORS = {
    "dark": {
        "BG_PRIMARY": "#0F172A",
        "BG_SECONDARY": "#1E293B",
        "BG_SURFACE": "#334155",
        "TEXT_PRIMARY": "#F1F5F9",
        "TEXT_SECONDARY": "#CBD5E1",
        "TEXT_MUTED": "#94A3B8",
        "ACCENT": "#3B82F6",
    },
    "light": {
        "BG_PRIMARY": "#F8FAFC",
        "BG_SECONDARY": "#E2E8F0",
        "BG_SURFACE": "#CBD5E1",
        "TEXT_PRIMARY": "#1E293B",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#64748B",
        "ACCENT": "#2563EB",
    },
}

BG_PRIMARY = THEME_COLORS["dark"]["BG_PRIMARY"]
BG_SECONDARY = THEME_COLORS["dark"]["BG_SECONDARY"]
BG_SURFACE = THEME_COLORS["dark"]["BG_SURFACE"]
TEXT_PRIMARY = THEME_COLORS["dark"]["TEXT_PRIMARY"]
TEXT_SECONDARY = THEME_COLORS["dark"]["TEXT_SECONDARY"]
TEXT_MUTED = THEME_COLORS["dark"]["TEXT_MUTED"]
ACCENT = THEME_COLORS["dark"]["ACCENT"]


def apply_theme(name: str) -> str:
    """Switch the active palette (returns the normalized name)."""
    normalized = name if name in THEME_COLORS else "dark"
    for key, value in THEME_COLORS[normalized].items():
        globals()[key] = value
    return normalized

PRESENCE_COLORS = {
    "idle": "#3B82F6",
    "working": "#F59E0B",
    "listening": "#10B981",
    "speaking": "#8B5CF6",
    "offline": "#334155",
    "thinking": "#F59E0B",
    "acting": "#38BDF8",
    "observing": "#38BDF8",
    "success": "#10B981",
    "error": "#EF4444",
    "sleeping": "#334155",
}
PRESENCE_DURATIONS = {
    "idle": 3400,
    "working": 1600,
    "listening": 1200,
    "speaking": 1050,
    "offline": 0,
    "thinking": 1600,
    "acting": 2000,
    "observing": 2000,
    "success": 2000,
    "error": 400,
    "sleeping": 5000,
}


def _lighten(hex_color: str, factor: float = 0.6) -> QColor:
    c = QColor(hex_color)
    return QColor(
        int(c.red() + (255 - c.red()) * factor),
        int(c.green() + (255 - c.green()) * factor),
        int(c.blue() + (255 - c.blue()) * factor),
    )


# ════════════════════════════════════════════════════════════════════════════
# Floating presence orb
# ════════════════════════════════════════════════════════════════════════════
class PresenceOrbWidget(QWidget):
    """Reactive presence orb — a layered translucent core wrapped in a voice
    field of ring-lines, mirroring the web/Android ReactiveBeanieOrb.

    The rings are not decoration: they carry the cognitive/voice state
    (idle breathe, listening mic-reactive, thinking circulating, acting sweep,
    speaking outward waves, success ripple, error disturbance, sleeping dim)."""

    # States whose `pulse` should advance linearly (rotation / outward / ripple).
    _LINEAR_STATES = {"speaking", "thinking", "acting", "observing", "success", "error"}

    def __init__(self, diameter: int = 220, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._pulse = 0.0
        self._status = "idle"
        self._level = 0.0
        self._color = QColor(PRESENCE_COLORS["idle"])
        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(PRESENCE_DURATIONS["idle"])
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    # Qt property for the breathing animation
    def _get_pulse(self) -> float:
        return self._pulse

    def _set_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    pulse = Property(float, _get_pulse, _set_pulse)

    def set_status(self, status: str) -> None:
        self._status = status
        self._color = QColor(PRESENCE_COLORS.get(status, PRESENCE_COLORS["idle"]))
        dur = PRESENCE_DURATIONS.get(status, PRESENCE_DURATIONS["idle"])
        if status in self._LINEAR_STATES:
            self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        else:
            self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        if dur == 0:
            self._anim.stop()
        else:
            self._anim.setDuration(dur)
            if self._anim.state() != QPropertyAnimation.State.Running:
                self._anim.start()
        self.update()

    @Slot(float)
    def set_level(self, level: float) -> None:
        """0..1 amplitude (mic while listening / TTS while speaking)."""
        self._level = max(0.0, min(1.0, level))
        self.update()

    def _ring_motion(self, status: str, phase: float, breath: float, index: int):
        """Return (rotation_deg, scale, alpha) for a ring, keyed by state."""
        level = self._level
        if status == "idle":
            return 0.0, 1.0 + 0.05 * breath, 0.28
        if status == "working":
            return 0.0, 1.0 + 0.08 * breath, 0.4
        if status == "listening":
            amp = level * 0.14 * (1.0 - index * 0.18)
            auto = 0.04 * breath
            return 0.0, 1.0 + amp + auto, 0.3 + level * 0.35
        if status == "speaking":
            s = 1.0 + phase * 0.55 + level * 0.1
            a = max(0.0, min(0.55, 0.55 * (1.0 - phase)))
            return 0.0, s, a
        if status in ("thinking", "acting", "observing"):
            direction = 1.0 if index % 2 == 0 else -1.0
            alpha = 0.38 if status == "thinking" else (0.42 if status == "acting" else 0.36)
            return phase * 360.0 * direction, 1.0, alpha
        if status == "success":
            s = 0.55 + phase * 1.15
            a = max(0.0, min(0.85, 0.85 * (1.0 - phase)))
            return 0.0, s, a
        if status == "error":
            jitter = 1.08 if int(phase * 10) % 2 == 0 else 0.94
            return 0.0, jitter, 0.5
        return 0.0, 1.0, 0.0

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        center = QPointF(w / 2.0, w / 2.0)
        color = self._color
        status = self._status

        # Breathing scale: pulse (0→1) → a single smooth in-out breath.
        breath = 0.5 + 0.5 * math.sin(self._pulse * 2.0 * math.pi)

        if status not in ("offline", "sleeping"):
            # Soft outer glow.
            glow = QRadialGradient(center, w / 2.0)
            glow_color = QColor(color)
            glow_color.setAlpha(70)
            glow.setColorAt(0.0, glow_color)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(center, w / 2.0, w / 2.0)

            # Voice-field rings (dashed, rotating/scaling per state).
            ring_radii = [w * 0.31, w * 0.39, w * 0.47]
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i, r in enumerate(ring_radii):
                rotation, scale, alpha = self._ring_motion(status, self._pulse, breath, i)
                if alpha <= 0.01:
                    continue
                pen = QPen(color)
                pen.setWidth(2)
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([10, 8])
                pen.setColor(QColor(color.red(), color.green(), color.blue(), int(255 * alpha)))
                p.setPen(pen)
                rr = r * scale
                p.save()
                p.translate(center)
                p.rotate(rotation)
                p.translate(-center)
                p.drawEllipse(center, rr, rr)
                p.restore()

        # Core sphere: highlight offset toward the top-left.
        radius = (w / 2.0) * 0.42 * (0.96 + 0.05 * breath)
        sphere = QRadialGradient(QPointF(w * 0.36, w * 0.36), radius)
        sphere.setColorAt(0.0, _lighten(color.name(), 0.7))
        sphere.setColorAt(0.55, color)
        sphere.setColorAt(1.0, QColor(color).darker(160))
        p.setBrush(sphere)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, radius, radius)

        # Inner highlight (light diffusion, not a face).
        p.setBrush(QColor(255, 255, 255, 80))
        p.drawEllipse(QPointF(w * 0.42, w * 0.42), w * 0.14, w * 0.14)

        # Focal point (presence, subtle).
        focal = QColor(color)
        focal.setAlpha(220)
        p.setBrush(focal)
        fr = w * 0.07 * (1.0 if status in ("offline", "sleeping") else 1.0 + 0.25 * breath)
        p.drawEllipse(center, fr, fr)

        p.end()


# ════════════════════════════════════════════════════════════════════════════
# Workers
# ════════════════════════════════════════════════════════════════════════════
class ChatWorker(QThread):
    reply_ready = Signal(str)
    error_ready = Signal(str)

    def __init__(self, client: ArenaBackendClient, content: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._content = content

    def run(self) -> None:
        try:
            self.reply_ready.emit(self._client.chat_text(self._content))
        except BackendConnectionError as e:
            self.error_ready.emit(str(e))


class HealthWorker(QThread):
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
                self.offline.emit("Backend not healthy.")
        except BackendConnectionError as e:
            self.offline.emit(str(e))


class LocationWorker(QThread):
    result = Signal(dict)
    error = Signal(str)

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        try:
            self.result.emit(self._client.resolve_location())
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class VisionWorker(QThread):
    """Runs a vision operation off the GUI thread and marshals results back.

    The LLM analysis step can take tens of seconds on CPU inference, so it must
    not run inside the event loop (it would freeze the window).
    """

    result = Signal(dict)
    preview = Signal(QImage)
    error = Signal(str)

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        # One of: "capture", "capture_analyze", "ocr", "analyze", "analyze_upload"
        self._mode = "capture_analyze"
        self._prompt_focus: Optional[str] = None
        self._image_path: str = ""
        self._upload_path: str = ""

    def capture(self, prompt_focus: Optional[str] = None) -> None:
        self._mode = "capture"
        self._prompt_focus = prompt_focus

    def capture_and_analyze(self, prompt_focus: Optional[str] = None) -> None:
        self._mode = "capture_analyze"
        self._prompt_focus = prompt_focus

    def ocr(self, image_path: str) -> None:
        self._mode = "ocr"
        self._image_path = image_path

    def analyze(self, image_path: str, prompt_focus: Optional[str] = None) -> None:
        self._mode = "analyze"
        self._image_path = image_path
        self._prompt_focus = prompt_focus

    def analyze_upload(self, upload_path: str, prompt_focus: Optional[str] = None) -> None:
        self._mode = "analyze_upload"
        self._upload_path = upload_path
        self._prompt_focus = prompt_focus

    def run(self) -> None:
        try:
            if self._mode == "capture":
                res = self._client.capture_screen()
            elif self._mode == "capture_analyze":
                res = self._client.capture_and_analyze(self._prompt_focus)
            elif self._mode == "ocr":
                res = self._client.ocr_image(self._image_path)
            elif self._mode == "analyze":
                res = self._client.analyze_image(self._image_path, self._prompt_focus)
            elif self._mode == "analyze_upload":
                up = self._client.upload_image_file(self._upload_path)
                if not up.get("success"):
                    self.error.emit(f"Upload failed: {up.get('error', 'unknown')}")
                    return
                res = self._client.analyze_image(up.get("file_path", ""), self._prompt_focus)
                res["image_url"] = up.get("file_url", "")
                res["file_name"] = up.get("file_name", "")
            else:
                self.error.emit("Unknown vision mode.")
                return

            # Try to load the returned image so the UI can preview it.
            url = res.get("image_url") or res.get("file_url")
            if url:
                try:
                    data = self._client.fetch_image_bytes(url)
                    img = QImage.fromData(data)
                    if not img.isNull():
                        self.preview.emit(img)
                except BackendConnectionError:
                    pass  # preview is best-effort; text results still matter
            self.result.emit(res)
        except BackendConnectionError as e:
            self.error.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class CameraThread(QThread):
    frame = Signal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap = None
        self._running = False

    def run(self) -> None:
        if not CV2_AVAILABLE:
            return
        try:
            self._cap = cv2.VideoCapture(0)
            if not self._cap.isOpened():
                return
            self._running = True
            while self._running:
                ok, frame = self._cap.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, _ = rgb.shape
                img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                self.frame.emit(img)
                self.msleep(33)
        finally:
            if self._cap is not None:
                self._cap.release()

    def stop(self) -> None:
        self._running = False


# ════════════════════════════════════════════════════════════════════════════
# Pages
# ════════════════════════════════════════════════════════════════════════════
class BeaniePage(QWidget):
    """The home screen — floating orb + BEANIE branding + quick actions."""

    def __init__(self, on_talk, on_quick_action, parent=None):
        super().__init__(parent)
        self._on_talk = on_talk
        self._on_quick_action = on_quick_action

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addStretch(1)

        # Orb
        self.orb = PresenceOrbWidget(diameter=200)
        orb_row = QHBoxLayout()
        orb_row.addStretch(1)
        orb_row.addWidget(self.orb)
        orb_row.addStretch(1)
        layout.addLayout(orb_row)

        # Branding
        title = QLabel("BEANIE")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 30px; font-weight: 800; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        subtitle = QLabel("Personal AI")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        self.message = QLabel("I'm here.")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(f"font-size: 13px; color: {TEXT_MUTED}; font-style: italic;")
        layout.addWidget(self.message)

        layout.addSpacing(12)

        # Quick actions (2-col grid)
        self.quick_actions = [
            ("Continue project", "continue_project"),
            ("What's new?", "whats_new"),
            ("Research", "research"),
            ("Talk to me", "talk"),
        ]
        grid = QHBoxLayout()
        for i in range(0, 4, 2):
            col = QVBoxLayout()
            for label, action in self.quick_actions[i:i + 2]:
                btn = QPushButton(label)
                btn.setMinimumHeight(56)
                btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
                btn.clicked.connect(lambda _=False, a=action: self._on_quick_action(a))
                col.addWidget(btn)
            grid.addLayout(col)
        layout.addLayout(grid)

        layout.addSpacing(8)

        # Talk button
        talk = QPushButton("🎙  Talk to Beanie")
        talk.setMinimumHeight(56)
        talk.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        talk.clicked.connect(self._on_talk)
        layout.addWidget(talk)

        layout.addStretch(1)

    def set_message(self, text: str) -> None:
        self.message.setText(text)

    def set_status(self, status: str) -> None:
        self.orb.set_status(status)


class LeftSidebar(QFrame):
    """ChatGPT-style left sidebar: Beanie identity + New Chat + conversation list + nav."""

    def __init__(self, on_new_chat, on_select_conversation, on_nav, on_conversation, parent=None):
        super().__init__(parent)
        self._on_select_conversation = on_select_conversation
        self._on_conversation = on_conversation
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
        name = QLabel("Beanie")
        name.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY};")
        name_col.addWidget(name)
        self.status_label = QLabel("● Offline")
        self.status_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        name_col.addWidget(self.status_label)
        ident.addLayout(name_col)
        ident.addStretch(1)
        layout.addLayout(ident)

        # New chat
        new_chat = QPushButton("+ New Chat")
        new_chat.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        new_chat.clicked.connect(on_new_chat)
        layout.addWidget(new_chat)

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
        chats_label = QLabel("Chats")
        chats_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 600;")
        layout.addWidget(chats_label)
        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet(
            f"background: transparent; color: {TEXT_PRIMARY}; border: none;"
            f" QListWidget::item {{ padding: 8px; border-radius: 6px; }}"
            f" QListWidget::item:selected {{ background: {BG_SURFACE}; }}"
        )
        self.conv_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.conv_list, stretch=1)

        # Navigation (mirrors the web sidebar: Chats / Pansophy / Files / Code / Settings)
        for label, key in [
            ("Chats", "chat"), ("Pansophy", "pansophy"), ("Files", "files"),
            ("Code", "code"), ("Images", "images"), ("Settings", "settings"),
            ("Beanie", "beanie"), ("Tools", "tools"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
            btn.clicked.connect(lambda _=False, k=key: on_nav(k))
            layout.addWidget(btn)

    def _on_item_clicked(self, item) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self._on_select_conversation(cid)

    def set_conversations(self, conversations) -> None:
        self.conv_list.clear()
        for cid, title in conversations:
            item = self.conv_list.addItem(title or "Conversation")
            item.setData(Qt.ItemDataRole.UserRole, cid)

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


class ContextPanel(QFrame):
    """Right context panel: connection + hardware (Goal/Memory/Knowledge are web-only)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet(f"background: {BG_SECONDARY}; border-left: 1px solid {BG_SURFACE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Context")
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        self.body = QLabel("Checking…")
        self.body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.body, stretch=1)

    def set_text(self, text: str) -> None:
        self.body.setText(text)


class FilesPage(QWidget):
    """File search — mirrors the web Files page."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Files")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Search files…")
        self.input.setStyleSheet(_input_style())
        self.input.returnPressed.connect(self._search)
        row.addWidget(self.input, 1)
        btn = QPushButton("Search")
        btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        btn.clicked.connect(self._search)
        row.addWidget(btn)
        layout.addLayout(row)

        self.results = QListWidget()
        self.results.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        layout.addWidget(self.results, 1)

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


class PansophyPage(QWidget):
    """Knowledge / memory — mirrors the web Pansophy page (list view)."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Pansophy")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        refresh = QPushButton("Refresh")
        refresh.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        refresh.clicked.connect(self._load)
        layout.addWidget(refresh)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        layout.addWidget(self.list, 1)
        self._load()

    def _load(self) -> None:
        self.list.clear()
        # Knowledge graph (entities + relationships) from the world model.
        try:
            graph = self._client.knowledge_graph()
            entities = graph.get("entities") or []
            relationships = graph.get("relationships") or []
            self.list.addItem(f"── Knowledge Graph — {len(entities)} entities, {len(relationships)} links ──")
            for e in entities[:150]:
                self.list.addItem(f"• {e.get('name')}  [{e.get('type')}]")
            for r in relationships[:150]:
                self.list.addItem(f"↳ {r.get('predicate')} ({r.get('subject_id', '')[:8]} → {r.get('object_id', '')[:8]})")
            if not entities and not relationships:
                self.list.addItem("(knowledge graph is empty)")
        except BackendConnectionError as e:
            self.list.addItem(f"⚠ knowledge graph: {e}")

        # Memories (vector memory).
        try:
            memories = self._client.list_memories()
            self.list.addItem(f"── Memories ({len(memories)}) ──")
            for m in memories[:150]:
                text = m.get("title") or m.get("content") or str(m)
                self.list.addItem(f"• {text}")
            if not memories:
                self.list.addItem("(no memories yet)")
        except BackendConnectionError as e:
            self.list.addItem(f"⚠ memories: {e}")


class SettingsPage(QWidget):
    """Full settings form (shared across web / desktop / Android via the backend).

    Editable: server URL, API key, wake word, voice (Piper), voice speed, theme,
    language, voice on/off, VAD sensitivity, response delay, and fast/main models.
    Everything except the server URL (which is a local QSettings value) is
    persisted on the backend's shared settings store.
    """

    def __init__(self, settings: DesktopSettings, client: ArenaBackendClient, on_save, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._client = client
        self._on_save = on_save

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        title = QLabel("Settings")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {BG_PRIMARY};")
        container = QWidget()
        container.setStyleSheet(f"background: {BG_PRIMARY};")
        form = QVBoxLayout(container)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(8)

        def section(label_text: str) -> QLabel:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 700; margin-top: 6px;")
            form.addWidget(lbl)
            return lbl

        def field(label_text: str) -> QLineEdit:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            form.addWidget(lbl)
            edit = QLineEdit()
            edit.setStyleSheet(_input_style())
            form.addWidget(edit)
            return edit

        # ── Connection ──
        section("Connection")
        self.url_input = field("Server URL")
        self.url_input.setText(settings.get("server_url"))
        self.api_key_input = field("API key (optional)")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        # ── Voice ──
        section("Voice")
        self.wake_input = field("Wake word")
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.setStyleSheet(_input_style())
        self.voice_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addWidget(QLabel("Voice (Piper)"))
        form.addWidget(self.voice_combo)
        self.speed_input = field("Voice speed (0.5–2.0)")
        self.language_combo = QComboBox()
        self.language_combo.setEditable(True)
        self.language_combo.setStyleSheet(_input_style())
        for lang in ("en_US", "en_GB", "es_ES", "fr_FR", "de_DE", "it_IT", "pt_PT", "nl_NL"):
            self.language_combo.addItem(lang)
        form.addWidget(QLabel("Language"))
        form.addWidget(self.language_combo)
        self.voice_enabled_check = QCheckBox("Voice enabled")
        self.voice_enabled_check.setStyleSheet(f"color: {TEXT_PRIMARY};")
        form.addWidget(self.voice_enabled_check)
        self.vad_input = field("VAD sensitivity (0–100)")
        self.delay_input = field("Response delay (ms)")

        # ── Appearance ──
        section("Appearance")
        self.theme_combo = QComboBox()
        self.theme_combo.setStyleSheet(_input_style())
        self.theme_combo.addItems(["dark", "light"])
        form.addWidget(QLabel("Theme"))
        form.addWidget(self.theme_combo)

        # ── Models ──
        section("Models (LM Studio)")
        self.fast_model_combo = QComboBox()
        self.fast_model_combo.setEditable(True)
        self.fast_model_combo.setStyleSheet(_input_style())
        self.fast_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addWidget(QLabel("Fast model"))
        form.addWidget(self.fast_model_combo)
        self.main_model_combo = QComboBox()
        self.main_model_combo.setEditable(True)
        self.main_model_combo.setStyleSheet(_input_style())
        self.main_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addWidget(QLabel("Main model"))
        form.addWidget(self.main_model_combo)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.status_label.setWordWrap(True)
        form.addWidget(self.status_label)

        form.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

        save = QPushButton("Save")
        save.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        save.clicked.connect(self._save)
        outer.addWidget(save)

        self._load()

    # ── load / save ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        # Start from the local cache (fast, no network) so the theme + fields
        # are populated even if the backend is offline at startup.
        self._set_combo(self.theme_combo, str(self._settings.get("theme") or "dark"))
        self.wake_input.setText(str(self._settings.get("wake_word") or "hey_arena"))

        # Shared settings (wake word, voice, speed, theme, language, api key, models).
        try:
            data = self._client.get_shared_settings()
            self.wake_input.setText(str(data.get("wake_word", "hey_arena")))
            self.speed_input.setText(str(data.get("voice_speed", 1.0)))
            self.vad_input.setText(str(data.get("vad_sensitivity", 50)))
            self.delay_input.setText(str(data.get("response_delay", 500)))
            self.voice_enabled_check.setChecked(bool(data.get("voice_enabled", True)))
            self.api_key_input.setText(str(data.get("api_key", "")))
            self._set_combo(self.theme_combo, str(data.get("theme", "dark")))
            self._set_combo(self.language_combo, str(data.get("language", "en_US")))
            voice = str(data.get("voice", "en_US-lessac-medium"))
            self._set_combo(self.voice_combo, voice)
            self._set_combo(self.fast_model_combo, str(data.get("fast_model", "")))
            self._set_combo(self.main_model_combo, str(data.get("main_model", "")))
        except BackendConnectionError as e:
            self.status_label.setText(f"⚠ {e}")

        # Piper voices (populate the dropdown).
        try:
            voices = self._client.list_piper_voices()
            for v in voices:
                self.voice_combo.addItem(str(v.get("id", "")), str(v.get("id", "")))
        except BackendConnectionError as e:
            app_logger.warning(f"Could not list Piper voices: {e}")

        # LM Studio models (populate fast/main dropdowns).
        try:
            data = self._client.list_models()
            loaded = data.get("loaded_models") or []
            for m in loaded:
                self.fast_model_combo.addItem(str(m))
                self.main_model_combo.addItem(str(m))
        except BackendConnectionError as e:
            app_logger.warning(f"Could not list models: {e}")

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        if not value:
            return
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(value)

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _save(self) -> None:
        url = self.url_input.text().strip()
        self._settings.set("server_url", url)

        theme = self._combo_text(self.theme_combo)
        self._settings.set("theme", theme)

        voice = self._combo_text(self.voice_combo)
        try:
            # Shared settings: wake word / voice / speed / theme / language / …
            self._client.update_shared_settings({
                "wake_word": self.wake_input.text().strip(),
                "voice": voice,
                "voice_speed": float(self.speed_input.text().strip() or "1.0"),
                "voice_enabled": self.voice_enabled_check.isChecked(),
                "language": self._combo_text(self.language_combo),
                "vad_sensitivity": int(float(self.vad_input.text().strip() or "50")),
                "response_delay": int(float(self.delay_input.text().strip() or "500")),
                "theme": self._combo_text(self.theme_combo),
                "api_key": self.api_key_input.text().strip(),
            })
            # Models (LM Studio).
            self._client.update_model_config(
                fast_model=self._combo_text(self.fast_model_combo),
                main_model=self._combo_text(self.main_model_combo),
            )
            # Ensure the active Piper voice matches (idempotent; /settings already
            # applies it, but this also drives /voice/piper-voices active flag).
            if voice:
                self._client.select_piper_voice(voice)
            self.status_label.setText("✓ Saved. Theme applies on next launch.")
        except (BackendConnectionError, ValueError) as e:
            self.status_label.setText(f"⚠ Could not save: {e}")

        if self._on_save:
            self._on_save(url)


class CodePage(QWidget):
    """Code execution — mirrors the web Code page (uses the backend sandbox)."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Code")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        self.code = QTextEdit()
        self.code.setPlaceholderText("Enter Python code…")
        self.code.setStyleSheet(_textarea_style())
        layout.addWidget(self.code, 1)

        run = QPushButton("Run")
        run.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        run.clicked.connect(self._run)
        layout.addWidget(run)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(_textarea_style())
        self.output.setFixedHeight(140)
        layout.addWidget(self.output)

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


class VisionPage(QWidget):
    """Images / Vision — desktop sight (native screen capture) + OCR + image analysis.

    Mirrors the web Images page but adds the native-only killer feature: capturing
    and understanding the host desktop screen (browsers can't do this without a
    screen-capture permission flow). Backed by /vision/capture, /vision/ocr,
    /vision/analyze, /vision/capture-and-analyze, /mobile/camera.
    """

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        self._worker: Optional[VisionWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Images / Vision")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        # ── Desktop sight ──
        sight_label = QLabel("Desktop sight")
        sight_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        layout.addWidget(sight_label)

        self.focus_input = QLineEdit()
        self.focus_input.setPlaceholderText("What should I focus on? (optional, e.g. \"the error dialog\")")
        self.focus_input.setStyleSheet(_input_style())
        layout.addWidget(self.focus_input)

        sight_row = QHBoxLayout()
        self.capture_btn = QPushButton("Capture screen")
        self.capture_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.capture_btn.clicked.connect(self._capture)
        sight_row.addWidget(self.capture_btn)
        self.analyze_btn = QPushButton("Capture & analyze")
        self.analyze_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.analyze_btn.clicked.connect(self._capture_and_analyze)
        sight_row.addWidget(self.analyze_btn)
        layout.addLayout(sight_row)

        # ── Image preview ──
        self.preview = QLabel("No image captured yet")
        self.preview.setMinimumHeight(180)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"background: {BG_PRIMARY}; color: {TEXT_MUTED}; border-radius: 8px;")
        layout.addWidget(self.preview, 1)

        # ── Analyze an image file ──
        file_label = QLabel("Analyze an image file")
        file_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        layout.addWidget(file_label)
        file_row = QHBoxLayout()
        self.file_btn = QPushButton("Choose image…")
        self.file_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.file_btn.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_btn)
        layout.addLayout(file_row)

        # ── Results: OCR + analysis ──
        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setPlaceholderText("OCR text appears here…")
        self.ocr_text.setStyleSheet(_textarea_style())
        self.ocr_text.setFixedHeight(90)
        layout.addWidget(self.ocr_text)

        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlaceholderText("AI analysis appears here…")
        self.analysis_text.setStyleSheet(_textarea_style())
        layout.addWidget(self.analysis_text, 1)

    def _busy(self, busy: bool) -> None:
        for b in (self.capture_btn, self.analyze_btn, self.file_btn):
            b.setEnabled(not busy)

    def _focus(self) -> Optional[str]:
        text = self.focus_input.text().strip()
        return text or None

    def _capture(self) -> None:
        self._start_worker(lambda w: w.capture(self._focus()))

    def _capture_and_analyze(self) -> None:
        self._start_worker(lambda w: w.capture_and_analyze(self._focus()))

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
        )
        if not path:
            return
        self.ocr_text.setPlainText("Uploading and analysing…")
        self.analysis_text.setPlainText("")
        w = VisionWorker(self._client, self)
        w.analyze_upload(path, self._focus())
        self._run_worker(w)

    def _start_worker(self, config) -> None:
        w = VisionWorker(self._client, self)
        config(w)
        self._run_worker(w)

    def _run_worker(self, w: VisionWorker) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
        self._worker = w
        w.result.connect(self._on_result)
        w.preview.connect(self._on_preview)
        w.error.connect(self._on_error)
        self._busy(True)
        w.start()

    @Slot(dict)
    def _on_result(self, res: dict) -> None:
        self._busy(False)
        if not res.get("success"):
            self.analysis_text.setPlainText(f"⚠ {res.get('error', 'Analysis failed')}")
            return
        self.ocr_text.setPlainText(res.get("ocr_text") or res.get("extracted_text") or "(no OCR text)")
        if res.get("screen_changed") is False and res.get("note"):
            self.analysis_text.setPlainText(res.get("note", ""))
        else:
            self.analysis_text.setPlainText(res.get("ai_analysis") or res.get("analysis") or "(no analysis)")

    @Slot(QImage)
    def _on_preview(self, img: QImage) -> None:
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    @Slot(str)
    def _on_error(self, err: str) -> None:
        self._busy(False)
        self.analysis_text.setPlainText(f"⚠ {err}")


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
                f"background: {ACCENT}; color: #FFFFFF; padding: 10px 14px;"
                f" border-radius: 14px; font-size: 14px;"
            )
            row.addStretch(1)
            row.addWidget(self.label)
        else:
            self._orb = PresenceOrbWidget(diameter=30)
            self.label.setStyleSheet(
                f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; padding: 10px 14px;"
                f" border: 1px solid {BG_SURFACE}; border-radius: 14px; font-size: 14px;"
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
        right.setContentsMargins(16, 16, 16, 12)
        right.setSpacing(8)

        # Scrollable message list (widget-based, so orbs animate in place).
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"background: {BG_PRIMARY}; border: 1px solid {BG_SURFACE}; border-radius: 8px;")

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

        composer = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message Beanie…")
        self.input.setStyleSheet(_input_style())
        self.input.returnPressed.connect(self._submit)
        composer.addWidget(self.input, stretch=1)

        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.mic_btn.clicked.connect(self._on_voice)
        composer.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Send")
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
            "listening": "#10B981",
            "recording": "#10B981",
            "processing": "#F59E0B",
            "thinking": "#F59E0B",
            "speaking": "#8B5CF6",
        }
        if status not in labels:
            self.voice_banner.hide()
            return
        label = labels[status]
        color = colors[status]
        self.voice_banner.setText(f'<span style="color:{color};">●</span>  {label}')
        self.voice_banner.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 16px; padding: 6px 14px;"
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


class ToolsPage(QWidget):
    """Native hardware: camera, location, files, status."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        self._camera_thread: Optional[CameraThread] = None
        self._last_frame: Optional[QImage] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        # ── Camera ──
        cam_label = QLabel("Camera")
        cam_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(cam_label)

        self.camera_view = QLabel("Webcam preview")
        self.camera_view.setMinimumHeight(180)
        self.camera_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_view.setStyleSheet(f"background: {BG_PRIMARY}; color: {TEXT_MUTED}; border-radius: 8px;")
        outer.addWidget(self.camera_view)

        cam_row = QHBoxLayout()
        self.cam_start = QPushButton("Start")
        self.cam_start.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.cam_start.clicked.connect(self._start_camera)
        cam_row.addWidget(self.cam_start)
        self.cam_capture = QPushButton("Capture")
        self.cam_capture.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.cam_capture.setEnabled(False)
        self.cam_capture.clicked.connect(self._capture)
        cam_row.addWidget(self.cam_capture)
        self.cam_stop = QPushButton("Stop")
        self.cam_stop.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.cam_stop.setEnabled(False)
        self.cam_stop.clicked.connect(self._stop_camera)
        cam_row.addWidget(self.cam_stop)
        outer.addLayout(cam_row)

        if not CV2_AVAILABLE:
            self.camera_view.setText("OpenCV not installed — pip install opencv-python")
            self.cam_start.setEnabled(False)

        outer.addSpacing(12)

        # ── Location ──
        loc_label = QLabel("Location")
        loc_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(loc_label)
        self.location_label = QLabel("Not resolved")
        self.location_label.setStyleSheet(f"color: {TEXT_MUTED}; padding: 4px;")
        outer.addWidget(self.location_label)
        loc_btn = QPushButton("Resolve my location")
        loc_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        loc_btn.clicked.connect(self._resolve_location)
        outer.addWidget(loc_btn)

        outer.addSpacing(12)

        # ── Files ──
        files_label = QLabel("Files")
        files_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(files_label)
        frow = QHBoxLayout()
        self.files_input = QLineEdit()
        self.files_input.setPlaceholderText("Search files…")
        self.files_input.setStyleSheet(_input_style())
        self.files_input.returnPressed.connect(self._search_files)
        frow.addWidget(self.files_input)
        fbtn = QPushButton("Search")
        fbtn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        fbtn.clicked.connect(self._search_files)
        frow.addWidget(fbtn)
        outer.addLayout(frow)
        self.files_list = QListWidget()
        self.files_list.setStyleSheet(f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; border: 1px solid {BG_SURFACE}; border-radius: 8px;")
        outer.addWidget(self.files_list)

        outer.addSpacing(12)

        # ── Status ──
        status_label = QLabel("Status")
        status_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(status_label)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFixedHeight(90)
        self.status_text.setStyleSheet(_textarea_style())
        outer.addWidget(self.status_text)

    def refresh_status(self) -> None:
        lines = []
        try:
            hw = self._client.hardware_stats()
            lines.append(f"CPU {hw.get('cpu_percent', '?')}% · RAM {hw.get('ram_percent', '?')}% · Disk {hw.get('disk_percent', '?')}%")
        except BackendConnectionError as e:
            lines.append(f"Hardware: ⚠ {e}")
        try:
            st = self._client.status()
            lines.append(f"{st.get('app_name', 'Arena')} — LM Studio {st.get('local_llm_status', '?')}")
        except BackendConnectionError as e:
            lines.append(f"Status: ⚠ {e}")
        self.status_text.setPlainText("\n".join(lines))

    # Camera
    def _start_camera(self) -> None:
        if self._camera_thread is not None and self._camera_thread.isRunning():
            return
        self._camera_thread = CameraThread(self)
        self._camera_thread.frame.connect(self._on_frame)
        self._camera_thread.start()
        self.cam_start.setEnabled(False)
        self.cam_capture.setEnabled(True)
        self.cam_stop.setEnabled(True)

    @Slot(QImage)
    def _on_frame(self, img: QImage) -> None:
        self._last_frame = img
        self.camera_view.setPixmap(QPixmap.fromImage(img).scaled(
            self.camera_view.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _capture(self) -> None:
        if self._last_frame is None:
            QMessageBox.information(self, "Camera", "No frame captured yet.")
            return
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self._last_frame.save(buf, "JPEG")
        data = bytes(buf.data())
        try:
            res = self._client.upload_camera_photo("desktop_capture.jpg", data)
            QMessageBox.information(self, "Camera", f"Photo saved: {res.get('file_name')}")
        except BackendConnectionError as e:
            QMessageBox.warning(self, "Camera", f"Upload failed: {e}")

    def _stop_camera(self) -> None:
        if self._camera_thread is not None:
            self._camera_thread.stop()
            self._camera_thread = None
        self.cam_start.setEnabled(CV2_AVAILABLE)
        self.cam_capture.setEnabled(False)
        self.cam_stop.setEnabled(False)

    # Location
    def _resolve_location(self) -> None:
        self._location_worker = LocationWorker(self._client, self)
        self._location_worker.result.connect(self._on_location)
        self._location_worker.error.connect(self._on_location_error)
        self._location_worker.start()

    @Slot(dict)
    def _on_location(self, data: dict) -> None:
        if data.get("success"):
            lat, lon = data.get("latitude"), data.get("longitude")
            city = data.get("city", "")
            self.location_label.setText(f"{lat}, {lon}" + (f" ({city})" if city else ""))
        else:
            self.location_label.setText(f"Unavailable — {data.get('error', 'unknown')}")

    @Slot(str)
    def _on_location_error(self, err: str) -> None:
        self.location_label.setText(f"Error — {err}")

    # Files
    def _search_files(self) -> None:
        query = self.files_input.text().strip()
        if not query:
            return
        self.files_list.clear()
        try:
            res = self._client.search_files(query)
            results = res if isinstance(res, list) else res.get("results", [])
            for item in results[:50]:
                name = item.get("name") or item.get("path") or str(item)
                self.files_list.addItem(str(name))
            if not results:
                self.files_list.addItem("(no results)")
        except BackendConnectionError as e:
            self.files_list.addItem(f"⚠ {e}")


# ════════════════════════════════════════════════════════════════════════════
# Styles
# ════════════════════════════════════════════════════════════════════════════
def _button_style(bg: str, fg: str) -> str:
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: 10px;"
        f" padding: 10px 14px; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {_lighten(bg, 0.15).name()}; }}"
        f"QPushButton:disabled {{ opacity: 0.5; }}"
    )


def _input_style() -> str:
    return (
        f"QLineEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BG_SURFACE}; border-radius: 8px; padding: 8px 10px; }}"
    )


def _textarea_style() -> str:
    return (
        f"QTextEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BG_SURFACE}; border-radius: 8px; padding: 8px; }}"
    )


# ════════════════════════════════════════════════════════════════════════════
# Main window
# ════════════════════════════════════════════════════════════════════════════
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

        self.settings = DesktopSettings()
        # Persisted server URL overrides the CLI default when set.
        saved_url = self.settings.get("server_url")
        base_url = saved_url if saved_url and saved_url != "http://localhost:8000" else base_url

        self.client = ArenaBackendClient(base_url=base_url)

        # Hydrate the theme from the backend's shared settings (short timeout so
        # an offline backend doesn't block launch), then apply it BEFORE any
        # widget is constructed so the whole window renders in the right palette.
        # This makes the "backend-driven" theme actually two-way: a theme change
        # made on web/Android now re-themes the desktop on next launch.
        try:
            shared = self.client.get_shared_settings(timeout=3.0)
            backend_theme = shared.get("theme")
            if backend_theme in ("dark", "light"):
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
        self.settings_page = SettingsPage(self.settings, self.client, on_save=self._on_save_server_url)
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
        }.get(key, 0)
        self.stack.setCurrentIndex(index)
        if key == "tools":
            self.tools.refresh_status()

    def _on_save_server_url(self, url: str) -> None:
        self.tray.showMessage(
            "Beanie", f"Server URL saved: {url}\nRestart the app to reconnect.",
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )

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
