from typing import Dict, Any, Optional
from app.llm import llm_client, extract_reply
from app.database import db
from app.utils.logger import app_logger, audit_logger

class KnowledgeDomainsTool:
    @classmethod
    def legal_compliance_consult(cls, topic_or_question: str) -> Dict[str, Any]:
        """
        Provides educational legal research, compliance principles (GDPR, Terms of Service, IP Law), and risk analysis.
        """
        system_prompt = (
            "You are a Senior Legal Compliance Analyst. Provide educational legal research, "
            "compliance analysis (GDPR, IP Law, Terms of Service, Contracts), and risk mitigation advice."
        )

        user_prompt = f"Legal Research Topic / Question: \"{topic_or_question}\"\n\nProvide structured analysis with key legal considerations and compliance checkpoints."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            res = llm_client.generate_chat_completion(messages=messages, complexity="main", max_tokens=800)
            analysis = extract_reply(res, fallback="Legal analysis completed.")
            return {"success": True, "topic": topic_or_question, "analysis": analysis}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def psychological_counseling_partner(cls, user_reflection: str) -> Dict[str, Any]:
        """
        Empathetic, active-listening partner grounded in Cognitive Behavioral Therapy (CBT) and active reflection principles.
        """
        system_prompt = (
            "You are a compassionate, active-listening counselor grounded in Cognitive Behavioral Therapy (CBT) principles. "
            "Provide empathetic, thoughtful reflection, reframing unhelpful thought patterns, and encouraging clarity."
        )

        user_prompt = f"User Expression: \"{user_reflection}\"\n\nRespond empathetically with reflective listening, CBT perspective reframing, and supportive guidance."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            res = llm_client.generate_chat_completion(messages=messages, complexity="main", max_tokens=600)
            response = extract_reply(res, fallback="Reflection completed.")
            return {"success": True, "counseling_reflection": response}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def accounting_finance_calc(cls, revenue: float, operating_expenses: float, tax_rate_percent: float = 20.0) -> Dict[str, Any]:
        """
        Computes small business profit & loss, operating margin, tax estimation, and net income.
        """
        gross_profit = revenue - operating_expenses
        tax_estimate = max(gross_profit * (tax_rate_percent / 100.0), 0.0) if gross_profit > 0 else 0.0
        net_income = gross_profit - tax_estimate
        margin = (net_income / revenue * 100.0) if revenue > 0 else 0.0

        return {
            "success": True,
            "revenue": revenue,
            "operating_expenses": operating_expenses,
            "gross_profit": round(gross_profit, 2),
            "estimated_tax": round(tax_estimate, 2),
            "net_income": round(net_income, 2),
            "net_margin_percent": round(margin, 2)
        }
