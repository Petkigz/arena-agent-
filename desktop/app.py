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
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.settings import DesktopSettings
from desktop.voice_client import DesktopVoiceClient

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False


# ── Theme (mirrors frontend tailwind.config.js) ──────────────────────────────
BG_PRIMARY = "#0F172A"
BG_SECONDARY = "#1E293B"
BG_SURFACE = "#334155"
TEXT_PRIMARY = "#F1F5F9"
TEXT_SECONDARY = "#CBD5E1"
TEXT_MUTED = "#94A3B8"
ACCENT = "#3B82F6"

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


class ChatPage(QWidget):
    def __init__(self, on_send, parent=None):
        super().__init__(parent)
        self._on_send = on_send
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(_textarea_style())
        layout.addWidget(self.log)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message Arena…")
        self.input.setStyleSheet(_input_style())
        self.input.returnPressed.connect(self._submit)
        row.addWidget(self.input)
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.send_btn.clicked.connect(self._submit)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

    def _submit(self) -> None:
        content = self.input.text().strip()
        if content:
            self._on_send(content)

    def append(self, speaker: str, text: str) -> None:
        self.log.append(f"<span style='color:{ACCENT};font-weight:600'>{speaker}:</span>")
        self.log.append(text)
        self.log.append("")


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

    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.setWindowTitle("Arena — Beanie")
        self.resize(520, 760)

        self.settings = DesktopSettings()
        # Persisted server URL overrides the CLI default when set.
        saved_url = self.settings.get("server_url")
        base_url = saved_url if saved_url and saved_url != "http://localhost:8000" else base_url

        self.client = ArenaBackendClient(base_url=base_url)
        self._chat_worker: Optional[ChatWorker] = None

        # Voice (talk to Beanie) — streams mic PCM to the backend.
        ws_url = base_url.replace("http://", "ws://").rstrip("/") + "/ws"
        self.voice = DesktopVoiceClient(ws_url=ws_url, conversation_id="desktop-voice")
        self.voice.on_reply = self._on_voice_reply
        self.voice.on_transcript = self._on_voice_transcript
        self.voice.on_error = self._on_voice_error
        self.voice.on_level = self._on_voice_level
        # Cross-thread: capture thread emits → beanie.set_level runs on GUI thread.
        self._level_signal.connect(self.beanie.set_level)
        self._listening = False

        # Pages
        self.beanie = BeaniePage(on_talk=self._toggle_talk, on_quick_action=self._quick_action)
        self.chat = ChatPage(on_send=self._send_message)
        self.tools = ToolsPage(self.client)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.beanie)   # index 0
        self.stack.addWidget(self.chat)     # index 1
        self.stack.addWidget(self.tools)    # index 2

        # Bottom navigation (Beanie / Chat / Tools)
        nav = QFrame()
        nav.setStyleSheet(f"background: {BG_SECONDARY}; border-top: 1px solid {BG_SURFACE};")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)

        self.nav_buttons = []
        for i, (label, icon) in enumerate([("● Beanie", "beanie"), ("Chat", "chat"), ("Tools", "tools")]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(56)
            btn.setStyleSheet(
                f"QPushButton {{ color: {TEXT_MUTED}; border: none; font-weight: 600; }}"
                f"QPushButton:checked {{ color: {ACCENT}; }}"
            )
            btn.clicked.connect(lambda _=False, idx=i: self._nav_to(idx))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        self.nav_buttons[0].setChecked(True)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.stack)
        central_layout.addWidget(nav)
        self.setCentralWidget(central)

        # Dark theme
        self.setStyleSheet(f"QMainWindow {{ background: {BG_PRIMARY}; }}")
        self._setup_tray()
        self._check_health()

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
        self.tray.hide()
        self.client.close()
        QApplication.instance().quit()

    # ── Navigation ──
    def _nav_to(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 2:
            self.tools.refresh_status()

    # ── Health ──
    def _check_health(self) -> None:
        self._health_worker = HealthWorker(self.client, self)
        self._health_worker.online.connect(self._on_online)
        self._health_worker.offline.connect(self._on_offline)
        self._health_worker.start()

    @Slot()
    def _on_online(self) -> None:
        self.beanie.set_status("idle")
        self.beanie.set_message("I'm here.")

    @Slot(str)
    def _on_offline(self, err: str) -> None:
        self.beanie.set_status("offline")
        self.beanie.set_message("Offline — start the backend.")

    # ── Chat ──
    def _send_message(self, content: str) -> None:
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return
        self.chat.input.clear()
        self.chat.append("You", content)
        self.beanie.set_status("thinking")
        self.beanie.set_message("Thinking…")
        self._chat_worker = ChatWorker(self.client, content, self)
        self._chat_worker.reply_ready.connect(self._on_reply)
        self._chat_worker.error_ready.connect(self._on_chat_error)
        self._chat_worker.start()

    @Slot(str)
    def _on_reply(self, text: str) -> None:
        self.chat.append("Arena", text)
        self.beanie.set_status("idle")
        self.beanie.set_message("I'm here.")

    @Slot(str)
    def _on_chat_error(self, err: str) -> None:
        self.chat.append("System", f"⚠ {err}")
        self.beanie.set_status("offline")
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
            self._nav_to(1)
            self._send_message(prompt)

    def _toggle_talk(self) -> None:
        if self._listening:
            self._stop_voice()
        else:
            self._start_voice()

    def _start_voice(self) -> None:
        if self.voice.start():
            self._listening = True
            self.beanie.set_status("listening")
            self.beanie.set_message("Listening…")
            if self.settings.get("notifications_enabled"):
                self.tray.showMessage("Arena", "Listening… say 'Hey Arena'.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _stop_voice(self) -> None:
        if self._listening:
            self.voice.stop()
            self._listening = False
            self.beanie.set_status("idle")
            self.beanie.set_message("I'm here.")

    # ── Voice callbacks ─────────────────────────────────────────────────────
    def _on_voice_transcript(self, text: str, is_final: bool) -> None:
        if is_final and text.strip():
            self.chat.append("You (voice)", text.strip())
            self.beanie.set_status("thinking")
            self.beanie.set_message("Thinking…")

    def _on_voice_reply(self, text: str) -> None:
        self.chat.append("Arena", text)
        self.beanie.set_status("speaking")
        self.beanie.set_message("Speaking…")
        self._speak(text)
        if self.settings.get("notifications_enabled") and not self.isVisible():
            self.tray.showMessage("Arena", (text[:160] + "…") if len(text) > 160 else text, QSystemTrayIcon.MessageIcon.Information, 5000)
        # Return to idle after a short speaking pause.
        QThread.msleep(0)  # speaking state is cleared below by TTS completion

    def _on_voice_level(self, level: float) -> None:
        self._level_signal.emit(level)

    def _on_voice_error(self, err: str) -> None:
        self.chat.append("System", f"⚠ {err}")
        self._stop_voice()

    def _speak(self, text: str) -> None:
        """Local TTS via pyttsx3 (optional; silently skipped if absent)."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", int(175 * self.settings.get("voice_speed")))
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
        self.beanie.set_status("idle")
        self.beanie.set_message("I'm here.")

    def closeEvent(self, event) -> None:
        self._stop_voice()
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
