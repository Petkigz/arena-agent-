from typing import Dict, Any, Optional
from app.database import db
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class FinanceTraderTool:
    @classmethod
    def calculate_position_size(
        cls, 
        bankroll: float, 
        risk_percent: float = 1.0, 
        entry_price: float = 100.0, 
        stop_loss_price: float = 95.0
    ) -> Dict[str, Any]:
        """
        Calculates safe position size and max risk amount based on bankroll and 1-2% risk rules.
        """
        if bankroll <= 0 or entry_price <= 0:
            return {"success": False, "error": "Bankroll and entry price must be greater than 0."}

        risk_percent = min(max(risk_percent, 0.1), 5.0)  # Max 5% safety cap
        max_risk_amount = bankroll * (risk_percent / 100.0)
        risk_per_unit = abs(entry_price - stop_loss_price)

        if risk_per_unit <= 0:
            return {"success": False, "error": "Entry price and Stop Loss price must not be equal."}

        units = max_risk_amount / risk_per_unit
        total_position_value = units * entry_price

        return {
            "success": True,
            "bankroll": bankroll,
            "risk_percent": risk_percent,
            "max_risk_amount": round(max_risk_amount, 2),
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "recommended_units": round(units, 4),
            "total_position_value": round(total_position_value, 2)
        }

    @classmethod
    def calculate_expected_value(cls, odds_decimal: float, estimated_win_probability: float, stake: float) -> Dict[str, Any]:
        """
        Calculates Expected Value (EV) and Kelly Criterion recommendation for betting or trading setups.
        """
        if odds_decimal <= 1.0 or stake <= 0:
            return {"success": False, "error": "Odds must be greater than 1.0 and stake greater than 0."}

        win_prob = min(max(estimated_win_probability, 0.01), 0.99)
        loss_prob = 1.0 - win_prob
        profit_if_win = (odds_decimal - 1.0) * stake

        ev = (win_prob * profit_if_win) - (loss_prob * stake)
        ev_percent = (ev / stake) * 100.0

        # Kelly Criterion % = (b*p - q) / b where b = odds - 1, p = win_prob, q = loss_prob
        b = odds_decimal - 1.0
        kelly = (b * win_prob - loss_prob) / b
        fractional_kelly = max(kelly * 0.25, 0.0)  # Safe quarter Kelly

        return {
            "success": True,
            "stake": stake,
            "odds_decimal": odds_decimal,
            "win_probability": win_prob,
            "expected_value_amount": round(ev, 2),
            "expected_value_percent": round(ev_percent, 2),
            "is_positive_ev": ev > 0,
            "recommended_kelly_bankroll_fraction_percent": round(fractional_kelly * 100, 2)
        }

    @classmethod
    def log_paper_trade(
        cls, 
        asset_or_event: str, 
        direction: str, 
        entry_val: float, 
        target_val: float, 
        stop_val: float,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Logs a simulated paper trade or bet to SQLite Memory Vault. Live execution is strictly Level 3 blocked.
        """
        allowed, reason, level = PolicyEvaluator.evaluate_action("execute_trade", {"asset": asset_or_event})
        # Live trading is always Level 3 blocked; paper logging is permitted as a simulation
        
        content = (
            f"📈 [PAPER TRADE / BET JOURNAL :: {asset_or_event}]\n"
            f"Direction: {direction.upper()} | Entry: {entry_val} | Target: {target_val} | Stop: {stop_val}\n"
            f"Notes: {notes}\n"
            f"(Simulated Paper Mode - No real capital executed)"
        )

        mem_id = db.create_memory({
            "content": content,
            "category": "paper_journal",
            "source": "paper_trader_tool",
            "confidence": 1.0
        })

        audit_logger.info(f"Logged paper trade journal entry #{mem_id} for '{asset_or_event}'")

        return {
            "success": True,
            "memory_id": mem_id,
            "asset_or_event": asset_or_event,
            "journal_entry": content
        }
