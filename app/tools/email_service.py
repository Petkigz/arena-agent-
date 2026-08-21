"""Email send/read — native coworker tool (Level-3 gated by the caller).

Uses only the Python stdlib (smtplib / imaplib / email). Credentials come from
environment variables (never hardcoded): ARENA_SMTP_HOST, ARENA_SMTP_PORT,
ARENA_SMTP_USER, ARENA_SMTP_PASS, ARENA_IMAP_HOST.

Degrades gracefully: returns a clear error when credentials are unconfigured.
"""

from __future__ import annotations

import email
import imaplib
import os
import smtplib
from email.message import EmailMessage
from typing import Dict, Any, List, Optional

from app.utils.logger import app_logger, audit_logger


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


class EmailService:
    @classmethod
    def is_configured(cls) -> bool:
        return bool(_env("ARENA_SMTP_HOST") and _env("ARENA_SMTP_USER"))

    @classmethod
    def send_email(
        cls,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a plain-text email. Requires SMTP credentials via env vars."""
        host = _env("ARENA_SMTP_HOST")
        port = int(_env("ARENA_SMTP_PORT", "587") or "587")
        user = _env("ARENA_SMTP_USER")
        password = _env("ARENA_SMTP_PASS", "") or ""

        if not host or not user:
            return {
                "success": False,
                "error": "Email not configured. Set ARENA_SMTP_HOST/USER/PASS environment variables.",
            }

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_name or user
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        msg.set_content(body)

        try:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)
            audit_logger.info(f"Sent email to {to} (subject: {subject[:60]})")
            return {"success": True, "to": to, "subject": subject}
        except Exception as e:
            app_logger.warning(f"Email send failed: {e}")
            return {"success": False, "error": f"Email send failed: {e}"}

    @classmethod
    def read_inbox(cls, limit: int = 10) -> Dict[str, Any]:
        """Read the most recent N messages from the inbox (subject + sender)."""
        host = _env("ARENA_IMAP_HOST") or _env("ARENA_SMTP_HOST")
        user = _env("ARENA_SMTP_USER")
        password = _env("ARENA_SMTP_PASS", "") or ""

        if not host or not user:
            return {"success": False, "error": "Email not configured (IMAP)."}

        try:
            M = imaplib.IMAP4_SSL(host)
            M.login(user, password)
            M.select("INBOX")

            typ, data = M.search(None, "ALL")
            if typ != "OK":
                return {"success": False, "error": "IMAP search failed."}

            ids = data[0].split()[-limit:]
            messages: List[Dict[str, str]] = []
            for i in reversed(ids):
                typ, msg_data = M.fetch(i, "(RFC822)")
                if typ != "OK":
                    continue
                raw = msg_data[0][1]
                parsed = email.message_from_bytes(raw)
                messages.append({
                    "from": parsed.get("From", ""),
                    "subject": parsed.get("Subject", ""),
                    "date": parsed.get("Date", ""),
                })
            M.logout()
            return {"success": True, "messages": messages}
        except Exception as e:
            app_logger.warning(f"Inbox read failed: {e}")
            return {"success": False, "error": f"Inbox read failed: {e}"}
