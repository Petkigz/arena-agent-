import pytest
import os
from app.tools.ast_janitor import ASTJanitor

def test_ast_janitor_audit():
    res = ASTJanitor.audit_and_refactor_code("app/tools/app_inventory.py")
    assert res["success"] is True
    assert "scan_installed_applications" in res["functions_found"]

def test_ast_janitor_contract_generation():
    res = ASTJanitor.generate_pytest_contract("sample_janitor_tool")
    assert res["success"] is True
    assert os.path.exists(res["test_path"])
