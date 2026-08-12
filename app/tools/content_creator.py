from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.tools.doc_manager import DocumentManager
from app.utils.logger import app_logger, audit_logger

class ContentCreatorTool:
    @classmethod
    def generate_content_script(
        cls, 
        topic: str, 
        platform: str = "youtube", 
        target_audience: str = "developers & tech enthusiasts",
        auto_save_workspace: bool = True
    ) -> Dict[str, Any]:
        """
        Generates viral post outlines, YouTube video scripts, Twitter/X threads, and SEO tags.
        Saves drafts automatically to data/workspace/drafts/.
        """
        system_prompt = (
            "You are a master social media content strategist and scriptwriter. "
            "Generate high-engagement, hook-driven content outlines and scripts."
        )

        user_prompt = f"""
Generate a high-engagement content script for:
- Topic: "{topic}"
- Platform: {platform.upper()} (YouTube video, Twitter thread, LinkedIn post, or Short)
- Target Audience: {target_audience}

Provide:
1. **Hook**: Attention-grabbing opening statement (0-5 seconds).
2. **Core Outline & Body Paragraphs**: Main value points, code examples, or story arc.
3. **Call-To-Action (CTA)**: High-converting closing statement.
4. **SEO Hashtags & Keywords**: Top 8 relevant tags.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=900
            )

            script_text = llm_res["choices"][0]["message"]["content"] if llm_res.get("choices") else "Content script generated."

            file_path_str = f"drafts/script_{platform.lower()}_{topic.lower().replace(' ', '_')[:20]}.md"
            save_res = None

            if auto_save_workspace:
                save_res = DocumentManager.create_document(
                    file_path_str, 
                    f"# Content Script: {topic}\nPlatform: {platform.upper()}\n\n{script_text}", 
                    overwrite=True
                )
                audit_logger.info(f"Saved content script draft: {file_path_str}")

            return {
                "success": True,
                "topic": topic,
                "platform": platform,
                "script_text": script_text,
                "draft_file": file_path_str if auto_save_workspace else None
            }
        except Exception as e:
            app_logger.error(f"Error generating content script: {e}")
            return {
                "success": False,
                "error": f"Content script error: {str(e)}",
                "topic": topic
            }
