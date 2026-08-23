import httpx
from typing import Dict, Any, Optional
from app.policy import PolicyEvaluator
from app.tools.doc_manager import DocumentManager
from app.utils.logger import app_logger, audit_logger
from app.cognition.execution_control import (
    ExecutionCancelled,
    run_cancellable_blocking_call,
)

class ConnectorsTool:
    @classmethod
    def trigger_webhook(cls, webhook_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Triggers an external webhook (e.g. Discord, Slack, Zapier, Make.com) under Level 2/3 Safety Policy.
        """
        webhook_url = webhook_url.strip()
        allowed, reason, level = PolicyEvaluator.evaluate_action("send_webhook", {"url": webhook_url})
        if not allowed:
            return {"success": False, "error": f"Policy Blocked: {reason}", "authority_level": level}

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.post(webhook_url, json=payload),
                    cancel=client.close,
                    description="webhook send request",
                )
                resp.raise_for_status()

            audit_logger.info(f"Triggered webhook at {webhook_url}")
            return {
                "success": True,
                "status_code": resp.status_code,
                "message": f"Webhook triggered successfully at {webhook_url}."
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.error(f"Error triggering webhook '{webhook_url}': {e}")
            return {"success": False, "error": f"Webhook error: {str(e)}"}

    @classmethod
    def prepare_email_draft(cls, to_address: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Prepares an email draft in Level 1 (Draft status). Sending live emails is Level 3 blocked.
        """
        file_name = f"drafts/email_{to_address.replace('@', '_at_')[:20]}.md"
        content = f"# Email Draft\n**To:** {to_address}\n**Subject:** {subject}\n\n---\n\n{body}"

        res = DocumentManager.create_document(file_name, content, overwrite=True)
        audit_logger.info(f"Prepared email draft for {to_address}: {file_name}")

        return {
            "success": True,
            "to_address": to_address,
            "subject": subject,
            "draft_file": file_name,
            "note": "Email draft created in workspace. Sending live emails requires Level 3 explicit user approval."
        }
