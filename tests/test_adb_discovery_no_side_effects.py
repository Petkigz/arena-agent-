from unittest.mock import patch
from app.tools.android_adb_controller import AndroidADBController


def test_is_adb_available_uses_list_connected_devices_without_side_effects():
    """
    Verify is_adb_available checks connected devices without running user-facing
    operations or battery queries.
    """
    mock_devices_res = {
        "success": True,
        "connected_android_devices": ["emulator-5554"],
        "adb_output": "List of devices attached\nemulator-5554 device\n"
    }

    with patch.object(AndroidADBController, "list_connected_devices", return_value=mock_devices_res) as mock_list:
        available = AndroidADBController.is_adb_available()

        assert available is True
        mock_list.assert_called_once()


def test_is_adb_available_runs_lightweight_adb_devices():
    """
    Verify is_adb_available invokes lightweight adb devices command without dumpsys/shell commands.
    """
    mock_adb_res = {
        "success": True,
        "stdout": "List of devices attached\nemulator-5554 device\n",
        "stderr": ""
    }

    with patch.object(AndroidADBController, "run_adb_cmd", return_value=mock_adb_res) as mock_cmd:
        available = AndroidADBController.is_adb_available()

        assert available is True
        mock_cmd.assert_called_once_with(["devices"])
