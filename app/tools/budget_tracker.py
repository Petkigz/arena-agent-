"""Budget tracker — a deterministic CSV transaction ledger with category totals
and overspend detection. No LLM: the math is all done in code, so reported
numbers can never drift from the ledger.

Schema (CSV): date, kind, category, description, amount
- kind is "income" or "expense".
- amount is a positive number (income adds, expense subtracts).

Safety model (manifest authoritative):
- add_transaction → Level 2 (reversible: append-only, nothing overwritten).
- summary / list_transactions → Level 0 (read).
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger

_COLUMNS = ["date", "kind", "category", "description", "amount"]


class BudgetTracker:
    DEFAULT_FILE = settings.DATA_DIR / "budget.csv"

    @classmethod
    def _resolve(cls, file_path: Optional[str]) -> Path:
        if file_path:
            p = Path(file_path)
            if not p.is_absolute():
                p = settings.BASE_DIR / p
            return p
        return cls.DEFAULT_FILE

    @classmethod
    def add_transaction(
        cls,
        amount: float,
        category: str,
        description: str = "",
        date: Optional[str] = None,
        kind: str = "expense",
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a transaction to the ledger CSV (append-only, never overwrites)."""
        category = (category or "").strip()
        if not category:
            return {"success": False, "error": "category is required."}
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"success": False, "error": "amount must be a number."}
        if amount <= 0:
            return {"success": False, "error": "amount must be greater than zero."}
        kind = (kind or "").strip().lower()
        if kind not in ("income", "expense"):
            return {"success": False, "error": "kind must be 'income' or 'expense'."}
        if date:
            try:
                datetime.date.fromisoformat(date)
            except ValueError:
                return {"success": False, "error": "date must be YYYY-MM-DD."}
        else:
            date = datetime.date.today().isoformat()

        path = cls._resolve(file_path)
        row = {
            "date": date,
            "kind": kind,
            "category": category,
            "description": (description or "").strip(),
            "amount": round(amount, 2),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            exists = path.exists()
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_COLUMNS)
                if not exists:
                    writer.writeheader()
                writer.writerow(row)
            audit_logger.info(f"Added {kind} '{category}' {amount} to budget ledger")
            return {"success": True, "transaction": row, "file_path": str(path)}
        except Exception as e:
            app_logger.warning(f"add_transaction failed: {e}")
            return {"success": False, "error": f"Could not write transaction: {e}"}

    @classmethod
    def _read_rows(cls, file_path: Optional[str]) -> List[Dict[str, Any]]:
        path = cls._resolve(file_path)
        if not path.exists():
            return []
        with open(path, newline="", encoding="utf-8") as f:
            return [row for row in csv.DictReader(f)]

    @classmethod
    def list_transactions(
        cls,
        file_path: Optional[str] = None,
        category: Optional[str] = None,
        month: Optional[str] = None,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """List transactions, optionally filtered by category and/or month (YYYY-MM)."""
        limit = max(1, min(int(limit), 2000))
        rows = cls._read_rows(file_path)
        if category:
            rows = [r for r in rows if r.get("category", "").lower() == category.lower()]
        if month:
            rows = [r for r in rows if (r.get("date") or "").startswith(month)]
        out = rows[:limit]
        for r in out:
            try:
                r["amount"] = float(r["amount"])
            except (ValueError, TypeError):
                r["amount"] = 0.0
        return {"success": True, "count": len(out), "truncated": len(rows) > limit, "transactions": out}

    @classmethod
    def summary(
        cls,
        file_path: Optional[str] = None,
        month: Optional[str] = None,
        budgets: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Compute income/expense/net totals, per-category totals, and overspend.

        budgets is an optional {category: budget_amount} map; any expense category
        whose total exceeds its budget is reported in `overspend`.
        """
        rows = cls._read_rows(file_path)
        if month:
            rows = [r for r in rows if (r.get("date") or "").startswith(month)]

        total_income = 0.0
        total_expense = 0.0
        by_category: Dict[str, float] = {}
        for r in rows:
            try:
                amt = float(r.get("amount", 0))
            except (ValueError, TypeError):
                amt = 0.0
            kind = (r.get("kind") or "expense").lower()
            cat = (r.get("category") or "uncategorized")
            if kind == "income":
                total_income += amt
            else:
                total_expense += amt
                by_category[cat] = round(by_category.get(cat, 0.0) + amt, 2)

        net = round(total_income - total_expense, 2)

        overspend: List[Dict[str, Any]] = []
        if isinstance(budgets, dict):
            for cat, budget in budgets.items():
                try:
                    budget = float(budget)
                except (TypeError, ValueError):
                    continue
                spent = by_category.get(cat, 0.0)
                if spent > budget:
                    overspend.append({
                        "category": cat,
                        "budget": budget,
                        "spent": spent,
                        "over_by": round(spent - budget, 2),
                    })

        return {
            "success": True,
            "total_income": round(total_income, 2),
            "total_expense": round(total_expense, 2),
            "net": net,
            "by_category": {k: round(v, 2) for k, v in sorted(by_category.items())},
            "overspend": overspend,
            "transaction_count": len(rows),
        }
