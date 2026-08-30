"""
Native (browser-free) capability tests: webcam capture and location resolution.

These verify graceful degradation when the underlying hardware/deps are absent,
and that the capability map advertises the new native capabilities.
"""

from unittest.mock import patch

from app.tools.camera_capture import CameraCaptureTool
from app.tools.location_service import LocationService


def test_camera_not_available_without_opencv(monkeypatch):
    monkeypatch.setattr("app.tools.camera_capture.CV2_AVAILABLE", False)
    assert CameraCaptureTool.is_available() is False
    res = CameraCaptureTool.capture_photo()
    assert res["success"] is False
    assert "opencv" in res["error"].lower()


def test_camera_graceful_when_no_device(monkeypatch):
    class _FakeCap:
        def isOpened(self):
            return False

        def release(self):
            pass

    class _FakeCV2:
        VideoCapture = staticmethod(lambda *a, **k: _FakeCap())

    monkeypatch.setattr("app.tools.camera_capture.CV2_AVAILABLE", True)
    monkeypatch.setattr("app.tools.camera_capture.cv2", _FakeCV2)

    res = CameraCaptureTool.capture_photo()
    assert res["success"] is False
    assert "no webcam" in res["error"].lower()


def test_location_resolves_via_ip_when_no_phone(monkeypatch):
    """With no phone (ADB unavailable), location falls back to IP geolocation."""
    fake_phone = {"success": False, "error": "ADB not available"}
    fake_ip = {
        "success": True,
        "source": "ip_geolocation",
        "latitude": 0.35,
        "longitude": 32.58,
        "city": "Kampala",
        "country": "Uganda",
    }
    monkeypatch.setattr(LocationService, "get_phone_location", lambda: fake_phone)
    monkeypatch.setattr(LocationService, "get_ip_location", lambda: fake_ip)

    res = LocationService.resolve_location()
    assert res["success"] is True
    assert res["source"] == "ip_geolocation"
    assert res["city"] == "Kampala"


def test_location_returns_unknown_when_offline(monkeypatch):
    monkeypatch.setattr(LocationService, "get_phone_location", lambda: {"success": False})
    monkeypatch.setattr(LocationService, "get_ip_location", lambda: {"success": False})

    res = LocationService.resolve_location()
    assert res["success"] is False
    assert res["latitude"] is None


def test_native_capabilities_advertised_in_runtime():
    """P0 #11 (honest contract): camera + location are advertised READY
    (backed by real implementations, camera probed); microphone.capture is
    honestly UNSUPPORTED — the old test pinned the architectural fiction
    that marked it True with no implementation anywhere."""
    from unittest.mock import patch
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path="data/cap_probe.db")
    with patch.dict(CognitiveRuntime._CAPABILITY_PROBES, {"camera": lambda: True}):
        caps = rt.check_capability_availability(
            required_capabilities=["camera.capture", "location.resolve", "microphone.capture"],
            target_domain="desktop_os",
        )
    assert caps.get("camera.capture") is True
    assert caps.get("location.resolve") is True
    # No microphone implementation exists — advertising it was fiction.
    assert caps.get("microphone.capture") is False
