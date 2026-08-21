"""Translation via the local Qwen LLM — no external API, no key.

Uses llm_client (which falls back to a simulated response when offline), so it
always returns a well-formed dict.
"""

from __future__ import annotations

from typing import Dict, Any

from app.llm import llm_client
from app.utils.logger import app_logger


class TranslatorTool:
    @classmethod
    def translate(cls, text: str, target_language: str, source_language: str = "auto") -> Dict[str, Any]:
        if not text or not text.strip():
            return {"success": False, "error": "No text to translate."}

        system = (
            "You are a translator. Translate the user's text into the requested "
            "language. Output ONLY the translation, with no commentary."
        )
        user = f"Target language: {target_language}\nText: {text}"
        try:
            res = llm_client.generate_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                complexity="fast",
                max_tokens=1024,
            )
            translation = res.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return {
                "success": True,
                "translation": translation,
                "source_language": source_language,
                "target_language": target_language,
            }
        except Exception as e:
            app_logger.warning(f"Translation failed: {e}")
            return {"success": False, "error": f"Translation failed: {e}"}
