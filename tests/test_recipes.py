"""Recipes tests — deterministic multi-step composition (injected prices, real
CSV chart pipeline, mocked search+LLM). No live network/model."""

from unittest.mock import MagicMock

from app.tools.recipes import Recipes


def _prices(price_map):
    def fn(kind, symbol):
        key = (kind, symbol)
        if key in price_map:
            return {"success": True, "price": price_map[key]}
        return {"success": False, "error": "not found"}
    return fn


def test_portfolio_snapshot_totals():
    holdings = [
        {"kind": "stock", "symbol": "aapl", "quantity": 2},
        {"kind": "crypto", "symbol": "bitcoin", "quantity": 0.5},
    ]
    fn = _prices({("stock", "aapl"): 100.0, ("crypto", "bitcoin"): 40000.0})
    res = Recipes.portfolio_snapshot(holdings, price_fn=fn)
    assert res["success"] is True
    assert res["total_value"] == 20200.0  # 200 + 20000
    assert res["count"] == 2
    assert res["errors"] == 0
    assert res["holdings"][0]["value"] == 200.0


def test_portfolio_snapshot_reports_unavailable_holding():
    holdings = [
        {"kind": "stock", "symbol": "aapl", "quantity": 1},
        {"kind": "stock", "symbol": "zzzz", "quantity": 1},
    ]
    fn = _prices({("stock", "aapl"): 10.0})
    res = Recipes.portfolio_snapshot(holdings, price_fn=fn)
    assert res["success"] is True
    assert res["errors"] == 1
    assert res["total_value"] == 10.0
    assert res["holdings"][1]["error"] == "not found"


def test_portfolio_snapshot_validation():
    assert Recipes.portfolio_snapshot([])["success"] is False
    assert Recipes.portfolio_snapshot("notalist")["success"] is False
    assert Recipes.portfolio_snapshot([{"kind": "bond", "symbol": "x"}])["success"] is False
    assert Recipes.portfolio_snapshot([{"kind": "stock"}])["success"] is False
    assert Recipes.portfolio_snapshot([{"kind": "stock", "symbol": "x", "quantity": -1}])["success"] is False


def test_data_story(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("region,sales\nwest,10\neast,20\nwest,30\n", encoding="utf-8")
    res = Recipes.data_story(str(p), "region", "sales", chart_type="bar")
    assert res["success"] is True
    assert res["summary"]["rows"] == 3
    assert res["chart"]["success"] is True
    assert res["chart"]["chart_file_path"]


def test_data_story_missing_file():
    res = Recipes.data_story("/nonexistent/data.csv", "x", "y")
    assert res["success"] is False


def test_research_digest_requires_query():
    assert Recipes.research_digest("")["success"] is False


def test_research_digest_mocked(monkeypatch):
    import app.tools.web_research as wr

    pages = [{"url": "https://src.example", "title": "Source", "content": "content about python"}]
    monkeypatch.setattr(wr.WebResearcher, "search_and_scrape", classmethod(lambda cls, *a, **k: {"pages": pages}))

    llm = MagicMock()
    llm.generate_chat_completion.return_value = {"choices": [{"message": {"content": "Python is popular."}}]}
    res = Recipes.research_digest("python", llm=llm)
    assert res["success"] is True
    assert res["sources"][0]["url"] == "https://src.example"
    assert res["digest"] == "Python is popular."


def test_research_digest_search_fails_gracefully(monkeypatch):
    import app.tools.web_research as wr

    def boom(cls, *a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(wr.WebResearcher, "search_and_scrape", classmethod(boom))
    res = Recipes.research_digest("python")
    assert res["success"] is False
    assert res["sources"] == []
    assert res["digest"] == ""
    assert "Search failed" in res["error"]
