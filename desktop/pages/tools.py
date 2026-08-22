"""ToolsPage — extracted from monolithic app.py."""

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
        self._cam_label = QLabel("Camera")
        self._cam_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(self._cam_label)

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
        self._loc_label = QLabel("Location")
        self._loc_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(self._loc_label)
        self.location_label = QLabel("Not resolved")
        self.location_label.setStyleSheet(f"color: {TEXT_MUTED}; padding: 4px;")
        outer.addWidget(self.location_label)
        self._loc_btn = QPushButton("Resolve my location")
        self._loc_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self._loc_btn.clicked.connect(self._resolve_location)
        outer.addWidget(self._loc_btn)

        outer.addSpacing(12)

        # ── Files ──
        self._files_label = QLabel("Files")
        self._files_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(self._files_label)
        frow = QHBoxLayout()
        self.files_input = QLineEdit()
        self.files_input.setPlaceholderText("Search files…")
        self.files_input.setStyleSheet(_input_style())
        self.files_input.returnPressed.connect(self._search_files)
        frow.addWidget(self.files_input)
        self._files_btn = QPushButton("Search")
        self._files_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._files_btn.clicked.connect(self._search_files)
        frow.addWidget(self._files_btn)
        outer.addLayout(frow)
        self.files_list = QListWidget()
        self.files_list.setStyleSheet(f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; border: 1px solid {BG_SURFACE}; border-radius: 8px;")
        outer.addWidget(self.files_list)

        outer.addSpacing(12)

        # ── Status ──
        self._status_label = QLabel("Status")
        self._status_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        outer.addWidget(self._status_label)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFixedHeight(90)
        self.status_text.setStyleSheet(_textarea_style())
        outer.addWidget(self.status_text)

    def refresh_theme(self) -> None:
        self._cam_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        self.camera_view.setStyleSheet(f"background: {BG_PRIMARY}; color: {TEXT_MUTED}; border-radius: 8px;")
        self.cam_start.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.cam_capture.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.cam_stop.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self._loc_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        self.location_label.setStyleSheet(f"color: {TEXT_MUTED}; padding: 4px;")
        self._loc_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self._files_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        self.files_input.setStyleSheet(_input_style())
        self._files_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.files_list.setStyleSheet(f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; border: 1px solid {BG_SURFACE}; border-radius: 8px;")
        self._status_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        self.status_text.setStyleSheet(_textarea_style())

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

