"""Content creation — professional-grade multi-format content generator.

Produces platform-appropriate content (YouTube script, X/Twitter thread, LinkedIn
post, short caption, email, ad copy) with input validation, safe LLM extraction,
and optional workspace persistence. Backward-compatible with the old
`generate_content_script` entry point.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional

from app.llm import llm_client, extract_reply, require_real_completion
from app.tools.doc_manager import DocumentManager
from app.utils.logger import app_logger, audit_logger

# Supported content types → prompt guidance.
CONTENT_TYPES = {
    "youtube_script": "a YouTube video script (hook, body, CTA) with timestamps",
    "twitter_thread": "a Twitter/X thread of 6-10 numbered tweets (hook, value, CTA)",
    "linkedin_post": "a LinkedIn post with a strong hook, insight, and call-to-action",
    "short_caption": "a short-form caption (TikTok/Reels/Shorts) under 150 words",
    "email": "a persuasive email with subject line and body",
    "ad_copy": "ad copy (headline + body) for a specific offer",
}

PLATFORMS = {
    "youtube": "youtube_script",
    "twitter": "twitter_thread",
    "x": "twitter_thread",
    "linkedin": "linkedin_post",
    "tiktok": "short_caption",
    "instagram": "short_caption",
    "email": "email",
    "ad": "ad_copy",
}


class ContentCreatorTool:
    @classmethod
    def generate_content(
        cls,
        topic: str,
        content_type: str = "linkedin_post",
        target_audience: str = "developers & tech enthusiasts",
        tone: str = "confident and clear",
        auto_save: bool = True,
        complexity: str = "main",
    ) -> Dict[str, Any]:
        """Generate content of a given type on a topic.

        content_type must be one of: youtube_script, twitter_thread, linkedin_post,
        short_caption, email, ad_copy.
        """
        if not topic or not topic.strip():
            return {"success": False, "error": "A topic is required."}

        ctype = content_type.lower().strip()
        if ctype not in CONTENT_TYPES:
            return {
                "success": False,
                "error": f"Unsupported content_type '{content_type}'. "
                         f"Choose from: {', '.join(sorted(CONTENT_TYPES))}.",
            }

        guidance = CONTENT_TYPES[ctype]
        system_prompt = (
            "You are a senior content strategist and copywriter. Produce "
            "publish-ready content with a compelling hook, substance, and a clear "
            "call-to-action. Do not add commentary about the content itself."
        )
        user_prompt = (
            f"Topic: {topic}\n"
            f"Format: {guidance}\n"
            f"Target audience: {target_audience}\n"
            f"Tone: {tone}\n"
        )

        try:
            text = require_real_completion(llm_client.generate_chat_completion(
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                complexity=complexity,
                max_tokens=1200,
            ))

            if not text:
                return {"success": False, "error": "The model returned no content."}

            result: Dict[str, Any] = {
                "success": True,
                "topic": topic,
                "content_type": ctype,
                "content": text,
                "draft_file": None,
            }

            if auto_save:
                slug = "_".join(topic.lower().split())[:40]
                path = f"drafts/{ctype}_{slug}.md"
                body = f"# {ctype.replace('_', ' ').title()}: {topic}\n\n{text}\n"
                try:
                    DocumentManager.create_document(path, body, overwrite=True)
                    result["draft_file"] = path
                    audit_logger.info(f"Saved {ctype} draft: {path}")
                except Exception as e:
                    app_logger.warning(f"Could not save content draft: {e}")

            return result
        except Exception as e:
            app_logger.error(f"Content generation failed: {e}")
            return {"success": False, "error": f"Content generation error: {e}", "topic": topic}

    # ── Backward-compatible entry points ────────────────────────────────────
    @classmethod
    def generate_content_script(
        cls,
        topic: str,
        platform: str = "youtube",
        target_audience: str = "developers & tech enthusiasts",
        auto_save_workspace: bool = True,
    ) -> Dict[str, Any]:
        """Legacy wrapper: map a platform name → content type and generate."""
        ctype = PLATFORMS.get(platform.lower().strip(), "linkedin_post")
        res = cls.generate_content(
            topic=topic,
            content_type=ctype,
            target_audience=target_audience,
            auto_save=auto_save_workspace,
        )
        # Preserve the old response shape for existing callers.
        if res.get("success"):
            return {
                "success": True,
                "topic": topic,
                "platform": platform,
                "script_text": res["content"],
                "draft_file": res.get("draft_file"),
            }
        return res
