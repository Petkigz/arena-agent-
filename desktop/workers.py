"""Workers — extracted from monolithic app.py."""

from __future__ import annotations

import math
import sys
from typing import List, Optional

from PySide6.QtCore import QBuffer, QIODevice, QPointF, Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from desktop.backend_client import ArenaBackendClient, BackendConnectionError

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False

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
        # Per-thread client for thread-safety (D2)
        from desktop.backend_client import ArenaBackendClient
        client = ArenaBackendClient(base_url=self._client.base_url, timeout=5.0)
        try:
            if client.is_online():
                self.online.emit()
            else:
                self.offline.emit("Backend not healthy.")
        except BackendConnectionError as e:
            self.offline.emit(str(e))
        finally:
            try:
                client.close()
            except Exception:
                pass


class LocationWorker(QThread):
    result = Signal(dict)
    error = Signal(str)

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        # LocationService.resolve_location() is local (no HTTP), but keep pattern consistent
        # and avoid sharing httpx.Client across threads if future impl uses HTTP
        try:
            from app.tools.location_service import LocationService
            self.result.emit(LocationService.resolve_location())
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
        # D2 fix: create per-thread client so httpx.Client is not shared across QThreads (thread-safety)
        from desktop.backend_client import ArenaBackendClient
        client = ArenaBackendClient(base_url=self._client.base_url, timeout=self._client.timeout)
        try:
            if self._mode == "capture":
                res = client.capture_screen()
            elif self._mode == "capture_analyze":
                res = client.capture_and_analyze(self._prompt_focus)
            elif self._mode == "ocr":
                res = client.ocr_image(self._image_path)
            elif self._mode == "analyze":
                res = client.analyze_image(self._image_path, self._prompt_focus)
            elif self._mode == "analyze_upload":
                up = client.upload_image_file(self._upload_path)
                if not up.get("success"):
                    self.error.emit(f"Upload failed: {up.get('error', 'unknown')}")
                    return
                res = client.analyze_image(up.get("file_path", ""), self._prompt_focus)
                res["image_url"] = up.get("file_url", "")
                res["file_name"] = up.get("file_name", "")
            else:
                self.error.emit("Unknown vision mode.")
                return

            # Try to load the returned image so the UI can preview it.
            url = res.get("image_url") or res.get("file_url")
            if url:
                try:
                    data = client.fetch_image_bytes(url)
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
        finally:
            try:
                client.close()
            except Exception:
                pass


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
# Working context (design review section 4)
# ════════════════════════════════════════════════════════════════════════════


class WorkingContextWorker(QThread):
    """Compose the inline working-context card from existing backend endpoints.

    Same API contract the web context panels use (goals, projects, memories);
    each source is optional — a partial context still renders, an offline
    backend renders nothing (the card simply stays hidden).
    """

    result = Signal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        context: dict = {}
        try:
            goals = self._client.autonomous_goals(limit=5).get("goals", [])
            goal = goals[0] if goals else None
            if goal is not None:
                title = str(goal.get("title", "")).strip()
                if title:
                    context["objective"] = title
        except Exception:
            pass
        try:
            projects = self._client.list_projects(limit=5).get("projects", [])
            project = projects[0] if projects else None
            if project is not None:
                name = str(project.get("name", "")).strip()
                if name:
                    context["project"] = name
        except Exception:
            pass
        try:
            memories = self._client.list_memories()
            if isinstance(memories, list) and memories:
                context["memories"] = len(memories)
        except Exception:
            pass
        self.result.emit(context)
