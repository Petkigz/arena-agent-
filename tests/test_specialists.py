import pytest
from app.tools.security_lab import SecurityLabTool
from app.tools.finance_trader import FinanceTraderTool
from app.tools.music_studio import MusicStudioTool
from app.tools.content_creator import ContentCreatorTool

def test_security_lab_scope_enforcement():
    # Authorized target
    assert SecurityLabTool.is_scope_authorized("127.0.0.1") is True
    assert SecurityLabTool.is_scope_authorized("192.168.1.15") is True

    # Unauthorized external target
    scan_res = SecurityLabTool.scan_lab_target("unauthorized-external-site.com")
    assert scan_res["success"] is False
    assert "Security Scope Violation" in scan_res["error"]

def test_finance_trader_position_size():
    res = FinanceTraderTool.calculate_position_size(bankroll=1000, risk_percent=1.0, entry_price=100, stop_loss_price=95)
    assert res["success"] is True
    assert res["max_risk_amount"] == 10.0
    assert res["recommended_units"] == 2.0

def test_finance_ev_calculator():
    res = FinanceTraderTool.calculate_expected_value(odds_decimal=2.5, estimated_win_probability=0.5, stake=10.0)
    assert res["success"] is True
    assert res["is_positive_ev"] is True

def test_finance_paper_trade():
    res = FinanceTraderTool.log_paper_trade("BTC/USD", "LONG", 50000, 55000, 48000, "Breakout setup")
    assert res["success"] is True
    assert res["memory_id"] is not None

def test_music_studio_guide():
    res = MusicStudioTool.generate_vocal_chain_guide("hiphop", "male_rap", "FL Studio")
    assert res["success"] is True
    assert "quick_frequency_cheatsheet" in res

def test_content_creator_script():
    res = ContentCreatorTool.generate_content_script("Local AI Assistant Development", platform="youtube", auto_save_workspace=True)
    assert res["success"] is True
    assert res["draft_file"] is not None
