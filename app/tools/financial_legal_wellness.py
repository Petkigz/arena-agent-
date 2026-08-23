import os
import re
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger
from app.llm import (
    ModelCompletionUnavailable,
    llm_client,
    extract_reply,
    require_real_completion,
)

class FinancialLegalWellnessSuite:
    """Financial, legal, tone-calibration, and flashcard tools."""

    @staticmethod
    def _completion(result: Dict[str, Any]) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        try:
            return require_real_completion(result), None
        except ModelCompletionUnavailable as exc:
            return None, {
                "success": False,
                "available": False,
                "error_type": "model_unavailable",
                "error": str(exc),
            }

    @staticmethod
    def audit_subscriptions_and_trials(
        subscriptions_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Audits recurring SaaS subscriptions, free trial expiration dates, and detects upcoming billing alerts.
        Format of input item: {"service_name": "Netflix", "cost_monthly": 15.99, "trial_end_date": "2026-08-20"}
        """
        today = datetime.date.today()
        alerts = []
        total_monthly_cost = 0.0

        for sub in subscriptions_list:
            name = sub.get("service_name", "Unknown Service")
            cost = float(sub.get("cost_monthly", 0.0))
            trial_end_str = sub.get("trial_end_date", "")

            total_monthly_cost += cost

            if trial_end_str:
                try:
                    trial_end = datetime.datetime.strptime(trial_end_str, "%Y-%m-%d").date()
                    days_left = (trial_end - today).days
                    if 0 <= days_left <= 7:
                        alerts.append({
                            "service_name": name,
                            "type": "FREE_TRIAL_EXPIRING_SOON",
                            "days_remaining": days_left,
                            "message": f"CRITICAL: Free trial for '{name}' expires in {days_left} days ({trial_end_str})! Cancel if not needed."
                        })
                except Exception:
                    pass

        db.create_audit_log("audit_subscriptions_and_trials", "success", f"Audited {len(subscriptions_list)} subscriptions (Total: ${total_monthly_cost:.2f}/mo)", level=0)

        return {
            "success": True,
            "total_subscriptions_tracked": len(subscriptions_list),
            "estimated_monthly_spend": round(total_monthly_cost, 2),
            "urgent_alerts_count": len(alerts),
            "alerts": alerts
        }

    @staticmethod
    def audit_tos_and_privacy_policy(
        policy_text_or_url: str
    ) -> Dict[str, Any]:
        """
        Scans Terms of Service (ToS) or Privacy Policies for sneaky data selling, mandatory arbitration, or AI training rights.
        """
        prompt = (
            f"Perform a strict Privacy & Legal Audit on this Terms of Service / Privacy Policy text:\n\n"
            f"{policy_text_or_url[:6000]}\n\n"
            f"Flag any sneaky or harmful clauses regarding:\n"
            f"1) Selling personal data or sharing with data brokers\n"
            f"2) Permissions to train AI models on user content\n"
            f"3) Mandatory arbitration or loss of legal recourse\n"
            f"4) Automatic recurring price increases or cancellation penalties\n\n"
            f"Provide a risk rating (LOW, MEDIUM, HIGH, CRITICAL) and actionable legal takeaways."
        )

        llm_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            complexity="main",
            max_tokens=600
        )
        audit_summary, failure = FinancialLegalWellnessSuite._completion(llm_res)
        if failure:
            return failure

        db.create_audit_log("audit_tos_and_privacy_policy", "success", "Audited Terms of Service / Privacy Policy text", level=0)

        return {
            "success": True,
            "legal_audit_summary": audit_summary
        }

    @staticmethod
    def socratic_tone_sounding_board(
        draft_message: str,
        recipient_context: Optional[str] = "Professional Client / Colleague"
    ) -> Dict[str, Any]:
        """
        Acts as a Socratic sounding board to highlight unintended aggression, passive-aggressiveness,
        or logical fallacies in draft emails/messages.
        """
        prompt = (
            f"Review this draft message intended for '{recipient_context}':\n\n"
            f"\"{draft_message}\"\n\n"
            f"Critique this draft for:\n"
            f"1) Passive-aggressive or overly aggressive phrasing\n"
            f"2) Weak assumptions or logical fallacies\n"
            f"3) Recommended refined revision that achieves maximum leverage and respectful tone."
        )

        llm_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            complexity="main",
            max_tokens=500
        )
        critique, failure = FinancialLegalWellnessSuite._completion(llm_res)
        if failure:
            return failure

        return {
            "success": True,
            "original_draft": draft_message,
            "recipient_context": recipient_context,
            "socratic_critique": critique
        }

    @staticmethod
    def generate_anki_flashcards(
        study_material: str,
        deck_name: str = "Personal_AI_Knowledge"
    ) -> Dict[str, Any]:
        """
        Converts study notes or text into Anki-compatible flashcard import files (.txt / TSV).
        """
        prompt = (
            f"Extract key concepts from this study text and convert them into Anki Flashcard Front/Back Q&A pairs:\n\n"
            f"{study_material[:4000]}\n\n"
            f"Format output strictly as tab-separated Q&A pairs:\n"
            f"Question <TAB> Answer"
        )

        llm_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            complexity="fast",
            max_tokens=500
        )
        raw_qa, failure = FinancialLegalWellnessSuite._completion(llm_res)
        if failure:
            return failure

        export_dir = settings.DATA_DIR / "workspace" / "anki_decks"
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{deck_name.replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d')}.txt"
        filepath = export_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Anki Deck Export: {deck_name}\n" + raw_qa)

        db.create_audit_log("generate_anki_flashcards", "success", f"Generated Anki deck '{filename}'", level=0)

        return {
            "success": True,
            "deck_name": deck_name,
            "anki_file_path": str(filepath),
            "flashcard_content_snippet": raw_qa[:300]
        }
