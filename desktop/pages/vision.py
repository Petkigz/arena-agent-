"""VisionPage — extracted from monolithic app.py."""

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

        self._title = QLabel("Images / Vision")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        # ── Desktop sight ──
        self._sight_label = QLabel("Desktop sight")
        self._sight_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        layout.addWidget(self._sight_label)

        # Keep the capability boundary visible instead of implying that every
        # installation has a full vision-language model. Object detection and
        # OCR are always attempted; true VLM analysis is optional and its status
        # is reported by the backend.
        self._vision_note = QLabel(
            "Uses OCR + Qwen text analysis + object detection (YOLO/SSD/face). "
            "True VLM analysis is optional and falls back honestly when unavailable."
        )
        self._vision_note.setWordWrap(True)
        self._vision_note.setAccessibleName("Vision capability note")
        self._vision_note.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        layout.addWidget(self._vision_note)

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
        self._file_label = QLabel("Analyze an image file")
        self._file_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        layout.addWidget(self._file_label)
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

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self._sight_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        self._vision_note.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        self.focus_input.setStyleSheet(_input_style())
        self.capture_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.analyze_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.preview.setStyleSheet(f"background: {BG_PRIMARY}; color: {TEXT_MUTED}; border-radius: 8px;")
        self._file_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        self.file_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.ocr_text.setStyleSheet(_textarea_style())
        self.analysis_text.setStyleSheet(_textarea_style())

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
        # P1-1: show grounded detections
        dets = res.get("detections") or res.get("faces") or []
        if dets:
            det_lines = [f"• {d.get('label')} conf {d.get('confidence',0):.2f} bbox {d.get('bbox')}" for d in dets[:20]]
            det_text = "\n".join(det_lines)
            groundings = res.get("groundings_created") or []
            if groundings:
                det_text += f"\n\nGroundings created: {len(groundings)} (engine: {res.get('detection_engine') or res.get('engine','')})"
            # Prepend detections to analysis
            base_analysis = res.get("ai_analysis") or res.get("analysis") or "(no analysis)"
            if res.get("screen_changed") is False and res.get("note"):
                self.analysis_text.setPlainText(f"{res.get('note','')}\n\n{det_text}")
            else:
                self.analysis_text.setPlainText(f"{det_text}\n\n{base_analysis}")
        else:
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

