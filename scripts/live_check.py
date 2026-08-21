#!/usr/bin/env python3
"""Live verification of tools that need real network / credentials.

The sandbox has no internet and no API credentials, so the external-API tools
(crypto/stock prices, RSS, web search, Telegram, WhatsApp) are only unit-tested
for parsing/validation/degradation there. Run this on your machine to exercise
them for real:

    python scripts/live_check.py

Each probe reports PASS / FAIL / SKIP:
- PASS   — the tool returned real data.
- FAIL   — the tool errored (worth investigating).
- SKIP   — credentials not configured (Telegram/WhatsApp) — not a failure.

Credentials come from env vars (see app/tools/messaging.py). Exit code is 0 if
nothing FAILED, 1 otherwise — so it can be wired into a CI/manual check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

# Allow `python scripts/live_check.py` to import the app package regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402


def run_live_checks(probes: List[Tuple[str, Callable[[], Dict[str, Any]]]]) -> Dict[str, Any]:
    """Run a list of (name, callable) probes and aggregate a report (pure, testable)."""
    checks = []
    for name, fn in probes:
        try:
            res = fn()
            if not isinstance(res, dict) or "status" not in res:
                res = {"status": "fail", "detail": "probe returned an unexpected result"}
        except Exception as e:
            res = {"status": "fail", "detail": f"raised: {e}"}
        checks.append({"tool": name, **res})

    return {
        "checks": checks,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "failed": sum(1 for c in checks if c["status"] == "fail"),
        "skipped": sum(1 for c in checks if c["status"] == "skip"),
    }


def build_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    """The real probes, wired to the actual tools."""
    from app.tools.price_lookup import PriceLookup
    from app.tools.network_diagnostics import NetworkDiagnostics
    from app.tools.rss_aggregator import RssAggregator

    def crypto():
        r = PriceLookup.get_crypto_price("bitcoin")
        return {"status": "pass", "detail": f"BTC = ${r['price']}"} if r.get("success") else {"status": "fail", "detail": r.get("error")}

    def stock():
        r = PriceLookup.get_stock_price("aapl.us")
        return {"status": "pass", "detail": f"AAPL close = {r['close']}"} if r.get("success") else {"status": "fail", "detail": r.get("error")}

    def dns():
        r = NetworkDiagnostics.resolve_dns("example.com")
        return {"status": "pass", "detail": f"{r['count']} address(es)"} if r.get("success") else {"status": "fail", "detail": r.get("error")}

    def port():
        r = NetworkDiagnostics.check_port("example.com", 443)
        if r.get("success"):
            return {"status": "pass", "detail": "443 open" if r.get("open") else "443 closed/filtered"}
        return {"status": "fail", "detail": r.get("error")}

    def rss():
        r = RssAggregator.fetch_feed("https://news.ycombinator.com/rss")
        return {"status": "pass", "detail": f"{r['count']} item(s)"} if r.get("success") else {"status": "fail", "detail": r.get("error")}

    def search():
        from app.tools.web_research import WebResearcher
        r = WebResearcher.search_and_scrape("python programming", max_results=3)
        n = r.get("results_count", 0)
        return {"status": "pass", "detail": f"{n} scraped page(s)"} if n else {"status": "fail", "detail": "search returned no pages"}

    def telegram():
        token = os.environ.get("ARENA_TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return {"status": "skip", "detail": "ARENA_TELEGRAM_BOT_TOKEN not set"}
        try:
            r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10.0)
            d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 200 and d.get("ok"):
                return {"status": "pass", "detail": f"bot @{d['result'].get('username', '?')}"}
            return {"status": "fail", "detail": d.get("description", f"HTTP {r.status_code}")}
        except Exception as e:
            return {"status": "fail", "detail": str(e)}

    def whatsapp():
        sid = os.environ.get("ARENA_TWILIO_ACCOUNT_SID", "").strip()
        auth = os.environ.get("ARENA_TWILIO_AUTH_TOKEN", "").strip()
        if not (sid and auth):
            return {"status": "skip", "detail": "Twilio credentials not set"}
        try:
            r = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json", auth=(sid, auth), timeout=10.0)
            if r.status_code == 200:
                return {"status": "pass", "detail": r.json().get("friendly_name", "account ok")}
            return {"status": "fail", "detail": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"status": "fail", "detail": str(e)}

    return [
        ("crypto_price", crypto),
        ("stock_price", stock),
        ("dns_lookup", dns),
        ("port_check", port),
        ("rss_fetch", rss),
        ("web_search", search),
        ("telegram", telegram),
        ("whatsapp", whatsapp),
    ]


def main() -> int:
    report = run_live_checks(build_probes())
    print(f"{'TOOL':<14} {'RESULT':<7} DETAIL")
    print("-" * 60)
    for c in report["checks"]:
        print(f"{c['tool']:<14} {c['status'].upper():<7} {c.get('detail', '')}")
    print("-" * 60)
    print(f"passed={report['passed']} failed={report['failed']} skipped={report['skipped']}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
