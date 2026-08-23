"""Fact-check / citation — assess a claim against live web sources, with real links.

Strong-tools-thin-model + honesty: the *search* is real (reuses the existing
`WebResearchTool.search_and_scrape`), and every citation is a URL that was
actually returned by that search — the LLM is only allowed to pick a verdict and
write a justification, never to invent a source or link.

Verdicts are tri-state (SUPPORTED / REFUTED / UNVERIFIABLE) so a claim we can't
back up is reported as unverifiable, not silently affirmed.

Safety model (manifest authoritative): Level 0 (read-only; fetches public pages).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.llm import llm_client, extract_reply
from app.utils.logger import app_logger

_VERDICTS = ("supported", "refuted", "unverifiable")


class FactChecker:
    @classmethod
    def fact_check(cls, claim: str, max_results: int = 3, llm=None) -> Dict[str, Any]:
        """Verify a claim against web sources; return a verdict + real citations."""
        claim = (claim or "").strip()
        if not claim:
            return {"success": False, "error": "A claim is required."}
        max_results = max(1, min(int(max_results), 10))

        try:
            from app.tools.web_research import WebResearcher
        except Exception:
            return {"success": False, "error": "Web research tool is unavailable."}

        try:
            search = WebResearcher.search_and_scrape(claim, max_results=max_results)
        except Exception as e:
            app_logger.warning(f"Fact-check search failed: {e}")
            return {
                "success": True,
                "search_success": False,
                "evidence_available": False,
                "claim": claim,
                "verdict": "unverifiable",
                "justification": f"Could not search for sources (search failed: {e}).",
                "citations": [],
                "evidence": [],
            }

        sources = cls._extract_sources(search.get("pages", []))
        if not sources:
            return {
                "success": True,
                "search_success": bool(search.get("success", False)),
                "evidence_available": False,
                "claim": claim,
                "verdict": "unverifiable",
                "justification": "No usable sources were found for this claim.",
                "citations": [],
                "evidence": [],
            }

        llm = llm or llm_client
        digest = "\n".join(
            f"[{i}] {s['title']} ({s['url']})\n    {s['snippet'][:300]}"
            for i, s in enumerate(sources, 1)
        )
        system = (
            "You fact-check a claim against the sources provided. Output exactly two lines: "
            "Line 1: VERDICT: one of SUPPORTED, REFUTED, UNVERIFIABLE. "
            "Line 2: JUSTIFICATION: one concise sentence citing the source numbers (e.g. [1][3]). "
            "Do not cite any source number that is not in the list, and do not invent facts."
        )
        user = f"Claim: {claim}\n\nSources:\n{digest}"
        reply = extract_reply(
            llm.generate_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                complexity="main", max_tokens=300,
            ),
            fallback="",
        )
        verdict, justification = cls._parse_verdict(reply)

        return {
            "success": True,
            "search_success": True,
            "evidence_available": True,
            "claim": claim,
            "verdict": verdict,
            "justification": justification,
            # Every citation below is a URL the search actually returned.
            "citations": [{"title": s["title"], "url": s["url"]} for s in sources],
            "evidence": [{"title": s["title"], "url": s["url"], "snippet": s["snippet"]} for s in sources],
        }

    # ── deterministic helpers ───────────────────────────────────────────────
    @classmethod
    def _extract_sources(cls, pages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        out = []
        for p in pages or []:
            if not isinstance(p, dict):
                continue
            url = (p.get("url") or "").strip()
            if not url:
                continue
            title = (p.get("title") or p.get("domain") or url).strip()
            snippet = (p.get("content") or "").strip()
            out.append({"title": title, "url": url, "snippet": snippet})
        return out

    @classmethod
    def _parse_verdict(cls, reply: str):
        """Parse the model's two-line output; default to UNVERIFIABLE on garbage."""
        verdict = "unverifiable"
        justification = reply.strip() or "No justification produced."
        for line in reply.splitlines():
            if line.strip().upper().startswith("VERDICT:"):
                v = line.split(":", 1)[1].strip().lower()
                if v in _VERDICTS:
                    verdict = v
            elif line.strip().upper().startswith("JUSTIFICATION:"):
                justification = line.split(":", 1)[1].strip() or justification
        return verdict, justification
