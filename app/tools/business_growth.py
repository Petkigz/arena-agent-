from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.tools.web_research import WebResearcher
from app.database import db
from app.utils.logger import app_logger, audit_logger

class BusinessGrowthEngine:
    @classmethod
    def discover_opportunities(cls, niche: str, complexity: str = "main") -> Dict[str, Any]:
        """
        Searches web trends & generates realistic, low-capital business opportunities in a niche.
        """
        app_logger.info(f"Conducting opportunity discovery for niche: '{niche}'")
        search_res = WebResearcher.search_and_scrape(f"{niche} trends opportunities business market demand 2026", max_results=3)

        web_context = ""
        if search_res.get("pages"):
            web_context = "\n\nWeb Market Trends:\n" + "\n---\n".join([p["content"][:1500] for p in search_res["pages"]])

        system_prompt = (
            "You are a pragmatic business strategist. Identify high-upside, low-capital "
            "business opportunities based on real market trends and customer pain points."
        )

        user_prompt = f"""
Niche: "{niche}"
{web_context}

Identify 3 high-probability, low-capital business opportunities in this niche. For each, provide:
1. **Opportunity Name & Elevator Pitch**
2. **Customer Pain Point & Target Audience**
3. **Monetization Model** (e.g. SaaS subscription, freelance service, digital product)
4. **First 3 Action Steps to Launch**
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity=complexity,
                max_tokens=900
            )

            opportunity_analysis = llm_res["choices"][0]["message"]["content"] if llm_res.get("choices") else "Opportunities identified."

            # Save opportunity note to SQLite memory
            mem_id = db.create_memory({
                "content": f"💼 [BUSINESS OPPORTUNITIES :: {niche}]\n\n{opportunity_analysis}",
                "category": "business_opportunity",
                "source": "business_growth_engine",
                "confidence": 0.90
            })

            audit_logger.info(f"Logged business opportunities for niche '{niche}' (Memory #{mem_id})")

            return {
                "success": True,
                "niche": niche,
                "opportunity_analysis": opportunity_analysis,
                "memory_id": mem_id
            }
        except Exception as e:
            app_logger.error(f"Error in opportunity discovery: {e}")
            return {"success": False, "error": f"Opportunity discovery error: {str(e)}", "niche": niche}

    @classmethod
    def generate_growth_loop(cls, business_name: str, target_monthly_revenue: float) -> Dict[str, Any]:
        """
        Formulates an A/B testing strategy, customer acquisition channel map, and growth loop plan.
        """
        system_prompt = (
            "You are a growth analytics and marketing loop strategist. "
            "Design actionable customer acquisition growth loops and revenue strategies."
        )

        user_prompt = f"""
Business Name: "{business_name}"
Target Monthly Revenue: ${target_monthly_revenue}

Formulate a complete Growth Engine Plan:
1. **Customer Acquisition Channels**: Top 2 traffic channels (SEO, YouTube, cold outreach, viral shorts).
2. **Growth Loop Mechanism**: How existing users bring in new users.
3. **A/B Testing Experiments**: 2 split tests for pricing, landing page hooks, or ad headlines.
4. **Revenue Math**: Unit economics required to hit ${target_monthly_revenue}/month.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=850
            )

            growth_plan = llm_res["choices"][0]["message"]["content"] if llm_res.get("choices") else "Growth plan generated."

            return {
                "success": True,
                "business_name": business_name,
                "target_monthly_revenue": target_monthly_revenue,
                "growth_plan": growth_plan
            }
        except Exception as e:
            app_logger.error(f"Error generating growth plan: {e}")
            return {"success": False, "error": f"Growth plan error: {str(e)}"}
