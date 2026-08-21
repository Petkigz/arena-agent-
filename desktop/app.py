"""Native Arena desktop window (PySide6 / Qt).

Phase 1: connection status + text chat.
Phase 2: native hardware tabs — camera (live preview + capture), location, files,
         and system status. All hardware access is native (OpenCV webcam, ADB/IP
         location, filesystem) — no browser, no permission prompts.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtCore import QBuffer, QIODevice, Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError

# OpenCV is optional — the camera tab degrades gracefully without it.
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False


class ChatWorker(QThread):
    """Send a chat message to the backend off the UI thread."""

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


class LocationWorker(QThread):
    """Resolve native location off the UI thread."""

    result = Signal(dict)
    error = Signal(str)

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        try:
            self.result.emit(self._client.resolve_location())
        except Exception as e:  # noqa: BLE001 - report any failure to the UI
            self.error.emit(str(e))


class CameraThread(QThread):
    """Live webcam preview — emits a QImage per frame."""

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
                # BGR → RGB for Qt.
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, _ = rgb.shape
                img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                self.frame.emit(img)
                self.msleep(33)  # ~30 fps
        finally:
            if self._cap is not None:
                self._cap.release()

    def stop(self) -> None:
        self._running = False


class MainWindow(QMainWindow):
    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.setWindowTitle("Arena — Local Assistant")
        self.resize(820, 620)

        self.client = ArenaBackendClient(base_url=base_url)
        self._chat_worker: Optional[ChatWorker] = None
        self._camera_thread: Optional[CameraThread] = None
        self._last_frame: Optional[bytes] = None

        self.status_label = QLabel("Connecting…")
        self.statusBar().addWidget(self.status_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_chat_tab(), "Chat")
        tabs.addTab(self._build_camera_tab(), "Camera")
        tabs.addTab(self._build_location_tab(), "Location")
        tabs.addTab(self._build_files_tab(), "Files")
        tabs.addTab(self._build_status_tab(), "Status")
        self.setCentralWidget(tabs)

        self._check_health()

    # ══════════════════════════════════════════════════════════════════════
    # Tab builders
    # ══════════════════════════════════════════════════════════════════════
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

    def _build_camera_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.camera_view = QLabel("Webcam preview")
        self.camera_view.setMinimumSize(640, 360)
        self.camera_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_view.setStyleSheet("background: #0f172a; color: #94a3b8; border-radius: 8px;")
        layout.addWidget(self.camera_view)

        row = QHBoxLayout()
        self.camera_start_btn = QPushButton("Start preview")
        self.camera_start_btn.clicked.connect(self._start_camera)
        row.addWidget(self.camera_start_btn)

        self.camera_capture_btn = QPushButton("Capture photo")
        self.camera_capture_btn.setEnabled(False)
        self.camera_capture_btn.clicked.connect(self._capture_photo)
        row.addWidget(self.camera_capture_btn)

        self.camera_stop_btn = QPushButton("Stop")
        self.camera_stop_btn.setEnabled(False)
        self.camera_stop_btn.clicked.connect(self._stop_camera)
        row.addWidget(self.camera_stop_btn)
        layout.addLayout(row)

        if not CV2_AVAILABLE:
            self.camera_view.setText("OpenCV not installed — run: pip install opencv-python")
            self.camera_start_btn.setEnabled(False)

        return tab

    def _build_location_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.location_label = QLabel("Location: not resolved")
        self.location_label.setStyleSheet("font-size: 14px; padding: 8px;")
        layout.addWidget(self.location_label)

        self.location_btn = QPushButton("Resolve my location")
        self.location_btn.clicked.connect(self._resolve_location)
        layout.addWidget(self.location_btn)
        layout.addStretch()

        return tab

    def _build_files_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        row = QHBoxLayout()
        self.files_input = QLineEdit()
        self.files_input.setPlaceholderText("Search files (e.g. README)…")
        self.files_input.returnPressed.connect(self._search_files)
        row.addWidget(self.files_input)
        self.files_btn = QPushButton("Search")
        self.files_btn.clicked.connect(self._search_files)
        row.addWidget(self.files_btn)
        layout.addLayout(row)

        self.files_list = QListWidget()
        layout.addWidget(self.files_list)

        return tab

    def _build_status_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        layout.addWidget(self.status_text)
        self.status_refresh = QPushButton("Refresh status")
        self.status_refresh.clicked.connect(self._refresh_status)
        layout.addWidget(self.status_refresh)
        return tab

    # ══════════════════════════════════════════════════════════════════════
    # Backend actions
    # ══════════════════════════════════════════════════════════════════════
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
        self._refresh_status()

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

    # ── Camera ─────────────────────────────────────────────────────────────
    def _start_camera(self) -> None:
        if self._camera_thread is not None and self._camera_thread.isRunning():
            return
        self._camera_thread = CameraThread(self)
        self._camera_thread.frame.connect(self._on_frame)
        self._camera_thread.start()
        self.camera_start_btn.setEnabled(False)
        self.camera_capture_btn.setEnabled(True)
        self.camera_stop_btn.setEnabled(True)

    @Slot(QImage)
    def _on_frame(self, img: QImage) -> None:
        self.camera_view.setPixmap(QPixmap.fromImage(img).scaled(
            self.camera_view.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self._last_frame = img

    def _capture_photo(self) -> None:
        if self._last_frame is None:
            QMessageBox.information(self, "Camera", "No frame captured yet.")
            return
        # Encode the QImage to JPEG bytes and upload to the backend.
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self._last_frame.save(buf, "JPEG")
        data = bytes(buf.data())
        try:
            res = self.client.upload_camera_photo("desktop_capture.jpg", data)
            QMessageBox.information(self, "Camera", f"Photo saved: {res.get('file_name')}")
        except BackendConnectionError as e:
            QMessageBox.warning(self, "Camera", f"Upload failed: {e}")

    def _stop_camera(self) -> None:
        if self._camera_thread is not None:
            self._camera_thread.stop()
            self._camera_thread = None
        self.camera_start_btn.setEnabled(CV2_AVAILABLE)
        self.camera_capture_btn.setEnabled(False)
        self.camera_stop_btn.setEnabled(False)

    # ── Location ───────────────────────────────────────────────────────────
    def _resolve_location(self) -> None:
        self.location_btn.setEnabled(False)
        self._location_worker = LocationWorker(self.client, self)
        self._location_worker.result.connect(self._on_location)
        self._location_worker.error.connect(self._on_location_error)
        self._location_worker.start()

    @Slot(dict)
    def _on_location(self, data: dict) -> None:
        self.location_btn.setEnabled(True)
        if data.get("success"):
            lat = data.get("latitude")
            lon = data.get("longitude")
            city = data.get("city", "")
            self.location_label.setText(
                f"Location: {lat}, {lon}" + (f" ({city})" if city else ""))
        else:
            self.location_label.setText(f"Location: unavailable — {data.get('error', 'unknown')}")

    @Slot(str)
    def _on_location_error(self, err: str) -> None:
        self.location_btn.setEnabled(True)
        self.location_label.setText(f"Location: error — {err}")

    # ── Files ──────────────────────────────────────────────────────────────
    def _search_files(self) -> None:
        query = self.files_input.text().strip()
        if not query:
            return
        self.files_list.clear()
        try:
            res = self.client.search_files(query)
            results: List[dict] = res if isinstance(res, list) else res.get("results", [])
            for item in results[:50]:
                name = item.get("name") or item.get("path") or str(item)
                self.files_list.addItem(str(name))
            if not results:
                self.files_list.addItem("(no results)")
        except BackendConnectionError as e:
            self.files_list.addItem(f"⚠ {e}")

    # ── Status ─────────────────────────────────────────────────────────────
    def _refresh_status(self) -> None:
        lines = []
        try:
            hw = self.client.hardware_stats()
            lines.append("Hardware:")
            lines.append(f"  CPU: {hw.get('cpu_percent', '?')}%")
            lines.append(f"  RAM: {hw.get('ram_percent', '?')}% ({hw.get('ram_used_gb', '?')}/{hw.get('ram_total_gb', '?')} GB)")
            lines.append(f"  Disk: {hw.get('disk_percent', '?')}%")
        except BackendConnectionError as e:
            lines.append(f"Hardware: ⚠ {e}")
        try:
            st = self.client.status()
            lines.append("")
            lines.append(f"Status: {st.get('status', '?')} — {st.get('app_name', '')}")
            lines.append(f"LM Studio: {st.get('local_llm_status', '?')}")
        except BackendConnectionError as e:
            lines.append(f"Status: ⚠ {e}")
        self.status_text.setPlainText("\n".join(lines))

    def closeEvent(self, event) -> None:
        self._stop_camera()
        self.client.close()
        super().closeEvent(event)


def run(base_url: str = "http://localhost:8000") -> int:
    app = QApplication(sys.argv)
    window = MainWindow(base_url=base_url)
    window.show()
    return app.exec()
