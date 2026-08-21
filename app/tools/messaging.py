"""Messaging — send Telegram and WhatsApp messages.

Deterministic httpx calls to provider HTTP APIs, no LLM. Both are Level 3
(sending a message to another person is sensitive/irreversible) and gated behind
owner approval. Credentials come from env vars, so secrets never sit in tool
payloads:

- Telegram: ARENA_TELEGRAM_BOT_TOKEN (required), ARENA_TELEGRAM_CHAT_ID (default).
- WhatsApp: Twilio — ARENA_TWILIO_ACCOUNT_SID, ARENA_TWILIO_AUTH_TOKEN,
  ARENA_TWILIO_FROM (your Twilio WhatsApp sender, e.g. 'whatsapp:+1415...').

Unconfigured providers degrade to a clear "set these env vars" error.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from app.utils.logger import app_logger, audit_logger


class Messaging:
    @classmethod
    def send_telegram(cls, message: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Send a Telegram message via the Bot API."""
        message = (message or "").strip()
        if not message:
            return {"success": False, "error": "A message is required."}
        token = os.environ.get("ARENA_TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return {"success": False, "error": "Telegram is not configured: set ARENA_TELEGRAM_BOT_TOKEN."}
        chat_id = (chat_id or os.environ.get("ARENA_TELEGRAM_CHAT_ID", "")).strip()
        if not chat_id:
            return {"success": False, "error": "Telegram chat_id is required (or set ARENA_TELEGRAM_CHAT_ID)."}

        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=15.0,
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 200 and data.get("ok"):
                audit_logger.info(f"Sent Telegram message to {chat_id}")
                return {"success": True, "channel": "telegram", "chat_id": chat_id}
            err = (data.get("description") or f"HTTP {resp.status_code}")
            return {"success": False, "error": f"Telegram send failed: {err}"}
        except httpx.HTTPError as e:
            app_logger.warning(f"Telegram send failed: {e}")
            return {"success": False, "error": f"Telegram send failed: {e}"}

    @classmethod
    def send_whatsapp(cls, message: str, to: Optional[str] = None) -> Dict[str, Any]:
        """Send a WhatsApp message via Twilio (requires a configured sender)."""
        message = (message or "").strip()
        if not message:
            return {"success": False, "error": "A message is required."}
        sid = os.environ.get("ARENA_TWILIO_ACCOUNT_SID", "").strip()
        token = os.environ.get("ARENA_TWILIO_AUTH_TOKEN", "").strip()
        frm = os.environ.get("ARENA_TWILIO_FROM", "").strip()
        if not (sid and token and frm):
            return {
                "success": False,
                "error": "WhatsApp is not configured: set ARENA_TWILIO_ACCOUNT_SID, "
                         "ARENA_TWILIO_AUTH_TOKEN, and ARENA_TWILIO_FROM.",
            }
        to = (to or os.environ.get("ARENA_TWILIO_TO", "")).strip()
        if not to:
            return {"success": False, "error": "WhatsApp recipient 'to' is required (e.g. 'whatsapp:+1415...')."}

        try:
            resp = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"From": frm, "To": to, "Body": message},
                auth=(sid, token),
                timeout=15.0,
            )
            if resp.status_code in (200, 201):
                audit_logger.info(f"Sent WhatsApp message to {to}")
                return {"success": True, "channel": "whatsapp", "to": to}
            return {"success": False, "error": f"WhatsApp send failed: HTTP {resp.status_code}"}
        except httpx.HTTPError as e:
            app_logger.warning(f"WhatsApp send failed: {e}")
            return {"success": False, "error": f"WhatsApp send failed: {e}"}
