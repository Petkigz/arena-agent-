"""Face detection data (live 2026-09-05): OpenCV 5 wheels no longer
bundle cascade data, so cv2.data.haarcascades is an empty path on
modern installs and every diag run logged "Face cascade not found in
candidates". The cascade is now vendored in app/tools/cascades/ and the
miss-warning fires at most ONCE per process."""

import logging
from pathlib import Path

from app.utils.logger import app_logger


def test_cascade_file_is_vendored():
    vendored = (Path(__file__).resolve().parent.parent
                / "app" / "tools" / "cascades"
                / "haarcascade_frontalface_default.xml")
    assert vendored.exists(), "the vendored cascade must ship with the repo"
    assert vendored.stat().st_size > 100_000  # a real cascade, not a stub


def test_cascade_miss_or_load_logs_at_most_once(caplog):
    from app.tools.object_detector import ObjectDetectorTool
    ObjectDetectorTool._face_cascade = None
    ObjectDetectorTool._face_cascade_missing = False  # fresh process
    old_propagate = app_logger.propagate
    app_logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger="app"):
            for _ in range(3):
                ObjectDetectorTool._ensure_face_cascade()
    finally:
        app_logger.propagate = old_propagate
    cascade_warnings = [r for r in caplog.records
                        if r.levelno == logging.WARNING
                        and "cascade" in r.message.lower()]
    assert len(cascade_warnings) <= 1, (
        "the cascade miss must warn once per process, not per attempt")
    # On a cv2 build with objdetect this LOADS the vendored file (no
    # warning at all); on minimal builds it warns exactly once.
