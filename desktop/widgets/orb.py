"""Presence orb widget — extracted from monolithic app.py."""

from __future__ import annotations

import math

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from desktop.theme import PRESENCE_COLORS, PRESENCE_DURATIONS, _lighten

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

