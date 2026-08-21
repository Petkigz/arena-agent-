"""BudgetTracker tests — deterministic CSV ledger, totals, and overspend."""

from app.tools.budget_tracker import BudgetTracker


def _add(db, amount, category, kind="expense", date=None, description=""):
    return BudgetTracker.add_transaction(
        amount=amount, category=category, kind=kind, date=date,
        description=description, file_path=str(db),
    )


def test_add_and_summary(tmp_path):
    db = tmp_path / "b.csv"
    assert _add(db, 100, "food")["success"] is True
    assert _add(db, 2000, "salary", kind="income")["success"] is True
    assert _add(db, 50, "food")["success"] is True

    res = BudgetTracker.summary(file_path=str(db))
    assert res["success"] is True
    assert res["total_income"] == 2000.0
    assert res["total_expense"] == 150.0
    assert res["net"] == 1850.0
    assert res["by_category"]["food"] == 150.0
    assert res["transaction_count"] == 3


def test_overspend_detection(tmp_path):
    db = tmp_path / "b.csv"
    _add(db, 120, "food")
    _add(db, 30, "food")
    _add(db, 40, "transport")

    res = BudgetTracker.summary(file_path=str(db), budgets={"food": 100.0, "transport": 100.0})
    assert res["success"] is True
    assert len(res["overspend"]) == 1
    assert res["overspend"][0]["category"] == "food"
    assert res["overspend"][0]["over_by"] == 50.0


def test_month_filter(tmp_path):
    db = tmp_path / "b.csv"
    _add(db, 10, "food", date="2026-01-05")
    _add(db, 20, "food", date="2026-02-05")

    res = BudgetTracker.summary(file_path=str(db), month="2026-01")
    assert res["total_expense"] == 10.0
    assert res["transaction_count"] == 1


def test_list_transactions_filter(tmp_path):
    db = tmp_path / "b.csv"
    _add(db, 10, "food", date="2026-01-05")
    _add(db, 20, "transport", date="2026-01-06")

    res = BudgetTracker.list_transactions(file_path=str(db), category="food")
    assert res["success"] is True
    assert res["count"] == 1
    assert res["transactions"][0]["category"] == "food"


def test_validation(tmp_path):
    db = tmp_path / "b.csv"
    assert _add(db, 0, "food")["success"] is False
    assert _add(db, -5, "food")["success"] is False
    assert _add(db, 10, "")["success"] is False
    assert _add(db, 10, "food", kind="bogus")["success"] is False
    assert _add(db, 10, "food", date="not-a-date")["success"] is False
    assert _add(db, "ten", "food")["success"] is False


def test_empty_ledger_summary(tmp_path):
    res = BudgetTracker.summary(file_path=str(tmp_path / "missing.csv"))
    assert res["success"] is True
    assert res["total_income"] == 0.0
    assert res["total_expense"] == 0.0
    assert res["transaction_count"] == 0


def test_append_only_keeps_history(tmp_path):
    db = tmp_path / "b.csv"
    _add(db, 10, "food")
    _add(db, 20, "food")
    res = BudgetTracker.summary(file_path=str(db))
    assert res["transaction_count"] == 2
    assert res["by_category"]["food"] == 30.0
