"""Deterministic recipes — multi-step composition over existing tools.

The real bottleneck after Tier 1 is not tool count, it's *composing* tools into
multi-step plans. A recipe is a thin, deterministic pipeline that chains existing
tools together and returns one typed result — the weak local model only has to
pick a recipe and relay its exact output, never re-derive the steps.

Strong-tools-thin-model: every recipe below is pure code; where an LLM is used at
all (research_digest), it only condenses sources the deterministic search already
returned.

Recipes:
- portfolio_snapshot  — compose many price lookups into one portfolio valuation.
- data_story          — compose dataset inspection + chart generation into one call.
- research_digest     — compose web search + source extraction (+ optional LLM digest).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.llm import llm_client, extract_reply
from app.utils.logger import app_logger


class Recipes:
    # ── portfolio_snapshot ──────────────────────────────────────────────────
    @classmethod
    def portfolio_snapshot(cls, holdings: List[Dict[str, Any]], price_fn: Optional[Callable] = None) -> Dict[str, Any]:
        """Value a portfolio of stocks/cryptos from live (or injected) prices.

        holdings: list of {kind: 'stock'|'crypto', symbol, quantity}.
        price_fn: optional (kind, symbol) -> {success, price} for testing/injection.
        """
        if not isinstance(holdings, list) or not holdings:
            return {"success": False, "error": "holdings must be a non-empty list."}

        items = []
        for h in holdings:
            if not isinstance(h, dict):
                return {"success": False, "error": "Each holding must be a dict."}
            kind = str(h.get("kind", "stock")).lower()
            if kind not in ("stock", "crypto"):
                return {"success": False, "error": "kind must be 'stock' or 'crypto'."}
            symbol = str(h.get("symbol") or h.get("id") or "").strip()
            if not symbol:
                return {"success": False, "error": "Each holding needs a symbol/id."}
            try:
                quantity = float(h.get("quantity", 1))
            except (TypeError, ValueError):
                return {"success": False, "error": f"quantity for '{symbol}' must be a number."}
            if quantity <= 0:
                return {"success": False, "error": f"quantity for '{symbol}' must be > 0."}
            items.append({"kind": kind, "symbol": symbol, "quantity": quantity})

        lookup = price_fn or cls._lookup_price
        results = []
        total = 0.0
        errors = 0
        for it in items:
            try:
                r = lookup(it["kind"], it["symbol"]) or {}
            except Exception as e:
                r = {"success": False, "error": str(e)}
            if r.get("success") and r.get("price") is not None:
                price = float(r["price"])
                value = round(it["quantity"] * price, 2)
                total = round(total + value, 2)
                results.append({**it, "price": price, "value": value})
            else:
                errors += 1
                results.append({**it, "price": None, "value": None, "error": r.get("error", "unavailable")})

        return {
            "success": True,
            "holdings": results,
            "total_value": total,
            "count": len(results),
            "errors": errors,
        }

    @staticmethod
    def _lookup_price(kind: str, symbol: str) -> Dict[str, Any]:
        from app.tools.price_lookup import PriceLookup
        if kind == "crypto":
            r = PriceLookup.get_crypto_price(symbol)
            return {"success": r.get("success"), "price": r.get("price")}
        r = PriceLookup.get_stock_price(symbol)
        return {"success": r.get("success"), "price": r.get("close")}

    # ── data_story ──────────────────────────────────────────────────────────
    @classmethod
    def data_story(cls, file_path: str, x_col: str, y_col: str,
                   chart_type: str = "bar", chart_title: Optional[str] = None) -> Dict[str, Any]:
        """Inspect a dataset AND produce a chart in one step."""
        if not file_path or not str(file_path).strip():
            return {"success": False, "error": "A dataset path is required."}
        try:
            from app.tools.data_analyzer import DataAnalysisEngine
        except Exception:
            return {"success": False, "error": "Data analysis engine is unavailable."}

        summary = DataAnalysisEngine.analyze_dataset(str(file_path))
        if not summary.get("success"):
            return {"success": False, "error": summary.get("error", "Could not inspect dataset.")}

        result = {
            "success": True,
            "file_name": summary.get("file_name"),
            "summary": {
                "rows": summary.get("rows_count"),
                "columns": summary.get("columns_count"),
                "columns_list": summary.get("columns"),
                "missing_values": summary.get("missing_values"),
            },
        }

        chart = DataAnalysisEngine.generate_chart_visualization(
            str(file_path), x_col, y_col, chart_type=chart_type, chart_title=chart_title,
        )
        result["chart"] = chart
        if not chart.get("success"):
            result["chart_error"] = chart.get("error", "Chart generation failed.")
        return result

    # ── research_digest ──────────────────────────────────────────────────────
    @classmethod
    def research_digest(cls, query: str, max_results: int = 3, llm=None) -> Dict[str, Any]:
        """Search the web, extract real sources, and (optionally) digest them.

        The model only sees sources the search actually returned — it cannot
        invent links. Falls back to a deterministic title list if the LLM is empty.
        """
        query = (query or "").strip()
        if not query:
            return {"success": False, "error": "A query is required."}
        max_results = max(1, min(int(max_results), 10))

        try:
            from app.tools.web_research import WebResearcher
            from app.tools.fact_checker import FactChecker
        except Exception:
            return {"success": False, "error": "Web research tool is unavailable."}

        try:
            search = WebResearcher.search_and_scrape(query, max_results=max_results)
        except Exception as e:
            app_logger.warning(f"research_digest search failed: {e}")
            return {
                "success": False,
                "query": query,
                "sources": [],
                "digest": "",
                "error": f"Search failed: {e}",
            }

        sources = FactChecker._extract_sources(search.get("pages", []))
        if not sources:
            return {
                "success": False,
                "query": query,
                "sources": [],
                "digest": "",
                "error": "No usable sources found; no research digest was produced.",
            }

        llm = llm or llm_client
        digest = extract_reply(
            llm.generate_chat_completion(
                messages=[
                    {"role": "system", "content": (
                        "You write a short research digest. Summarize the sources below in "
                        "2-4 sentences. Do NOT add facts or links not present in the sources. "
                        "Output only the digest."
                    )},
                    {"role": "user", "content": (
                        f"Query: {query}\n\nSources:\n" + "\n".join(
                            f"- {s['title']} ({s['url']}): {s['snippet'][:200]}" for s in sources
                        )
                    )},
                ],
                complexity="main", max_tokens=400,
            ),
            fallback="",
        )
        if not digest.strip():
            digest = "Sources: " + "; ".join(s["title"] for s in sources)
        return {"success": True, "query": query, "sources": sources, "digest": digest.strip()}
