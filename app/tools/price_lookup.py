"""Price / portfolio lookup — keyless crypto and stock quotes.

Deterministic httpx calls to free, keyless public endpoints:
- Crypto: CoinGecko `simple/price` (no API key).
- Stocks: Stooq CSV quote endpoint (no API key).

No LLM. Typed `{"success": bool, ...}` responses; offline/unreachable degrades to
a clear error. Parsers are separate static methods so they're unit-testable
without the network.

Safety model (manifest authoritative): Level 0 (read-only public data).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Optional

import httpx

from app.utils.logger import app_logger


class PriceLookup:
    @classmethod
    def get_crypto_price(cls, coin_id: str, currency: str = "usd") -> Dict[str, Any]:
        """Get the current price of a cryptocurrency (CoinGecko, keyless)."""
        coin_id = (coin_id or "").strip().lower()
        if not coin_id:
            return {"success": False, "error": "A coin id (e.g. 'bitcoin', 'ethereum') is required."}
        currency = (currency or "usd").strip().lower()
        try:
            resp = httpx.get(
                f"https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": currency},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return cls._parse_coingecko(coin_id, currency, data)
        except httpx.HTTPError as e:
            app_logger.warning(f"CoinGecko fetch failed for {coin_id}: {e}")
            return {"success": False, "error": f"Could not fetch crypto price: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Could not fetch crypto price: {e}"}

    @classmethod
    def get_stock_price(cls, symbol: str) -> Dict[str, Any]:
        """Get the latest stock quote (Stooq CSV, keyless)."""
        symbol = (symbol or "").strip().lower()
        if not symbol:
            return {"success": False, "error": "A stock symbol is required."}
        try:
            resp = httpx.get(
                "https://stooq.com/q/l/",
                params={"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return cls._parse_stooq_csv(resp.text, symbol)
        except httpx.HTTPError as e:
            app_logger.warning(f"Stooq fetch failed for {symbol}: {e}")
            return {"success": False, "error": f"Could not fetch stock price: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Could not fetch stock price: {e}"}

    # ── parsers (deterministic, unit-testable) ──────────────────────────────
    @classmethod
    def _parse_coingecko(cls, coin_id: str, currency: str, data: Dict[str, Any]) -> Dict[str, Any]:
        price = (data or {}).get(coin_id, {}).get(currency)
        if price is None:
            return {"success": False, "error": f"No price found for '{coin_id}' in '{currency}'."}
        return {"success": True, "coin_id": coin_id, "currency": currency, "price": float(price)}

    @classmethod
    def _parse_stooq_csv(cls, text: str, symbol: str) -> Dict[str, Any]:
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) < 2:
            return {"success": False, "error": f"No quote data returned for '{symbol}'."}
        header = [h.strip().lower() for h in rows[0]]
        values = rows[1]
        rec = dict(zip(header, values))
        # Stooq returns "N/D" (no data) when a symbol is invalid.
        if rec.get("close", "").upper() in ("N/D", "N/A", ""):
            return {"success": False, "error": f"No data for symbol '{symbol}' (invalid symbol?)."}
        try:
            return {
                "success": True,
                "symbol": rec.get("symbol", symbol),
                "date": rec.get("date", ""),
                "open": float(rec.get("open", 0)),
                "high": float(rec.get("high", 0)),
                "low": float(rec.get("low", 0)),
                "close": float(rec.get("close", 0)),
                "volume": rec.get("volume", ""),
            }
        except (ValueError, TypeError) as e:
            return {"success": False, "error": f"Could not parse quote: {e}"}
