# Auto-generated Pytest Contract by ASTJanitor for sample_janitor_tool
import pytest
from app.tools.app_inventory import SystemAppInventory

def test_auto_generated_sample_janitor_tool_contract():
    res = SystemAppInventory.get_installed_apps_count()
    assert res >= 0
