"""Owner review item 10 (2026-09-01, P2): ADB is simply unavailable
('adb binary not on PATH', pack probe skipped). No Arena bug — Android
control cannot be meaningfully tested until ADB is installed and a
device is authorized.

What that REQUIRES of Arena while the capability is incomplete (same
honesty contract as item 9's VLM):
  * the unavailable state is reported HONESTLY at every layer — the
    pack probe skips with the reason, the capability ladder probes
    phone.adb to unavailable (gating to DEFER), and
    list_connected_devices must not claim success=True when the adb
    binary cannot even run (a vacuous success makes the /android/devices
    endpoint and its unit test 'pass' while measuring nothing);
  * claim surfaces name the ADB requirement — phone tool descriptions
    don't get to imply Android control works unconditionally;
  * the actionable path is visible: install platform-tools, connect
    and authorize a device.
"""

from unittest.mock import patch

from app.tools.android_adb_controller import AndroidADBController


ADB_MISSING_RES = {
    "success": False,
    "stdout": "",
    "stderr": "ADB Error: [Errno 2] No such file or directory: 'adb'",
}
ADB_NO_DEVICE_RES = {
    "success": True,
    "stdout": "List of devices attached\n\n",
    "stderr": "",
}
ADB_DEVICE_RES = {
    "success": True,
    "stdout": "List of devices attached\nemulator-5554\tdevice\n",
    "stderr": "",
}


# ── the measurement itself: list_connected_devices ──────────────────────

def test_list_devices_adb_missing_is_honest_failure():
    """adb cannot run → success=False with the reason and the install
    path. success=True with an empty list here would be a vacuous
    measurement (the old behavior — and the old unit test passed on it
    in environments without adb)."""
    with patch.object(AndroidADBController, "run_adb_cmd", return_value=ADB_MISSING_RES):
        res = AndroidADBController.list_connected_devices()
    assert res["success"] is False
    assert res["connected_android_devices"] == []
    note = str(res.get("note", "")).lower()
    assert "adb" in note
    assert "platform-tools" in note or "install" in note


def test_list_devices_adb_present_no_device_is_success_with_empty_list():
    """adb runs and finds nothing: the command SUCCEEDED — the honest
    answer is success=True with an empty device list (plus a hint to
    connect/authorize). Distinct from adb-not-runnable."""
    with patch.object(AndroidADBController, "run_adb_cmd", return_value=ADB_NO_DEVICE_RES):
        res = AndroidADBController.list_connected_devices()
    assert res["success"] is True
    assert res["connected_android_devices"] == []


def test_list_devices_adb_device_connected():
    with patch.object(AndroidADBController, "run_adb_cmd", return_value=ADB_DEVICE_RES):
        res = AndroidADBController.list_connected_devices()
    assert res["success"] is True
    assert res["connected_android_devices"] == ["emulator-5554"]


# ── the availability probe (drives the capability ladder → DEFER) ───────

def test_is_adb_available_false_when_adb_missing():
    with patch.object(AndroidADBController, "run_adb_cmd", return_value=ADB_MISSING_RES):
        assert AndroidADBController.is_adb_available() is False


def test_is_adb_available_false_with_no_device():
    with patch.object(AndroidADBController, "run_adb_cmd", return_value=ADB_NO_DEVICE_RES):
        assert AndroidADBController.is_adb_available() is False


def test_is_adb_available_true_with_device():
    with patch.object(AndroidADBController, "run_adb_cmd", return_value=ADB_DEVICE_RES):
        assert AndroidADBController.is_adb_available() is True


def test_capability_ladder_probes_phone_adb_to_unavailable(tmp_path):
    """The ladder's honest unavailable → the cycle defers (pinned end to
    end elsewhere); here: the ladder entry itself carries probed-False
    with the ADB probe as its basis.

    The runtime CONSTRUCTOR claims the process-wide singleton (the 'one
    brain' invariant, runtime.py line ~294) — this file sorts before
    test_audit_release_blockers.py, so the previous singleton MUST be
    restored or the tmp runtime clobbers it for every later test."""
    from app.cognition.runtime import CognitiveRuntime
    previous = CognitiveRuntime._instance
    try:
        rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
        status = rt.check_capability_status(["phone.adb"], "mobile_phone")
    finally:
        CognitiveRuntime._instance = previous
    entry = status["phone.adb"]
    assert entry["supported"] is True
    assert entry["available"] is False
    assert entry["ready"] is False
    assert "adb" in entry["evidence"].lower()


# ── claim surfaces: tool descriptions name the ADB requirement ──────────

def test_phone_tool_descriptions_name_the_adb_requirement():
    """Android control is conditional on adb + an authorized device; the
    tool listing says so (no unconditional 'control your phone')."""
    from app.cognition.tool_registry import capability_entry
    for name in ("phone_command", "phone_sms", "phone_call"):
        entry = capability_entry(name)
        assert entry is not None, name
        assert "adb" in str(entry.get("description", "")).lower(), name


# ── the pack probe skips honestly ───────────────────────────────────────

def test_pack_probe_skips_with_reason_when_adb_unavailable():
    import scripts.owner_diagnostics as od
    with patch.object(AndroidADBController, "is_adb_available", return_value=False):
        status, detail = od.h_adb_phone()
    assert status == "skip"
    assert "adb" in detail.lower()
