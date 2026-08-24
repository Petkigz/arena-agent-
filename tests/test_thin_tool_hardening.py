"""
Hardening tests for the deepened thin tools: pentest, coder_brain,
knowledge_domains, security_education, music_studio.
"""

from unittest.mock import patch

from app.tools.pentest_company_assistant import PentestCompanyAssistant
from app.tools.coder_brain import CoderBrainTool
from app.tools.knowledge_domains import KnowledgeDomainsTool
from app.tools.security_education import SecurityEducationTool
from app.tools.music_studio import MusicStudioTool


# ── pentest_company_assistant ───────────────────────────────────────────────
def test_pentest_requires_client():
    assert PentestCompanyAssistant.generate_pentest_report("")["success"] is False


def test_pentest_roe_requires_targets():
    assert PentestCompanyAssistant.draft_rules_of_engagement("x", [])["success"] is False
    assert PentestCompanyAssistant.draft_rules_of_engagement("x", None)["success"] is False


def test_pentest_llm_failure_is_graceful(monkeypatch):
    def llm_raises(**kw):
        raise RuntimeError("llm down")
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", llm_raises)
    res = PentestCompanyAssistant.generate_pentest_report(
        "Acme", target_scope=["192.168.1.0/24"],
        vulnerabilities_found=[{"title": "Observed issue", "description": "evidence", "remediation": "fix"}],
    )
    assert res["success"] is False
    assert "failed" in res["error"]


def test_pentest_roe_success(monkeypatch):
    # Avoid DB writes in tests.
    monkeypatch.setattr("app.tools.pentest_company_assistant.db.create_audit_log", lambda *a, **k: 0)
    res = PentestCompanyAssistant.draft_rules_of_engagement("Acme", ["192.168.1.0/24"])
    assert res["success"] is True
    assert "Acme" in res["roe_document_text"]


# ── coder_brain ─────────────────────────────────────────────────────────────
def test_coder_requires_code():
    assert CoderBrainTool.explain_and_debug_code("")["success"] is False
    assert CoderBrainTool.generate_unit_tests("   ")["success"] is False


def test_coder_rejects_bad_language():
    res = CoderBrainTool.explain_and_debug_code("print(1)", language="brainfuck")
    assert res["success"] is False
    assert "Unsupported language" in res["error"]


def test_coder_accepts_valid_language(monkeypatch):
    fake = {"choices": [{"message": {"content": "explained"}}]}
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)
    res = CoderBrainTool.explain_and_debug_code("print(1)", language="python")
    assert res["success"] is True


def test_coder_tests_dont_crash_on_save_failure(monkeypatch):
    fake = {"choices": [{"message": {"content": "def test_x(): ..."}}]}

    def save_fails(*a, **k):
        raise OSError("no disk")

    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)
    monkeypatch.setattr("app.tools.doc_manager.DocumentManager.create_document", save_fails)

    res = CoderBrainTool.generate_unit_tests("def add(a,b): return a+b", "python")
    assert res["success"] is True
    assert res["test_file_path"] is None  # graceful, not a crash


# ── knowledge_domains ───────────────────────────────────────────────────────
def test_legal_requires_topic():
    assert KnowledgeDomainsTool.legal_compliance_consult("")["success"] is False


def test_counseling_requires_input():
    assert KnowledgeDomainsTool.psychological_counseling_partner("  ")["success"] is False


def test_counseling_includes_disclaimer(monkeypatch):
    fake = {"choices": [{"message": {"content": "I hear you."}}]}
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)
    res = KnowledgeDomainsTool.psychological_counseling_partner("I feel anxious")
    assert res["success"] is True
    assert "disclaimer" in res


def test_finance_calc_validates_numbers():
    assert KnowledgeDomainsTool.accounting_finance_calc("abc", 10)["success"] is False
    assert KnowledgeDomainsTool.accounting_finance_calc(100, 50, tax_rate_percent=150)["success"] is False


def test_finance_calc_succeeds():
    res = KnowledgeDomainsTool.accounting_finance_calc(1000, 400, tax_rate_percent=20)
    assert res["success"] is True
    assert res["gross_profit"] == 600.0
    assert res["net_income"] == 480.0  # 600 - (600*0.20)


# ── security_education ──────────────────────────────────────────────────────
def test_security_audit_requires_code():
    assert SecurityEducationTool.audit_code_defensively("")["success"] is False


# ── music_studio ────────────────────────────────────────────────────────────
def test_music_requires_genre():
    assert MusicStudioTool.generate_vocal_chain_guide("")["success"] is False
