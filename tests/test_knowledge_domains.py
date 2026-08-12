import pytest
from app.tools.security_education import SecurityEducationTool
from app.tools.coder_brain import CoderBrainTool
from app.tools.media_studio import MediaStudioTool
from app.tools.knowledge_domains import KnowledgeDomainsTool

def test_defensive_code_audit():
    code = "def login(user, pwd):\n    query = f'SELECT * FROM users WHERE u={user} AND p={pwd}'"
    res = SecurityEducationTool.audit_code_defensively(code, language="python")
    assert res["success"] is True
    assert "audit_report" in res

def test_coder_brain_debug_and_tests():
    code = "def add(a, b): return a + b"
    explain_res = CoderBrainTool.explain_and_debug_code(code, language="python")
    assert explain_res["success"] is True

    test_res = CoderBrainTool.generate_unit_tests(code, language="python")
    assert test_res["success"] is True
    assert test_res["test_file_path"] is not None

def test_media_studio_svg():
    res = MediaStudioTool.generate_svg_graphic("Cyberpunk logo")
    assert res["success"] is True
    assert "<svg" in res["svg_code"]

def test_knowledge_domains_consulting():
    legal_res = KnowledgeDomainsTool.legal_compliance_consult("GDPR compliance for user data")
    assert legal_res["success"] is True

    counsel_res = KnowledgeDomainsTool.psychological_counseling_partner("Feeling overwhelmed with work tasks")
    assert counsel_res["success"] is True

    pnl_res = KnowledgeDomainsTool.accounting_finance_calc(revenue=10000, operating_expenses=4000, tax_rate_percent=20)
    assert pnl_res["success"] is True
    assert pnl_res["net_income"] == 4800.0
