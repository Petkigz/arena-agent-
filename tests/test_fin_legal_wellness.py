import pytest
import os
from app.tools.financial_legal_wellness import FinancialLegalWellnessSuite

def test_subscription_trial_audit():
    res = FinancialLegalWellnessSuite.audit_subscriptions_and_trials([
        {"service_name": "Cloud Host Trial", "cost_monthly": 29.99, "trial_end_date": "2026-08-15"}
    ])
    assert res["success"] is True
    assert res["total_subscriptions_tracked"] == 1

def test_tos_privacy_audit():
    res = FinancialLegalWellnessSuite.audit_tos_and_privacy_policy("We reserve the right to sell your data to third parties.")
    assert res["success"] is False
    assert res["error_type"] == "model_unavailable"

def test_socratic_tone_sounding_board():
    res = FinancialLegalWellnessSuite.socratic_tone_sounding_board("Per my previous email, as you clearly failed to read...")
    assert res["success"] is False
    assert res["error_type"] == "model_unavailable"

def test_generate_anki_flashcards():
    res = FinancialLegalWellnessSuite.generate_anki_flashcards("Pytest is a testing framework for Python.")
    assert res["success"] is False
    assert res["error_type"] == "model_unavailable"
    assert "anki_file_path" not in res
