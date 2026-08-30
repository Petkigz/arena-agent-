"""P0 bottleneck #11: SUPPORTED / AVAILABLE / READY are separate concepts.
'microphone.capture' used to be marked True in NATIVE_CAPABILITIES with no
implementation anywhere — 'architecture supports it' posing as 'the device
is available right now'. Now every capability reports the honest ladder."""
from unittest.mock import patch

from app.cognition.runtime import CognitiveRuntime


def _rt(tmp_path):
    return CognitiveRuntime(db_path=str(tmp_path / "rt.db"))


def _probe(cam=lambda: True):
    return patch.dict(CognitiveRuntime._CAPABILITY_PROBES, {"camera": cam})


def test_microphone_is_unsupported_not_ready(tmp_path):
    """No microphone implementation exists in the codebase: 'supported' must
    be False — the old blanket True was architectural fiction."""
    status = _rt(tmp_path).check_capability_status(["microphone.capture", "microphone.record"], "desktop_os")
    for cap, s in status.items():
        assert s["supported"] is False
        assert s["available"] is False
        assert s["ready"] is False
        assert s["status"] == "unsupported"
        assert "no implementation" in s["evidence"].lower()


def test_camera_supported_and_unavailable_when_probe_fails(tmp_path):
    """The three concepts separate: an IMPLEMENTED capability whose device
    probe fails is supported=True, available=False (not unsupported)."""
    rt = _rt(tmp_path)
    with _probe(cam=lambda: False):
        s = rt.check_capability_status(["camera.capture"], "desktop_os")["camera.capture"]
    assert s["supported"] is True
    assert s["available"] is False
    assert s["ready"] is False
    assert s["status"] == "unavailable"

    with _probe(cam=lambda: True):
        s = rt.check_capability_status(["camera.capture"], "desktop_os")["camera.capture"]
    assert s["status"] == "ready" and s["ready"] is True


def test_unprobeable_stays_unverified_never_optimistic(tmp_path):
    """LLM/web availability would cost a live call: available=None means
    'honestly unverified', and the cap stays attemptable (ready=True) —
    failures then surface honestly at execution, per the item-1 contract."""
    s = _rt(tmp_path).check_capability_status(["llm.generate", "web.search"], "desktop_os")
    assert s["llm.generate"]["supported"] is True
    assert s["llm.generate"]["available"] is None
    assert s["llm.generate"]["ready"] is True
    assert s["llm.generate"]["status"] == "supported_unverified"


def test_registered_tools_report_their_own_availability(tmp_path):
    """A registered tool's availability comes from its own checker (probed):
    an unconfigured integration defers honestly instead of 'handler=ready'."""
    rt = _rt(tmp_path)
    with patch.object(rt.registry, "get_tool_availability",
                      return_value={"available": False, "status": "not_configured"}):
        s = rt.check_capability_status(["send_telegram"], "messaging")["send_telegram"]
    assert s["supported"] is True
    assert s["available"] is False
    assert s["status"] == "unavailable"

    with patch.object(rt.registry, "get_tool_availability",
                      return_value={"available": True, "status": "available"}):
        s = rt.check_capability_status(["send_telegram"], "messaging")["send_telegram"]
    assert s["status"] == "ready"


def test_not_checked_is_unverified_not_unavailable(tmp_path):
    """A checker returning available=None ('not_checked') must stay
    unverified — coercing it to False would defer nearly everything."""
    rt = _rt(tmp_path)
    with patch.object(rt.registry, "get_tool_availability",
                      return_value={"available": None, "status": "not_checked"}):
        s = rt.check_capability_status(["ping"], "network")["ping"]
    assert s["available"] is None
    assert s["ready"] is True
    assert s["status"] == "supported_unverified"


def test_phone_probe_determines_availability(tmp_path):
    rt = _rt(tmp_path)
    with patch("app.tools.android_adb_controller.AndroidADBController.is_adb_available",
               return_value=False):
        s = rt.check_capability_status(["phone.sms"], "mobile_phone")["phone.sms"]
    assert s["supported"] is True and s["available"] is False and s["ready"] is False
    with patch("app.tools.android_adb_controller.AndroidADBController.is_adb_available",
               return_value=True):
        s = rt.check_capability_status(["phone.sms"], "mobile_phone")["phone.sms"]
    assert s["status"] == "ready"


def test_availability_map_stays_bool_backward_compatible(tmp_path):
    rt = _rt(tmp_path)
    with _probe(cam=lambda: True):
        caps = rt.check_capability_availability(
            ["camera.capture", "location.resolve", "microphone.capture"], "desktop_os")
    assert caps == {"camera.capture": True, "location.resolve": True, "microphone.capture": False}
    assert all(isinstance(v, bool) for v in caps.values())


def test_invented_phrases_still_cannot_veto(tmp_path):
    status = _rt(tmp_path).check_capability_status(
        ["ability to express emotions verbally"], "conversation")
    assert "ability to express emotions verbally" not in status
