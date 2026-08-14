import pytest
from app.tools.app_inventory import SystemAppInventory

def test_app_inventory_scanning():
    scan_res = SystemAppInventory.scan_installed_applications()
    assert scan_res["success"] is True
    assert scan_res["total_apps_count"] >= 0
    assert isinstance(scan_res["applications"], list)

def test_app_inventory_launch():
    launch_res = SystemAppInventory.launch_any_app("echo")
    assert "success" in launch_res
