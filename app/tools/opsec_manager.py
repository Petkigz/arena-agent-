import os
import json
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
from app.config import settings
from app.database import db
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger
from app.tools.web_research import WebResearcher
from app.llm import llm_client, extract_reply, require_real_completion

class OpSecManagerTool:
    """
    Operational Security (OpSec) & Digital Footprint Management Engine.
    Scrapes the web for exposed credentials, forgotten logins, PII leaks, and data brokers.
    Uses pandas data analytics to assess exposure risk and drafts legally compliant GDPR/CCPA
    data erasure and account deletion requests.
    """

    @staticmethod
    def audit_digital_footprint(query_identifier: str) -> Dict[str, Any]:
        """
        Scans for online digital footprint exposures matching an email, username, or name.
        """
        app_logger.info(f"Initiating OpSec digital footprint scan for query: '{query_identifier}'")
        search_query = f'"{query_identifier}" login breach password account data leak'
        search_results = WebResearcher.search_and_scrape(search_query, max_results=5)

        raw_results = search_results.get("results", [])
        exposures = []

        # Analyze scraped findings for exposure risk
        for idx, item in enumerate(raw_results, 1):
            snippet = item.get("snippet", "") + " " + item.get("title", "")
            snippet_lower = snippet.lower()

            risk_level = "LOW"
            privacy_cvss = 2.5
            exposure_type = "Public Web Mention"

            if any(k in snippet_lower for w in ["password", "hash", "breach", "leak", "dump", "paste"] for k in [w]):
                risk_level = "CRITICAL"
                privacy_cvss = 9.0
                exposure_type = "Credential / Password Breach Leak"
            elif any(k in snippet_lower for w in ["broker", "people search", "directory", "phone", "address"] for k in [w]):
                risk_level = "HIGH"
                privacy_cvss = 7.5
                exposure_type = "Data Broker / PII Directory Listing"
            elif any(k in snippet_lower for w in ["forum", "profile", "account", "login", "register"] for k in [w]):
                risk_level = "MEDIUM"
                privacy_cvss = 5.0
                exposure_type = "Forgotten Account / Profile Sign-Up"

            exposures.append({
                "id": idx,
                "source_url": item.get("url", "N/A"),
                "source_title": item.get("title", "Scraped Web Result"),
                "exposure_type": exposure_type,
                "risk_level": risk_level,
                "privacy_cvss_score": privacy_cvss,
                "snippet": snippet[:200]
            })

        # Use pandas for data analytics
        df = pd.DataFrame(exposures) if exposures else pd.DataFrame(columns=["id", "exposure_type", "risk_level", "privacy_cvss_score"])
        risk_counts = df["risk_level"].value_counts().to_dict() if not df.empty else {}
        avg_risk_score = round(float(df["privacy_cvss_score"].mean()), 2) if not df.empty else 0.0

        db.create_audit_log("audit_digital_footprint", "success", f"Audited footprint for '{query_identifier}': {len(exposures)} findings (Avg CVSS: {avg_risk_score})", level=0)

        return {
            "success": True,
            "query_identifier": query_identifier,
            "total_exposures_found": len(exposures),
            "average_privacy_risk_score": avg_risk_score,
            "risk_distribution": risk_counts,
            "findings": exposures
        }

    @staticmethod
    def generate_erasure_requests(
        target_service_name: str,
        user_identifier: str,
        jurisdiction: str = "GDPR Article 17 / CCPA"
    ) -> Dict[str, Any]:
        """
        Drafts a formal, legally binding Data Erasure & Right-to-be-Forgotten request letter.
        Follows Level 1 (Drafting) policy autonomously, flagged for Level 3 approval before sending.
        """
        prompt = (
            f"Draft a formal, imperative 'Right to Erasure / Account Deletion' request letter under {jurisdiction}.\n"
            f"Target Service / Data Broker: {target_service_name}\n"
            f"User Identity / Email / Username: {user_identifier}\n\n"
            f"Requirements:\n"
            f"1) Specify statutory grounds for deletion of all personal data, credential logs, and account profiles.\n"
            f"2) Request written confirmation of data deletion within 30 days.\n"
            f"3) Include placeholder signature and contact details."
        )

        llm_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            complexity="main",
            max_tokens=600
        )
        try:
            erasure_letter = require_real_completion(llm_res)
        except Exception as exc:
            return {
                "success": False,
                "available": False,
                "error_type": "model_unavailable",
                "error": str(exc),
            }

        # Safety Policy Check for Level 3 submission approval
        allowed, reason, level = PolicyEvaluator.evaluate_action(
            "send_email",
            {"recipient": f"privacy@{target_service_name}.com", "subject": f"Data Erasure Request - {user_identifier}"}
        )

        db.create_memory({
            "content": f"OpSec Erasure Request drafted for service '{target_service_name}' ({user_identifier}).",
            "category": "opsec_privacy",
            "source": "opsec_manager",
            "confidence": 1.0
        })

        db.create_audit_log("generate_erasure_requests", "success", f"Drafted erasure request for '{target_service_name}'", level=1)

        return {
            "success": True,
            "target_service": target_service_name,
            "user_identifier": user_identifier,
            "jurisdiction": jurisdiction,
            "erasure_letter_draft": erasure_letter,
            "submission_safety_status": {
                "auto_submitted": allowed,
                "reason": reason,
                "authority_level": level,
                "approval_action_required": "User must click 1-click Approval to dispatch email or submit opt-out web form."
            }
        }
