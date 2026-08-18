import pytest
import os
from app.memory.human_nature_engine import HumanNatureEngine
from app.tools.universal_media_learner import UniversalMediaLearner
from app.tools.opsec_manager import OpSecManagerTool
from app.tools.pentest_company_assistant import PentestCompanyAssistant

def test_human_nature_engine():
    # Test emotional tone analysis
    analysis = HumanNatureEngine.analyze_emotional_tone("I'm really stressed and overwhelmed with this urgent deadline")
    assert analysis["detected_state"] == "stressed"
    assert analysis["warmth_level"] > 0.5

    # Test assimilation of human experience
    assim = HumanNatureEngine.assimilate_human_experience(
        user_text="I prefer direct code answers and dry humor",
        assistant_response="Understood, boss.",
        feedback="Perfect"
    )
    assert assim["success"] is True
    assert assim["memory_id"] is not None

def test_universal_media_learner():
    # Test webpage media scraping & analysis
    res = UniversalMediaLearner.analyze_media_target(
        target_url_or_path="https://example.com",
        prompt_focus="ad strategy and video embeds"
    )
    assert res["success"] is True
    assert "platform_type" in res

def test_opsec_manager():
    # Test digital footprint scan
    footprint = OpSecManagerTool.audit_digital_footprint("user@example.com")
    assert footprint["success"] is True
    assert "findings" in footprint

    # Test erasure request generation
    erasure = OpSecManagerTool.generate_erasure_requests(
        target_service_name="DataBrokerCorp",
        user_identifier="user@example.com"
    )
    assert erasure["success"] is True
    assert "erasure_letter_draft" in erasure
    assert "Right to Erasure" in erasure["erasure_letter_draft"]

def test_pentest_company_assistant():
    # Test RoE drafting
    roe = PentestCompanyAssistant.draft_rules_of_engagement(
        client_company_name="Apex Financial Systems",
        authorized_ip_ranges=["10.0.0.0/24", "api.apexfin.com"]
    )
    assert roe["success"] is True
    assert "RULES OF ENGAGEMENT" in roe["roe_document_text"]

    # Test Pentest Report generation
    report = PentestCompanyAssistant.generate_pentest_report(
        client_company_name="Apex Financial Systems",
        vulnerabilities_found=[{
            "title": "Remote Code Execution via Deserialization",
            "severity": "CRITICAL",
            "cvss_v3_score": 9.8,
            "description": "Untrusted Java object deserialization endpoint.",
            "remediation": "Disable default deserialization and implement strict object whitelisting."
        }]
    )
    assert report["success"] is True
    assert os.path.exists(report["report_path"])
