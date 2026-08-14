from typing import Dict, Any, List, Optional
from app.database import db
from app.tools.web_research import WebResearcher
from app.tools.youtube_learner import YouTubeLearner
from app.tools.knowledge_indexer import KnowledgeIndexer
from app.utils.logger import app_logger, audit_logger

class SkillAcquisitionManager:
    @classmethod
    def check_memory_for_skill(cls, query: str) -> Optional[Dict[str, Any]]:
        """
        Checks SQLite memories for existing learned skills or notes matching the query.
        """
        memories = db.get_memories()
        query_words = set(query.lower().split())

        for mem in memories:
            content_lower = mem.get("content", "").lower()
            category = mem.get("category", "")
            
            # Check if relevant keywords match
            match_count = sum(1 for w in query_words if len(w) > 3 and w in content_lower)
            if match_count >= 2 or (match_count >= 1 and category in ["learned_skill", "youtube_learning"]):
                return {
                    "id": mem["id"],
                    "category": category,
                    "source": mem.get("source", "SQLite Memory"),
                    "content": mem["content"]
                }
        return None

    @classmethod
    def auto_acquire_skill_for_task(cls, task_title: str, task_goal: str) -> Dict[str, Any]:
        """
        Main autonomous skill loop:
        1. Checks SQLite memory for existing skill.
        2. If missing, searches YouTube for tutorial video.
        3. Extracts transcript, summarizes actionable checklist, and indexes into SQLite.
        """
        search_query = f"{task_title} {task_goal}"
        app_logger.info(f"Checking existing skills in memory for task: '{task_title}'")

        # Step 1: Check SQLite Memory
        existing = cls.check_memory_for_skill(search_query)
        if existing:
            app_logger.info(f"Found existing skill in SQLite memory for task '{task_title}'")
            return {
                "source": "sqlite_memory",
                "acquired": False,
                "existing_memory": existing,
                "summary": f"Using existing skill from memory (Source: {existing['source']}):\n\n{existing['content']}"
            }

        # Step 2: Missing skill -> Search YouTube for tutorial video
        app_logger.info(f"No existing skill in memory for '{task_title}'. Searching YouTube for tutorials...")
        
        # Search web for YouTube video links matching query
        search_res = WebResearcher.search_and_scrape(f"site:youtube.com/watch {search_query} tutorial", max_results=3)
        
        target_video_url = None
        if search_res.get("pages"):
            for page in search_res["pages"]:
                v_id = YouTubeLearner.extract_video_id(page["url"])
                if v_id:
                    target_video_url = page["url"]
                    break

        if not target_video_url:
            # Fallback search for demonstration or general tutorial search
            target_video_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"

        # Step 3: Extract Transcript & Learn Skill
        learned_res = YouTubeLearner.learn_from_video(target_video_url, prompt_focus=f"{task_title} - {task_goal}")
        
        if learned_res.get("success"):
            # Step 4: Save new skill into SQLite Memory
            mem_id = KnowledgeIndexer.index_youtube_knowledge(learned_res, category="learned_skill", confidence=0.95)
            db.create_audit_log(
                "auto_acquire_skill",
                "success",
                f"Autonomous YouTube Skill Acquisition for task '{task_title}'. Source: {learned_res.get('video_url')}",
                level=0
            )

            return {
                "source": "youtube_auto_learned",
                "acquired": True,
                "video_url": learned_res.get("video_url"),
                "memory_id": mem_id,
                "summary": f"✓ [AUTONOMOUSLY LEARNED SKILL FROM YOUTUBE]\nSource: {learned_res.get('video_url')}\nSaved to SQLite Memory ID #{mem_id}\n\n{learned_res.get('ai_summary')}"
            }

        return {
            "source": "none",
            "acquired": False,
            "error": "Could not automatically retrieve YouTube transcript for this topic. Please provide a direct tutorial link."
        }
