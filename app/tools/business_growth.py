"""Business growth — professional-grade opportunity + growth-loop strategist.

Validates inputs, degrades gracefully when web research/LLM are unavailable, and
returns structured results. Uses safe LLM extraction throughout.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional

from app.llm import llm_client, extract_reply
from app.tools.web_research import WebResearcher
from app.database import db
from app.utils.logger import app_logger, audit_logger


class BusinessGrowthEngine:
    @classmethod
    def discover_opportunities(cls, niche: str, complexity: str = "main") -> Dict[str, Any]:
        """Research + synthesize low-capital opportunities in a niche."""
        if not niche or not niche.strip():
            return {"success": False, "error": "A niche is required."}
        niche = niche.strip()
        app_logger.info(f"Opportunity discovery for niche: '{niche}'")

        # Web research is best-effort — proceed even if it fails.
        web_context = ""
        try:
            search_res = WebResearcher.search_and_scrape(
                f"{niche} trends opportunities market demand 2026", max_results=3
            )
            if isinstance(search_res, dict) and search_res.get("pages"):
                web_context = "\n\nWeb Market Trends:\n" + "\n---\n".join(
                    p.get("content", "")[:1500] for p in search_res["pages"] if isinstance(p, dict)
                )
        except Exception as e:
            app_logger.warning(f"Web research failed (continuing without it): {e}")

        system_prompt = (
            "You are a pragmatic business strategist. Identify high-upside, "
            "low-capital opportunities grounded in real market pain points. "
            "Be specific and actionable; do not fabricate statistics."
        )
        user_prompt = (
            f"Niche: {niche}\n{web_context}\n\n"
            "Identify 3 high-probability, low-capital opportunities. For each provide: "
            "name, customer pain point, target audience, monetization model, "
            "and the first 3 launch steps."
        )

        try:
            analysis = extract_reply(llm_client.generate_chat_completion(
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                complexity=complexity,
                max_tokens=1000,
            ), fallback="")

            if not analysis:
                return {"success": False, "error": "No analysis produced.", "niche": niche}

            mem_id = db.create_memory({
                "content": f"[BUSINESS OPPORTUNITIES :: {niche}]\n\n{analysis}",
                "category": "business_opportunity",
                "source": "business_growth_engine",
                "confidence": 0.90,
            })
            audit_logger.info(f"Logged opportunities for '{niche}' (Memory #{mem_id})")

            return {
                "success": True,
                "niche": niche,
                "opportunity_analysis": analysis,
                "memory_id": mem_id,
                "used_web_research": bool(web_context),
            }
        except Exception as e:
            app_logger.error(f"Opportunity discovery failed: {e}")
            return {"success": False, "error": f"Opportunity discovery error: {e}", "niche": niche}

    @classmethod
    def generate_growth_loop(cls, business_name: str, target_monthly_revenue: float) -> Dict[str, Any]:
        """Design a growth engine (channels, loop, A/B tests, unit economics)."""
        if not business_name or not business_name.strip():
            return {"success": False, "error": "A business name is required."}

        try:
            revenue = float(target_monthly_revenue)
        except (TypeError, ValueError):
            return {"success": False, "error": "target_monthly_revenue must be a number."}
        if revenue <= 0:
            return {"success": False, "error": "target_monthly_revenue must be positive."}

        business_name = business_name.strip()
        system_prompt = (
            "You are a growth analytics and marketing loop strategist. Design "
            "actionable customer-acquisition growth loops with concrete numbers. "
            "Do not fabricate benchmarks; base unit economics on stated inputs."
        )
        user_prompt = (
            f"Business: {business_name}\nTarget monthly revenue: ${revenue:,.0f}\n\n"
            "Provide: (1) top 2 acquisition channels, (2) a growth-loop mechanism, "
            "(3) 2 A/B experiments, (4) the unit economics required to hit target."
        )

        try:
            plan = extract_reply(llm_client.generate_chat_completion(
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                complexity="main",
                max_tokens=1000,
            ), fallback="")

            if not plan:
                return {"success": False, "error": "No plan produced."}

            return {
                "success": True,
                "business_name": business_name,
                "target_monthly_revenue": revenue,
                "growth_plan": plan,
            }
        except Exception as e:
            app_logger.error(f"Growth plan failed: {e}")
            return {"success": False, "error": f"Growth plan error: {e}"}
